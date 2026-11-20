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
    # Open for another week, but the number that decides it is published in 20 hours.
    deciding = quote(close_ts=now + 7 * 86400, expected_expiration_ts=now + 20 * 3600)
    assert "closes_too_soon" in lp.market_reasons(program(end_ts=far), deciding, cfg.lp, now)
    assert "price_moving" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, previous_price=0.60), cfg.lp, now)
    assert "category_excluded" in lp.market_reasons(program(end_ts=far), quote(close_ts=far, category="Sports"), cfg.lp, now)
    assert "program_ending" in lp.market_reasons(program(end_ts=now + 3600), ok, cfg.lp, now)
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
