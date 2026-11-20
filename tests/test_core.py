import math

import pytest

from pmbot import config
from pmbot.blend import blend, calibrate, kelly_fraction, size_order
from pmbot.execution.brokers import ShadowBroker, book_order, client_order_id
from pmbot.kalshi.fees import fee_per_contract, order_fee
from pmbot.ledger.db import Ledger, now
from pmbot.portfolio import account, positions
from pmbot.risk import RiskManager


@pytest.fixture
def cfg():
    return config.load("config/settings.yaml")


@pytest.fixture
def ledger():
    led = Ledger(":memory:")
    led.insert("series", {"ticker": "S", "title": "", "category": "Economics", "frequency": "", "fee_type": "quadratic",
                          "fee_multiplier": 1.0, "tags": [], "updated_ts": 0})
    for t in ("S-E1-A", "S-E1-B", "S-E2-A"):
        led.insert("markets", {"ticker": t, "event_ticker": t.rsplit("-", 1)[0], "series_ticker": "S", "status": "active"})
    return led


# --- fees -----------------------------------------------------------------

def test_taker_fee_matches_published_formula():
    assert fee_per_contract(0.50, maker=False) == pytest.approx(0.0175)
    assert fee_per_contract(0.41, maker=False) == pytest.approx(0.07 * 0.41 * 0.59)


def test_maker_fee_depends_on_series():
    assert fee_per_contract(0.50, maker=True) == 0.0
    assert fee_per_contract(0.50, maker=True, fee_type="quadratic_with_maker_fees") == pytest.approx(0.004375)
    assert fee_per_contract(0.50, maker=True, fee_type="quadratic_with_combo_maker_fees") == pytest.approx(0.00875)


def test_order_fee_rounds_up_to_balance_precision():
    assert order_fee(0.41, 1, maker=False) == pytest.approx(0.0170)     # 0.016933 -> 0.0170
    assert order_fee(0.50, 100, maker=False) == pytest.approx(1.75)


# --- blending and sizing ----------------------------------------------------

def test_blend_is_log_odds_average_and_shrinks_disagreement():
    assert blend(0.555, 0.40, 0.67) == pytest.approx(0.4505, abs=1e-3)   # the design's worked example
    assert blend(0.9, 0.4, 1.0) == pytest.approx(0.4)
    assert blend(0.9, 0.4, 0.0) == pytest.approx(0.9)


def test_calibrate_identity_and_extremizing():
    assert calibrate(0.3) == pytest.approx(0.3)
    assert calibrate(0.7, a=math.sqrt(3)) > 0.7
    assert calibrate(0.3, a=math.sqrt(3)) < 0.3


def test_kelly_fraction():
    assert kelly_fraction(0.4505, 0.40) == pytest.approx(0.0505 / 0.60)
    assert kelly_fraction(0.30, 0.40) == 0.0


def test_size_order_worked_example():
    s = size_order(0.4505, yes_price=0.40, no_price=0.60, bankroll=1000, kelly_mult=0.2, max_fraction=0.03, min_edge=0.03)
    assert (s.side, s.contracts) == ("yes", 42)
    assert s.edge == pytest.approx(0.0505)


def test_size_order_picks_no_side_and_respects_cap():
    s = size_order(0.20, yes_price=0.40, no_price=0.60, bankroll=1000, kelly_mult=1.0, max_fraction=0.03, min_edge=0.03)
    assert s.side == "no"
    assert s.contracts == 50   # 3% of $1,000 at 60c


def test_size_order_refuses_thin_edge_and_taker_fee_eats_it():
    assert size_order(0.42, 0.40, 0.60, 1000).side is None
    maker = size_order(0.4505, 0.41, 0.59, 1000, maker=True)
    taker = size_order(0.4505, 0.41, 0.59, 1000, maker=False)
    assert maker.side == "yes" and taker.side is None


# --- order book translation -------------------------------------------------

def test_buying_no_is_an_ask_on_the_yes_book():
    assert book_order("yes", 0.40) == ("bid", 0.40)
    assert book_order("no", 0.60) == ("ask", 0.40)


# --- shadow fills -----------------------------------------------------------

class Tape:
    def __init__(self, trades):
        self._trades = trades

    def trades(self, **_):
        return iter(self._trades)


def trade(yes_price, count, taker_side, at=None):
    stamp = at or now()
    iso = __import__("datetime").datetime.fromtimestamp(stamp, __import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
    return {"yes_price_dollars": f"{yes_price:.4f}", "count_fp": f"{count:.2f}", "taker_outcome_side": taker_side,
            "is_block_trade": False, "created_time": iso}


def place(ledger, tape, side, price, n, queue=0.0, decision="d1", ticker="S-E1-A"):
    broker = ShadowBroker(ledger, Tape(tape))
    broker.place(decision, ticker, side, price, n, ttl_s=3600, queue_ahead=queue)
    return broker


def filled(ledger, decision="d1"):
    return ledger.one("SELECT COALESCE(SUM(contracts),0) AS n FROM fills WHERE client_order_id=?", [client_order_id(decision)])["n"]


def test_bid_fills_when_takers_sell_through_it(ledger):
    broker = place(ledger, [trade(0.39, 5, "no")], "yes", 0.40, 10)
    broker.sync()
    assert filled(ledger) == 10


def test_bid_ignores_takers_buying_and_trades_above(ledger):
    broker = place(ledger, [trade(0.38, 50, "yes"), trade(0.41, 50, "no")], "yes", 0.40, 10)
    broker.sync()
    assert filled(ledger) == 0


def test_trades_at_our_price_fill_only_after_the_queue_ahead(ledger):
    broker = place(ledger, [trade(0.40, 30, "no"), trade(0.40, 30, "no")], "yes", 0.40, 10, queue=50)
    broker.sync()
    assert filled(ledger) == 10          # 60 traded at our price: 50 ahead of us, then our 10
    broker2 = place(ledger, [trade(0.40, 30, "no")], "yes", 0.40, 10, queue=50, decision="d2")
    broker2.sync()
    assert filled(ledger, "d2") == 0


def test_no_order_fills_when_takers_buy_yes_through_it(ledger):
    # Buying NO at 0.60 rests as an ask on YES at 0.40.
    broker = place(ledger, [trade(0.41, 5, "yes")], "no", 0.60, 10)
    broker.sync()
    row = ledger.one("SELECT side, price, contracts FROM fills")
    assert (row["side"], row["price"], row["contracts"]) == ("no", 0.60, 10)


def test_placing_the_same_decision_twice_creates_one_order(ledger):
    broker = place(ledger, [], "yes", 0.40, 10)
    broker.place("d1", "S-E1-A", "yes", 0.40, 10, 3600)
    assert ledger.one("SELECT COUNT(*) AS n FROM orders")["n"] == 1


# --- portfolio --------------------------------------------------------------

def fill(ledger, decision, ticker, side, price, n):
    ShadowBroker(ledger, Tape([])).place(decision, ticker, side, price, n, 3600)
    ledger.insert("fills", {"id": decision, "client_order_id": client_order_id(decision), "ticker": ticker, "side": side,
                            "price": price, "contracts": n, "fee": 0.0, "ts": now(), "simulated": True})
    ledger.execute("UPDATE orders SET status='filled' WHERE client_order_id=?", [client_order_id(decision)])


def test_partly_filled_order_is_not_counted_twice(ledger, cfg):
    ShadowBroker(ledger, Tape([])).place("a", "S-E1-A", "yes", 0.40, 50, 3600)      # $20 order
    ledger.insert("fills", {"id": "f", "client_order_id": client_order_id("a"), "ticker": "S-E1-A", "side": "yes",
                            "price": 0.40, "contracts": 25, "fee": 0.0, "ts": now(), "simulated": True})
    ledger.execute("UPDATE orders SET status='partial'")
    v = RiskManager(ledger, cfg, "shadow", 1000).review(sizing(100), "S-E1-A", "S-E1")
    assert v.contracts == 25     # $30 cap - $10 filled - $10 still resting = $10 of room at 40c


def test_account_tracks_cost_and_settlement(ledger):
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 10)
    acct = account(ledger, "shadow", 1000)
    assert acct.cash == pytest.approx(996) and acct.open_cost == pytest.approx(4)
    ledger.execute("UPDATE markets SET result='yes' WHERE ticker='S-E1-A'")
    acct = account(ledger, "shadow", 1000)
    assert acct.cash == pytest.approx(1006) and acct.realized == pytest.approx(6) and not acct.open_positions


def test_losing_position_and_no_side_payout(ledger):
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 10)
    fill(ledger, "b", "S-E2-A", "no", 0.70, 10)
    ledger.execute("UPDATE markets SET result='no'")
    acct = account(ledger, "shadow", 1000)
    assert acct.realized == pytest.approx(-4 + 3)


def test_yes_and_no_in_one_market_pair_off(ledger):
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 10)
    fill(ledger, "b", "S-E1-A", "no", 0.55, 10)
    (p,) = positions(ledger, "shadow")
    assert p.contracts == 0 and p.cost == pytest.approx(4 + 5.5 - 10)   # locked in a 50c gain


# --- order leases -----------------------------------------------------------

class TimedTape(Tape):
    def trades(self, min_ts=None, max_ts=None, **_):
        from pmbot.catalog import ts
        return iter(t for t in self._trades if min_ts <= ts(t["created_time"]) <= max_ts)


def test_an_order_whose_lease_lapsed_takes_no_paper_fills_afterwards(ledger):
    # The bot stopped for a while; a seller then traded through our bid. On the exchange the order was gone.
    broker = ShadowBroker(ledger, TimedTape([trade(0.20, 50, "no", at=now() - 60)]), lease_s=1200)
    broker.place("d1", "S-E1-A", "yes", 0.40, 10, ttl_s=7 * 86400)
    ledger.execute("UPDATE orders SET created_ts=?, expires_ts=?", [now() - 2400, now() - 600])   # lease ran out 10 minutes ago
    assert broker.sync() == 0 and filled(ledger) == 0
    assert ledger.one("SELECT status FROM orders")["status"] == "expired"
    assert broker.renew() == 0                                        # a lapsed order is not revived


def test_a_lease_is_renewed_each_cycle_but_never_past_the_orders_lifetime(ledger):
    broker = ShadowBroker(ledger, Tape([]), lease_s=1200)
    broker.place("d1", "S-E1-A", "yes", 0.40, 10, ttl_s=12 * 3600)
    expires = lambda: ledger.one("SELECT expires_ts FROM orders")["expires_ts"]
    assert abs(expires() - (now() + 1200)) <= 2                       # 20 minutes, not 12 hours
    ledger.execute("UPDATE orders SET expires_ts = expires_ts - 600")   # a cycle later
    assert broker.renew() == 1 and abs(expires() - (now() + 1200)) <= 2
    ledger.execute("UPDATE orders SET expires_ts = expires_ts - 600")
    ledger.set_state(f"deadline:{client_order_id('d1')}", now() + 700)  # the order's own lifetime ends in ~12 minutes
    assert broker.renew() == 1 and abs(expires() - (now() + 700)) <= 2
    assert ShadowBroker(ledger, Tape([])).renew() == 0                # no lease configured: nothing changes

    ShadowBroker(ledger, Tape([])).place("d2", "S-E1-A", "no", 0.55, 10, ttl_s=7 * 86400)   # placed before leases existed
    assert broker.renew() == 1                                        # brought under a lease: 20 minutes, not 7 days
    assert abs(ledger.one("SELECT expires_ts FROM orders WHERE decision_id='d2'")["expires_ts"] - (now() + 1200)) <= 2


# --- risk -------------------------------------------------------------------

def sizing(n, price=0.40):
    from pmbot.blend import Sizing
    return Sizing("yes", price, 0.0, 0.05, 0.08, n)


def test_risk_trims_to_market_cap(ledger, cfg):
    risk = RiskManager(ledger, cfg, "shadow", 1000)
    v = risk.review(sizing(200), "S-E1-A", "S-E1")
    assert v.ok and v.contracts == 75 and "trimmed_market_cap" in v.reasons      # 3% of $1,000 at 40c


def test_risk_enforces_cluster_cap_across_markets(ledger, cfg):
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 200)     # $80 already in event S-E1
    risk = RiskManager(ledger, cfg, "shadow", 1000)
    v = risk.review(sizing(75), "S-E1-B", "S-E1")
    assert v.ok and v.contracts == 50 and "trimmed_cluster_cap" in v.reasons     # $20 of room at 40c


def test_halt_blocks_orders_until_resumed(ledger, cfg):
    risk = RiskManager(ledger, cfg, "shadow", 1000)
    risk.halt("test")
    assert not risk.review(sizing(10), "S-E1-A", "S-E1").ok
    risk.resume()
    assert risk.review(sizing(10), "S-E1-A", "S-E1").ok


def test_drawdown_halts(ledger, cfg):
    ledger.insert("snapshots", {"ticker": "S-E1-A", "ts": now(), "yes_bid": 0.04, "yes_ask": 0.06})
    fill(ledger, "a", "S-E1-A", "yes", 0.50, 500)     # $250 position now marked at 5c
    risk = RiskManager(ledger, cfg, "shadow", 1000)
    assert "drawdown" in (risk.check_account() or "")


def test_positions_are_not_marked_off_a_wide_book(ledger):
    from pmbot.portfolio import mark_price, mark_to_market
    fill(ledger, "a", "S-E1-A", "yes", 0.19, 100)                 # paid $19
    ledger.insert("snapshots", {"ticker": "S-E1-A", "ts": now() - 600, "yes_bid": 0.08, "yes_ask": 0.10})
    assert mark_price(ledger, "S-E1-A") == pytest.approx(0.09)
    # The book thins out overnight: its midpoint (41.5c) is not a price anyone would pay.
    ledger.insert("snapshots", {"ticker": "S-E1-A", "ts": now(), "yes_bid": 0.10, "yes_ask": 0.73})
    assert mark_price(ledger, "S-E1-A") == pytest.approx(0.09)      # still the last tight book
    assert mark_to_market(ledger, account(ledger, "shadow", 1000)) == pytest.approx(1000 - 19 + 9)
    assert mark_price(ledger, "S-E1-B") is None                     # never had a usable book: carried at cost


def test_equity_does_not_shift_when_the_bot_restarts_on_an_exchange(ledger, cfg):
    ledger.insert("snapshots", {"ticker": "S-E1-A", "ts": now(), "yes_bid": 0.39, "yes_ask": 0.41})
    assert RiskManager(ledger, cfg, "shadow", 100, 100).check_account() is None      # day opens at $100
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 50)                                     # $20 of cash becomes a $20 position
    # After a restart the exchange reports $80 of cash. The $20 the ledger's fills explain is added back.
    start_cash = 80 - account(ledger, "shadow", 0.0).cash
    assert start_cash == pytest.approx(100)
    assert RiskManager(ledger, cfg, "shadow", 80, start_cash).check_account() is None
    # Measured from the balance at restart, the same account looks $20 poorer and halts.
    assert "daily loss" in (RiskManager(ledger, cfg, "shadow", 80).check_account() or "")


def test_bankroll_on_an_exchange_counts_open_positions_not_just_idle_cash(ledger, cfg):
    from pmbot.runner import exchange_basis
    assert exchange_basis(ledger, "shadow", 100.0) == (100.0, 100.0)
    fill(ledger, "a", "S-E1-A", "yes", 0.40, 50)              # $20 of the $100 becomes a position
    bankroll, start_cash = exchange_basis(ledger, "shadow", 80.0)
    assert (bankroll, start_cash) == (pytest.approx(100.0), pytest.approx(100.0))   # limits still scale to $100, not $80


def test_config_overlay_changes_only_what_it_names():
    demo, base = config.load("config/demo.yaml"), config.load("config/settings.yaml")
    assert demo.mode == "demo" and base.mode == "shadow"
    assert demo.lp.contracts_per_side == 10 and demo.lp.min_hours_to_close == base.lp.min_hours_to_close
    assert demo.risk.max_drawdown == base.risk.max_drawdown
    assert "synthetic_programs" not in base.lp
