"""Liquidity Incentive Program scoring, checked against the rules in Kalshi's CFTC filing."""

import pytest

from pmbot import config, lp
from pmbot.catalog import Quote

TARGET, DISCOUNT, TICK = 1000, 0.5, 0.01
YES = [(0.40, 100), (0.39, 150), (0.38, 800), (0.37, 500)]


def quote(**kw) -> Quote:
    base = dict(ticker="T-1", event_ticker="T", series_ticker="S", category="Economics", fee_type="quadratic",
                fee_multiplier=1.0, title="", yes_sub_title="", mutually_exclusive=False, n_event_markets=1,
                yes_bid=0.40, yes_ask=0.45, yes_bid_size=100, yes_ask_size=100, last_price=0.42, volume=0,
                volume_24h=0, open_interest=0, open_ts=0, close_ts=10**10, expected_expiration_ts=None,
                can_close_early=False, rules="", price_ranges=[(0.0, 1.0, 0.01)], previous_price=0.42)
    return Quote(**{**base, **kw})


def program(**kw) -> lp.Program:
    return lp.Program(**{**dict(ticker="T-1", series_ticker="S", reward_day=100.0, target=TARGET, discount=DISCOUNT,
                                start_ts=0, end_ts=10**10), **kw})


def test_whole_levels_qualify_until_target_and_reference_is_at_one_fifth():
    s = lp.score_side(YES, TARGET, DISCOUNT, TICK)
    assert s.qualifies and s.ref == 0.39          # cumulative 100, then 250 >= 200
    # 0.40 and 0.39 score 1.0x; 0.38 is one tick below the reference; 0.37 is past the target.
    assert s.score == pytest.approx(100 + 150 + 800 * 0.5)


def test_side_below_target_does_not_qualify():
    assert not lp.score_side([(0.40, 600), (0.39, 300)], TARGET, DISCOUNT, TICK).qualifies


def test_with_order_joins_or_creates_a_level():
    assert lp.with_order(YES, 0.39, 50)[1] == (0.39, 200)
    assert lp.with_order(YES, 0.41, 50)[0] == (0.41, 50)
    assert lp.with_order(YES, 0.385, 50)[2] == (0.385, 50)
    assert lp.with_order(YES, 0.30, 50)[-1] == (0.30, 50)


def test_share_at_reference_counts_in_full():
    assert lp.my_share(YES, TARGET, DISCOUNT, TICK, 0.39, 50, already_in_book=False) == pytest.approx(50 / 700)


def test_share_is_discounted_below_reference_and_zero_beyond_target():
    one_below = lp.my_share(YES, TARGET, DISCOUNT, TICK, 0.38, 50, already_in_book=False)
    assert one_below == pytest.approx(50 * 0.5 / (100 + 150 + 850 * 0.5))
    assert lp.my_share(YES, TARGET, DISCOUNT, TICK, 0.37, 50, already_in_book=False) == 0.0


def test_live_book_already_contains_our_order():
    book = lp.with_order(YES, 0.39, 50)
    assert lp.my_share(book, TARGET, DISCOUNT, TICK, 0.39, 50, already_in_book=True) == pytest.approx(50 / 700)


def test_big_order_at_the_touch_moves_the_reference_up():
    # 250 contracts at a new best price reach one fifth of target by themselves.
    assert lp.score_side(lp.with_order(YES, 0.41, 250), TARGET, DISCOUNT, TICK).ref == 0.41


def test_plan_quotes_both_sides_at_reference_and_splits_the_pool():
    no = [(0.55, 300), (0.54, 900)]
    cfg = config.load("config/settings.yaml")
    quotes = lp.plan_market(program(), quote(), (YES, no), 50, cfg.lp, now=0)
    by_side = {q.side: q for q in quotes}
    assert by_side["yes"].price == 0.39 and by_side["no"].price == 0.55
    # Each side is worth half the pool: $100/day x share / 2.
    assert by_side["yes"].reward_day == pytest.approx(100 * (50 / 700) / 2)
    assert by_side["no"].reward_day == pytest.approx(100 * (50 / (350 + 900 * 0.5)) / 2)
    assert by_side["yes"].at_risk == pytest.approx(0.39 * 50)
    assert by_side["yes"].queue_ahead == 150


def test_no_reward_when_either_side_is_short_of_target():
    cfg = config.load("config/settings.yaml")
    assert lp.plan_market(program(), quote(), (YES, [(0.55, 300)]), 50, cfg.lp, now=0) == []


def test_never_quote_a_price_that_would_cross():
    cfg = config.load("config/settings.yaml")
    no = [(0.61, 300), (0.60, 900)]          # NO bid 0.61 = YES ask 0.39: locked against our 0.39 reference
    sides = {q.side for q in lp.plan_market(program(), quote(), (YES, no), 50, cfg.lp, now=0)}
    assert "yes" not in sides


def test_eligibility_filters():
    cfg = config.load("config/settings.yaml")
    now = 1_000_000
    far = now + 30 * 86400
    ok = quote(close_ts=far)
    assert lp.market_reasons(program(end_ts=far), ok, cfg.lp, now) == []
    assert "closes_too_soon" in lp.market_reasons(program(end_ts=far), quote(close_ts=now + 3600), cfg.lp, now)
    assert "other_exchange_shard" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, exchange_index=2), cfg.lp, now)
    # Open for another week, but the number that decides it is published in 20 hours.
    deciding = quote(close_ts=now + 7 * 86400, expected_expiration_ts=now + 20 * 3600)
    assert "closes_too_soon" in lp.market_reasons(program(end_ts=far), deciding, cfg.lp, now)
    assert "price_moving" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, previous_price=0.60), cfg.lp, now)
    assert "category_excluded" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, category="Sports"), cfg.lp, now)
    assert "program_ending" in lp.market_reasons(program(end_ts=now + 3600), ok, cfg.lp, now)
    assert lp.market_reasons(program(end_ts=now + 3600), ok, cfg.lp, now, committed=True) == []   # already there: see it out
    assert "maker_fee_series" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, fee_type="quadratic_with_maker_fees"), cfg.lp, now)


def test_cheap_bids_need_more_reward_than_bids_on_the_favourite():
    cfg = config.load("config/settings.yaml")
    cheap = lp.SideQuote("T-1", "yes", 0.06, 50, 0.1, 0.09, 3.0, 0)       # 3%/day gross
    rich = lp.SideQuote("T-1", "no", 0.92, 30, 0.1, 0.276, 27.6, 0)       # 1%/day gross
    fill = cfg.lp.fill_prob_day
    assert cheap.net_yield_day(cfg.lp) == pytest.approx(0.03 + fill * -0.45)   # negative after expected fills
    assert rich.net_yield_day(cfg.lp) == pytest.approx(0.01 + fill * 0.02)
    assert rich.net_yield_day(cfg.lp) > cfg.lp.min_yield_day > cheap.net_yield_day(cfg.lp)


def test_market_is_left_alone_after_the_exchange_refuses_an_order():
    import copy

    from pmbot.execution.brokers import ShadowBroker
    from pmbot.ledger.db import Ledger, now
    from pmbot.lp_runner import LiquidityProvider
    from pmbot.risk import RiskManager
    from test_core import Tape

    cfg = config.Config(copy.deepcopy(dict(config.load("config/settings.yaml"))))
    ledger = Ledger(":memory:")
    provider = LiquidityProvider(cfg, ledger, object(), ShadowBroker(ledger, Tape([])), RiskManager(ledger, cfg, "shadow", 1000.0), "shadow")
    args = ({"T-1": program()}, {"T-1": quote()}, {"T-1": (YES, [(0.55, 300), (0.54, 900)])}, 0.0)

    ledger.insert("orders", {"client_order_id": "pm-x", "ticker": "T-1", "side": "yes", "price": 0.39, "contracts": 50,
                             "mode": "shadow", "status": "rejected", "created_ts": now() - 3600})
    assert provider.place(*args) == 0            # refused an hour ago: still cooling off
    ledger.execute("UPDATE orders SET created_ts=? WHERE client_order_id='pm-x'", [now() - 7 * 3600])
    assert provider.place(*args) == 2            # seven hours ago: quoted again, both sides


def test_cancel_reasons_are_counted_for_the_cycle_log():
    import copy

    from pmbot.execution.brokers import ShadowBroker
    from pmbot.ledger.db import Ledger
    from pmbot.lp_runner import LiquidityProvider
    from pmbot.risk import RiskManager
    from test_core import Tape

    cfg = config.Config(copy.deepcopy(dict(config.load("config/settings.yaml"))))
    ledger = Ledger(":memory:")
    provider = LiquidityProvider(cfg, ledger, object(), ShadowBroker(ledger, Tape([])), RiskManager(ledger, cfg, "shadow", 1000.0), "shadow")
    programs, quotes, no = {"T-1": program()}, {"T-1": quote()}, [(0.55, 300), (0.54, 900)]
    assert provider.place(programs, quotes, {"T-1": (YES, no)}, 0.0) == 2        # yes at 0.39, no at 0.55
    # More size at 0.40 lifts the YES reference one tick above our bid: kept, scoring at the discount.
    nudged = [(0.40, 300)] + YES[1:]
    assert provider.prune(provider.my_orders(), programs, quotes, {"T-1": (nudged, no)}, 0.0) == 0
    # New size at 0.41 lifts the YES reference two ticks above our bid; the NO side is unchanged.
    moved = [(0.41, 300)] + YES
    assert provider.prune(provider.my_orders(), programs, quotes, {"T-1": (moved, no)}, 0.0) == 1
    assert dict(provider.cancel_reasons) == {"reference_moved": 1}


# --- staying in a program until it pays ---------------------------------------

def sticky_provider(**lp_over):
    import copy

    from pmbot.execution.brokers import ShadowBroker
    from pmbot.ledger.db import Ledger
    from pmbot.lp_runner import LiquidityProvider
    from pmbot.risk import RiskManager
    from test_core import Tape

    raw = copy.deepcopy(dict(config.load("config/settings.yaml")))
    raw["lp"].update(lp_over)
    cfg, ledger = config.Config(raw), Ledger(":memory:")
    return LiquidityProvider(cfg, ledger, object(), ShadowBroker(ledger, Tape([])), RiskManager(ledger, cfg, "shadow", 1000.0), "shadow"), ledger


NO = [(0.55, 300), (0.54, 900)]


def test_a_program_too_small_to_pay_is_quoted_only_if_earnings_there_already_close_the_gap():
    cfg, now = config.load("config/settings.yaml"), 1_000_000
    small = {"T-1": program(reward_day=10.0, end_ts=now + 86400)}      # a 50-contract quote earns about 36c in its last day
    args = (small, {"T-1": quote()}, {"T-1": (YES, NO)}, cfg.lp, 1000.0, now)
    assert lp.rank(*args) == []                                         # under the $1 floor: resting there earns nothing
    assert [s.side for s in lp.rank(*args, accrued={"T-1": 1.30})] == ["no"]   # the cheap YES bid still fails on fill cost


def test_a_market_quoted_this_period_keeps_its_slot_when_its_quotes_are_pulled():
    provider, ledger = sticky_provider(max_quotes=2)
    only_t2 = {"T-2": program(ticker="T-2", reward_day=50.0)}
    quotes = {"T-1": quote(), "T-2": quote(ticker="T-2")}
    books = {"T-1": (YES, NO), "T-2": (YES, NO)}
    assert provider.place(only_t2, quotes, books, 0.0) == 2             # the bot starts in T-2
    for o in provider.my_orders():
        provider.broker.cancel(o["client_order_id"], "reference_moved")  # its reference moves and both quotes are pulled
    both = {**only_t2, "T-1": program()}                                 # T-1 now pays twice as much
    assert provider.committed(both) == {"T-2"}
    assert provider.place(both, quotes, books, 0.0) == 2
    resting = ledger.query("SELECT ticker FROM orders WHERE status='resting'")
    assert {r["ticker"] for r in resting} == {"T-2"}                    # back into T-2, not off to the better-ranked T-1


def test_a_committed_market_only_has_to_reach_the_floor_itself():
    cfg, now = config.load("config/settings.yaml"), 1_000_000
    small = {"T-1": program(reward_day=10.0, end_ts=now + 86400)}       # a quote there adds about 36c by the end
    args = (small, {"T-1": quote()}, {"T-1": (YES, NO)}, cfg.lp, 1000.0, now)
    assert lp.rank(*args, accrued={"T-1": 0.80}) == []                  # new market: 1.16 is under the 1.50 margin
    assert [s.side for s in lp.rank(*args, accrued={"T-1": 0.80}, committed={"T-1"})] == ["no"]   # already there: 1.16 clears $1


def test_a_quote_that_can_no_longer_reach_the_payout_floor_is_pulled():
    provider, ledger = sticky_provider()
    programs, quotes = {"T-1": program()}, {"T-1": quote()}
    assert provider.place(programs, quotes, {"T-1": (YES, NO)}, 0.0) == 2
    fading = {"T-1": program(reward_day=10.0, end_ts=86400)}            # the pool shrank: about 36c a side by the end
    assert provider.prune(provider.my_orders(), fading, quotes, {"T-1": (YES, NO)}, 0.0) == 2
    # The NO bid would still cover its fill cost, but the program cannot pay; the YES bid fails on fill cost first.
    assert dict(provider.cancel_reasons) == {"cannot_reach_payout": 1, "yield_below_fill_cost": 1}


def test_estimated_rewards_are_split_by_whether_the_program_would_pay():
    import time

    from pmbot.ledger.db import Ledger
    from pmbot.score import rewards_by_program

    ledger, now = Ledger(":memory:"), int(time.time())
    periods = {"PAID": (now - 3 * 86400, now - 86400), "SMALL": (now - 3 * 86400, now - 86400), "RUNNING": (now - 86400, now + 86400)}
    for ticker, (start, end) in periods.items():
        ledger.insert("lp_programs", {"mode": "shadow", "ticker": ticker, "start_ts": start, "end_ts": end, "reward_day": 5.0})
    for ticker, usd, ts in (("PAID", 0.7, now - 2 * 86400), ("PAID", 0.6, now - 2 * 86400 + 60), ("SMALL", 0.4, now - 2 * 86400),
                            ("RUNNING", 0.3, now - 3600), ("OLD", 0.2, now - 3600)):
        ledger.insert("lp_accruals", {"ts": ts, "mode": "shadow", "ticker": ticker, "side": "yes", "seconds": 60, "share": 0.1, "usd": usd})
    r = rewards_by_program(ledger, "shadow")
    assert (r["payable_ended"], r["forfeited_ended"], r["running_below_floor"], r["untracked"]) == (1.3, 0.4, 0.3, 0.2)
    assert (r["programs_ended"], r["programs_ended_paying"], r["programs_running"]) == (2, 1, 1)


def test_live_quotes_use_the_whole_per_quote_cap_on_cheap_contracts():
    """A program pays nothing under $1, so at live size a quote should put its full $5 to work."""
    now = 1_000_000
    cheap = quote(yes_bid=0.02, yes_ask=0.05, last_price=0.03, previous_price=0.03)
    books = {"T-1": ([(0.02, 600), (0.01, 900)], [(0.95, 400), (0.94, 900)])}
    live, paper = config.load("config/live.yaml").lp, config.load("config/settings.yaml").lp

    [yes] = [s for s in lp.rank({"T-1": program()}, {"T-1": cheap}, books, live, 100.0, now) if s.side == "yes"]
    assert (yes.contracts, yes.at_risk) == (250, pytest.approx(5.0))          # was 50 contracts, $1 at risk
    [small] = [s for s in lp.rank({"T-1": program()}, {"T-1": cheap}, books, paper, 100.0, now) if s.side == "yes"]
    assert small.contracts == 50 and yes.reward_day > 3 * small.reward_day    # the larger quote earns its program's dollar sooner
    assert not [s for s in lp.rank({"T-1": program()}, {"T-1": cheap}, books, live, 100.0, now) if s.side == "no"]   # 95c side: 5 contracts, under the minimum

    dearer = quote(yes_bid=0.18, yes_ask=0.22, last_price=0.20, previous_price=0.20)
    books = {"T-1": ([(0.18, 600), (0.17, 900)], [(0.78, 400), (0.77, 900)])}
    [yes] = [s for s in lp.rank({"T-1": program()}, {"T-1": dearer}, books, live, 100.0, now) if s.side == "yes"]
    assert (yes.contracts, yes.at_risk) == (27, pytest.approx(4.86))          # still cut down to the $5 cap


def test_a_committed_quote_stays_through_the_programs_last_hours():
    """Pulled 6 hours early at $0.86, a program forfeits what it earned; held, it pays."""
    provider, ledger = sticky_provider()
    quotes, books = {"T-1": quote(), "T-2": quote(ticker="T-2")}, {"T-1": (YES, NO), "T-2": (YES, NO)}
    assert provider.place({"T-1": program(end_ts=5 * 86400)}, quotes, books, 0.0) == 2
    ending = {"T-1": program(end_ts=3 * 3600), "T-2": program(ticker="T-2", end_ts=3 * 3600)}   # three hours left in both
    import time
    ledger.insert_many("lp_accruals", [{"ts": int(time.time()), "mode": "shadow", "ticker": "T-1", "side": "yes", "client_order_id": "x",
                                        "seconds": 1.0, "share": 0.1, "usd": 0.90}])
    provider.earned = provider.accrued(ending)
    assert provider.prune(provider.my_orders(), ending, quotes, books, 0.0) == 0          # not pulled as `program_ending`
    for o in provider.my_orders():
        provider.broker.cancel(o["client_order_id"], "reference_moved")                    # a requote in the last hours
    assert provider.place(ending, quotes, books, 0.0) == 2                                # comes back to T-1
    assert {r["ticker"] for r in ledger.query("SELECT ticker FROM orders WHERE status='resting'")} == {"T-1"}   # T-2 is new: kept out
