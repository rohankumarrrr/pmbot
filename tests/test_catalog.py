"""The catalog pull: what it keeps in memory and what it writes to the ledger."""

from pmbot import catalog
from pmbot.ledger.db import Ledger


def market(ticker: str) -> dict:
    return {"ticker": ticker, "status": "active", "market_type": "binary", "title": f"Will {ticker} happen?",
            "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.45", "close_time": "2027-01-01T00:00:00Z",
            "rules_primary": f"Resolves YES if {ticker}.", "rules_secondary": "Source: the agency.",
            "price_ranges": [{"start": "0.01", "end": "0.99", "step": "0.01"}]}


class Exchange:
    def __init__(self, tickers):
        self.tickers = tickers

    def events(self, **_):
        yield {"event_ticker": "S-E1", "series_ticker": "S", "title": "Event", "markets": [market(t) for t in self.tickers]}

    def get(self, path, **params):
        return {"markets": [market(t) for t in params["tickers"].split(",")]}


SERIES = {"S": {"category": "Economics", "fee_type": "quadratic", "fee_multiplier": 1.0}}


def test_pull_writes_each_market_once_and_keeps_rules_out_of_memory():
    ledger = Ledger(":memory:")
    quotes = catalog.pull_open_quotes(Exchange(["S-E1-A", "S-E1-B"]), ledger, SERIES)
    assert [q.ticker for q in quotes] == ["S-E1-A", "S-E1-B"] and quotes[0].yes_bid == 0.40
    assert quotes[0].rules == ""                                   # rules text is in the ledger, not on 200,000 quotes
    assert quotes[0].price_ranges is quotes[1].price_ranges        # identical tick tables are shared
    stored = ledger.one("SELECT rules_primary, first_seen_ts FROM markets WHERE ticker='S-E1-A'")
    assert stored["rules_primary"] == "Resolves YES if S-E1-A."

    ledger.execute("UPDATE markets SET first_seen_ts=1 WHERE ticker='S-E1-A'")
    quotes = catalog.pull_open_quotes(Exchange(["S-E1-A", "S-E1-B", "S-E1-C"]), ledger, SERIES)   # one new listing
    assert len(quotes) == 3
    assert ledger.one("SELECT COUNT(*) AS n FROM markets")["n"] == 3
    assert ledger.one("SELECT first_seen_ts FROM markets WHERE ticker='S-E1-A'")["first_seen_ts"] == 1   # not rewritten
    assert ledger.one("SELECT COUNT(*) AS n FROM events")["n"] == 1


def test_rules_are_fetched_for_the_markets_being_forecast():
    exchange = Exchange(["S-E1-A"])
    quotes = catalog.pull_open_quotes(exchange, Ledger(":memory:"), SERIES)
    catalog.attach_rules(exchange, quotes)
    assert quotes[0].rules == "Resolves YES if S-E1-A.\n\nSource: the agency."


def test_day_ago_price_falls_back_to_that_days_book_when_nothing_traded():
    assert catalog.day_ago_price({"previous_price_dollars": "0.3100", "previous_yes_bid_dollars": "0.5000", "previous_yes_ask_dollars": "0.9500"}) == 0.31
    assert catalog.day_ago_price({"previous_price_dollars": "0.0000", "previous_yes_bid_dollars": "0.5000", "previous_yes_ask_dollars": "0.9500"}) == 0.725
    assert catalog.day_ago_price({"previous_price_dollars": "0.0000", "previous_yes_bid_dollars": "0.0000", "previous_yes_ask_dollars": "0.9900"}) == 0.0   # no book either


def test_a_market_that_fell_from_its_day_ago_book_counts_as_moving():
    from pmbot import config, lp
    cfg, now = config.load("config/settings.yaml"), 1_000_000
    m = {**market("S-E1-A"), "yes_bid_dollars": "0.29", "yes_ask_dollars": "0.50", "close_time": "2027-01-01T00:00:00Z",
         "previous_price_dollars": "0.0000", "previous_yes_bid_dollars": "0.5000", "previous_yes_ask_dollars": "0.9500"}

    class One(Exchange):
        def events(self, **_):
            yield {"event_ticker": "S-E1", "series_ticker": "S", "title": "Event", "markets": [m]}

    (q,) = catalog.pull_open_quotes(One([]), Ledger(":memory:"), SERIES)
    prog = lp.Program("S-E1-A", "S", 10.0, 1000, 0.5, 0, now + 30 * 86400)
    assert "price_moving" in lp.market_reasons(prog, q, cfg.lp, now)


def test_a_market_settled_before_its_listed_close_is_still_picked_up():
    """Kalshi settles a market once its outcome is known, which can be a week before the listed close."""
    class Settled(Exchange):
        def get(self, path, **params):
            return {"markets": [{**market(t), "status": "finalized", "result": "no"} for t in params["tickers"].split(",")]}

    ledger = Ledger(":memory:")
    catalog.pull_open_quotes(Exchange(["S-E1-A", "S-E1-B", "S-E1-C"]), ledger, SERIES)     # all close in 2027
    ledger.insert_many("decisions", [{"id": f"d-{t}", "kind": "lp", "ticker": t, "event_ticker": "S-E1", "created_ts": 1,
                                      "mode": "live", "action": "quote"} for t in ("S-E1-A", "S-E1-B")])
    stamp = 1_790_000_000                                                                  # long before that close
    assert catalog.unsettled(ledger, {"S-E1-A", "S-E1-B", "S-E1-C"}, stamp) == []          # both still trading
    assert catalog.unsettled(ledger, {"S-E1-A", "S-E1-C"}, stamp) == ["S-E1-B"]            # B has left the open catalogue
    assert catalog.unsettled(ledger, set(), stamp) == []                                   # no catalogue: close date only

    assert catalog.sync_settlements(Settled([]), ledger, ["S-E1-B"]) == 1
    assert ledger.one("SELECT result FROM markets WHERE ticker='S-E1-B'")["result"] == "no"
    assert catalog.unsettled(ledger, {"S-E1-A", "S-E1-C"}, stamp) == []                    # and it is not asked for again
