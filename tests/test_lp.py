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
    # Each cancel is recorded with its reason and the numbers behind it.
    [row] = ledger.query("SELECT side, price, reason, detail FROM lp_cancels")
    assert (row["side"], row["price"], row["reason"]) == ("yes", 0.39, "reference_moved")
    assert __import__("json").loads(row["detail"])["ref"] == 0.41


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
    provider.risk.bankroll = 2000.0                                     # room in one market for both sides at full size
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


def two_markets_whose_yes_reference_just_moved(**lp_over):
    provider, ledger = sticky_provider(**lp_over)
    provider.risk.bankroll = 4000.0
    programs = {t: program(ticker=t) for t in ("T-1", "T-2")}
    quotes = {"T-1": quote(), "T-2": quote(ticker="T-2")}
    assert provider.place(programs, quotes, {t: (YES, NO) for t in programs}, 0.0) == 4
    books = {t: ([(0.41, 300)] + YES, NO) for t in programs}
    assert provider.prune(provider.my_orders(), programs, quotes, books, 0.0) == 2
    assert dict(provider.cancel_reasons) == {"reference_moved": 2}
    return provider, programs, quotes, books


def test_a_moved_quote_that_finds_no_room_left_is_reported_as_such():
    provider, programs, quotes, books = two_markets_whose_yes_reference_just_moved()
    provider.c = config.Config({**dict(provider.c), "max_quotes": 2})
    assert provider.place(programs, quotes, books, 0.0) == 0
    assert dict(provider.moved_not_requoted) == {"no_room": 2}


def test_a_moved_quote_that_is_not_worth_quoting_at_its_new_price_is_reported_as_such():
    provider, programs, quotes, books = two_markets_whose_yes_reference_just_moved()
    programs["T-1"] = program(reward_day=0.001)
    assert provider.place(programs, quotes, books, 0.0) == 1
    assert dict(provider.moved_not_requoted) == {"does_not_qualify": 1}


def test_a_moved_quote_that_is_placed_again_is_not_reported():
    provider, programs, quotes, books = two_markets_whose_yes_reference_just_moved()
    assert provider.place(programs, quotes, books, 0.0) == 2
    assert dict(provider.moved_not_requoted) == {}


def test_a_moved_quote_keeps_the_room_it_freed_ahead_of_a_program_with_more_at_stake():
    provider, ledger = sticky_provider(fill_prob_day=0.0)
    provider.risk.bankroll = 4000.0
    programs = {t: program(ticker=t) for t in ("T-1", "T-2")}
    quotes = {"T-1": quote(), "T-2": quote(ticker="T-2")}
    assert provider.place(programs, quotes, {t: (YES, NO) for t in programs}, 0.0) == 4
    for o in provider.my_orders():
        if o["ticker"] == "T-2":
            provider.broker.cancel(o["client_order_id"], "yield_below_fill_cost")
    provider.c = config.Config({**dict(provider.c), "max_quotes": 2})
    provider.earned = {"T-1": 1.30, "T-2": 0.83}
    books = {t: ([(0.41, 300)] + YES, NO) for t in programs}
    assert provider.prune(provider.my_orders(), programs, quotes, books, 0.0) == 1
    assert provider.place(programs, quotes, books, 0.0) == 1
    assert {o["ticker"] for o in provider.my_orders()} == {"T-1"}
    assert dict(provider.moved_not_requoted) == {}


def test_room_goes_first_to_the_program_with_rewards_still_at_stake():
    """With room for one market, a program at $0.83 comes back before one already past $1."""
    provider, ledger = sticky_provider(max_quotes=4, fill_prob_day=0.0)      # no fill cost: this is about ordering only
    provider.risk.bankroll = 4000.0
    programs = {t: program(ticker=t, reward_day=40.0, end_ts=2 * 86400) for t in ("T-1", "T-2")}
    quotes = {"T-1": quote(), "T-2": quote(ticker="T-2")}
    books = {"T-1": (YES, NO), "T-2": (YES, NO)}
    assert provider.place(programs, quotes, books, 0.0) == 4
    # The pools shrink to the twin's size: each quote would earn well under a dollar in the two days left.
    programs = {t: program(ticker=t, reward_day=10.0, end_ts=2 * 86400) for t in ("T-1", "T-2")}
    for o in provider.my_orders():
        provider.broker.cancel(o["client_order_id"], "reference_moved")      # both markets' quotes are pulled to be moved
    provider.c = config.Config({**dict(provider.c), "max_quotes": 2})        # and there is room for one market only
    provider.earned = {"T-1": 1.30, "T-2": 0.83}
    assert provider.place(programs, quotes, books, 0.0) == 2
    assert {o["ticker"] for o in provider.my_orders()} == {"T-2"}            # was T-1: the larger sum banked, none of it at risk


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


# --- changing settings while the bot runs ---------------------------------------

def test_a_setting_changed_at_run_time_applies_on_the_next_step_and_can_be_undone():
    from pmbot import overrides

    provider, ledger = sticky_provider()
    base = provider.base
    assert overrides.effective(base, ledger, "shadow").requote_ticks == base["requote_ticks"]
    assert overrides.put(ledger, "shadow", base, "lp.requote_ticks", 5, "test") == base["requote_ticks"]
    assert overrides.effective(base, ledger, "shadow").requote_ticks == 5
    assert provider.c.requote_ticks == base["requote_ticks"]           # not yet: the bot picks it up at its next step
    provider.data = type("NoPrograms", (), {"get": lambda *a, **k: {"incentive_programs": []}, "paginate": lambda *a, **k: iter(())})()
    provider.programs = lambda: {"T-1": program()}                      # skip the exchange; the step still re-reads settings
    lp.fetch_books, saved = (lambda data, tickers: {}), lp.fetch_books
    try:
        stats = provider.step({"T-1": quote()})
    finally:
        lp.fetch_books = saved
    assert provider.c.requote_ticks == 5 and stats["lp_settings_changed_at_run_time"] == ["requote_ticks"]
    assert [r["kind"] for r in ledger.query("SELECT kind FROM risk_events")] == ["setting_changed"]   # logged with its reason

    assert overrides.drop(ledger, "shadow", base, "requote_ticks") is True
    assert overrides.effective(base, ledger, "shadow").requote_ticks == base["requote_ticks"]


def test_hard_limits_and_wrong_values_are_refused_at_run_time():
    from pmbot import overrides

    provider, ledger = sticky_provider()
    for setting, value in (("lp.max_at_risk_per_quote", 50.0),        # Rohan's limit
                           ("lp.capital_fraction", 0.9),              # Rohan's limit
                           ("risk.max_drawdown", 0.9),                # not a reward-strategy setting at all
                           ("lp.requote_ticks", "many"),              # wrong kind of value
                           ("lp.no_such_setting", 1)):
        with pytest.raises(ValueError):
            overrides.put(ledger, "shadow", provider.base, setting, value)
    assert overrides.load(ledger, "shadow") == {} and ledger.query("SELECT 1 FROM risk_events") == []


def test_pausing_a_family_pulls_its_quotes_and_keeps_it_out():
    from pmbot import overrides

    provider, ledger = sticky_provider()
    programs = {"GAS-AK-1": program(ticker="GAS-AK-1"), "RAIN-NY-1": program(ticker="RAIN-NY-1")}
    quotes = {t: quote(ticker=t) for t in programs}
    books = {t: (YES, NO) for t in programs}
    assert provider.place(programs, quotes, books, 0.0) == 4
    assert overrides.pause(ledger, "shadow", provider.base, "GAS", "answer is published on a schedule") == ["GAS"]
    provider.c = overrides.effective(provider.base, ledger, "shadow")   # what the next step does
    assert provider.prune(provider.my_orders(), programs, quotes, books, 0.0) == 2
    assert dict(provider.cancel_reasons) == {"family_paused": 2}
    assert provider.place(programs, quotes, books, 0.0) == 0            # and it does not come back
    assert {o["ticker"] for o in provider.my_orders()} == {"RAIN-NY-1"}
    assert overrides.unpause(ledger, "shadow", provider.base, "GAS") == []
    provider.c = overrides.effective(provider.base, ledger, "shadow")
    assert provider.place(programs, quotes, books, 0.0) == 2


def test_a_family_gets_only_a_few_markets():
    """Seventeen gas-price markets filled on one piece of news; a family is capped, held positions included."""
    provider, ledger = sticky_provider(max_markets_per_family=2, family_prefix_len=5)
    tickers = ["KXGASAK-1", "KXGASTX-1", "KXGASNY-1", "KXRAINNY-1"]
    programs = {t: program(ticker=t) for t in tickers}
    quotes, books = {t: quote(ticker=t) for t in tickers}, {t: (YES, NO) for t in tickers}
    provider.place(programs, quotes, books, 0.0)
    quoted = {o["ticker"] for o in provider.my_orders()}
    assert len({t for t in quoted if t.startswith("KXGAS")}) == 2 and "KXRAINNY-1" in quoted   # two gas markets, both sides each
    assert len(provider.my_orders()) == 6


def test_a_program_with_rewards_banked_is_not_left_just_because_yield_dipped():
    """Leaving at $0.90 forfeits the $0.90. Staying is worth it while the expected fill cost to the end is smaller."""
    provider, ledger = sticky_provider(keep_committed_while_accrued=True)
    quotes, books = {"T-1": quote()}, {"T-1": (YES, NO)}
    assert provider.place({"T-1": program()}, quotes, books, 0.0) == 2
    # The pool shrinks: the YES bid now earns less than its expected fill cost, with two days of the period left.
    thin = {"T-1": program(reward_day=15.0, end_ts=2 * 86400)}
    yes = next(o for o in provider.my_orders() if o["side"] == "yes")
    at_risk = yes["price"] * yes["remaining"]
    share = lp.my_share(YES, TARGET, DISCOUNT, TICK, yes["price"], yes["remaining"], False)
    net = 15.0 * share / 2 / at_risk + provider.c.fill_prob_day * lp.fill_return(yes["price"], provider.c)
    assert net < 0                                                       # so the plain rule would pull it
    assert -net * at_risk * 2.0 < 0.45                                   # staying two days is expected to cost under 45c

    assert lp.worth_staying(1.60, net, at_risk, 2.0, provider.c) is False   # past $1 nothing is forfeited: plain rule
    provider.earned = {"T-1": 0.90}                                      # 45c a side at stake, and on course for $1
    provider.prune(provider.my_orders(), thin, quotes, books, 0.0)
    assert "yield_below_fill_cost" not in provider.cancel_reasons        # kept: leaving would forfeit more than staying costs

    off, _ = sticky_provider()                                           # the setting is off by default
    assert off.place({"T-1": program()}, quotes, books, 0.0) == 2
    off.earned = {"T-1": 0.90}
    off.prune(off.my_orders(), thin, quotes, books, 0.0)
    assert off.cancel_reasons["yield_below_fill_cost"] >= 1


def test_a_quote_the_risk_limits_cut_down_is_placed_only_if_the_part_still_earns_its_payout():
    """The twin placed 1-contract orders beside a full position, pulled them minutes later and placed them again."""
    quotes, books, now = {"T-1": quote()}, {"T-1": (YES, NO)}, 1_000_000.0
    [full] = [s for s in lp.rank({"T-1": program()}, quotes, books, config.load("config/settings.yaml").lp, 1000.0, now)
              if s.side == "yes"]
    assert full.contracts == 50

    provider, _ = sticky_provider()
    provider.risk.bankroll = 70.0                 # the per-market cap (3%) leaves room for 5 contracts, under the minimum of 10
    assert provider.place({"T-1": program()}, quotes, books, now) == 0 and provider.my_orders() == []
    assert provider.trimmed_away >= 1

    # Room for 30 of the 50 contracts. With one day left, the program pays $1.50 to the whole quote but not to the part.
    part = lp.resized(full, 30, program(), quotes["T-1"], books["T-1"])
    assert part.reward_day < full.reward_day
    pays_whole_only = 100.0 * 1.5 / full.reward_day * 1.02
    for reward_day, placed in ((pays_whole_only, []), (3 * pays_whole_only, [30])):
        provider, _ = sticky_provider()
        provider.risk.bankroll = 400.0
        provider.place({"T-1": program(reward_day=reward_day, end_ts=now + 86400)}, quotes, books, now)
        assert [o["remaining"] for o in provider.my_orders() if o["side"] == "yes"] == placed


def filled_yes_position(**lp_over):
    """A provider holding 50 YES at 39c in T-1 with nothing resting: its bid filled, the other side was pulled."""
    from pmbot.ledger.db import new_id
    provider, ledger = sticky_provider(**lp_over)
    provider.risk.bankroll = 2000.0
    quotes, books = {"T-1": quote()}, {"T-1": (YES, NO)}
    assert provider.place({"T-1": program()}, quotes, books, 0.0) == 2
    for o in provider.my_orders():
        if o["side"] == "no":
            provider.broker.cancel(o["client_order_id"], "test")
            continue
        ledger.insert("fills", {"id": new_id(), "client_order_id": o["client_order_id"], "ticker": "T-1", "side": "yes",
                                "price": o["price"], "contracts": o["remaining"], "fee": 0.0, "ts": 1, "simulated": True})
        ledger.execute("UPDATE orders SET status='filled' WHERE client_order_id=?", [o["client_order_id"]])
    assert provider.my_orders() == [] and provider.exposure()[1] == {("T-1", "yes"): 50}
    return provider, ledger, quotes, books


def test_a_filled_position_is_offered_out_on_the_other_side_with_nothing_new_at_risk():
    """The twin's fills tied up $22 of its $60 until settlement; an offer on them earns rewards and frees it."""
    from pmbot.ledger.db import new_id
    from pmbot.portfolio import positions

    off, _, quotes, books = filled_yes_position()                          # the setting is off by default
    off.place({"T-1": program()}, quotes, books, 0.0)
    assert [o for o in off.my_orders() if o["kind"] == "lp_close"] == []

    provider, ledger, quotes, books = filled_yes_position(offer_out_positions=True)
    held_cost = provider.exposure()[0]
    assert held_cost == pytest.approx(50 * 0.39)
    provider.place({"T-1": program()}, quotes, books, 0.0)
    [offer] = provider.my_orders()                                         # no second YES bid: the position is full
    # A NO bid at its reference for exactly the 50 contracts held: selling the YES at 45c.
    assert (offer["kind"], offer["side"], offer["price"], offer["remaining"]) == ("lp_close", "no", 0.55, 50)
    assert provider.exposure()[0] == pytest.approx(held_cost)              # the offer adds nothing to dollars at risk
    assert provider.risk.review(lp_runner_sizing("yes", 0.39, 10), "T-9", "E-9").ok   # nor does it use up cash or caps
    # It is not judged on yield or the payout floor: a thin program does not pull it.
    assert provider.prune(provider.my_orders(), {"T-1": program(reward_day=0.01, end_ts=3600)}, quotes, books, 0.0) == 0

    ledger.insert("fills", {"id": new_id(), "client_order_id": offer["client_order_id"], "ticker": "T-1", "side": "no",
                            "price": 0.55, "contracts": 50, "fee": 0.0, "ts": 2, "simulated": True})
    ledger.execute("UPDATE orders SET status='filled' WHERE client_order_id=?", [offer["client_order_id"]])
    [p] = positions(ledger, "shadow")
    assert p.contracts == 0 and p.paired_gain == pytest.approx(50 - 50 * 0.39 - 50 * 0.55)
    assert provider.exposure()[0] == 0 and provider.exposure()[1] == {}    # the budget is free again


def test_the_reward_budget_counts_a_position_bought_again_at_what_was_paid_for_it():
    from pmbot.execution.brokers import client_order_id
    from pmbot.ledger.db import new_id

    provider, ledger, _, _ = filled_yes_position()
    for side, price in (("no", 0.55), ("yes", 0.90)):
        decision = new_id()
        provider.broker.place(decision, "T-1", side, price, 50, 3600)
        ledger.insert("fills", {"id": new_id(), "client_order_id": client_order_id(decision), "ticker": "T-1", "side": side,
                                "price": price, "contracts": 50, "fee": 0.0, "ts": 2, "simulated": True})
        ledger.execute("UPDATE orders SET status='filled' WHERE client_order_id=?", [client_order_id(decision)])
    assert provider.exposure()[0] == pytest.approx(50 * 0.90)


def test_an_offer_never_outlives_the_position_it_closes():
    """Left resting after its position is gone, a 50-contract NO bid at 55c would open a position no cap checked."""
    provider, ledger, quotes, books = filled_yes_position(offer_out_positions=True)
    provider.place({"T-1": program()}, quotes, books, 0.0)
    ledger.insert("markets", {"ticker": "T-1", "result": "no", "status": "finalized"})   # the market settles
    assert provider.prune(provider.my_orders(), {"T-1": program()}, quotes, books, 0.0) == 1
    assert dict(provider.cancel_reasons) == {"position_gone": 1}

    provider, ledger, quotes, books = filled_yes_position(offer_out_positions=True)
    provider.place({"T-1": program()}, quotes, books, 0.0)
    provider.c = config.Config({**dict(provider.c), "offer_out_positions": False})        # switched off at run time
    assert provider.prune(provider.my_orders(), {"T-1": program()}, quotes, books, 0.0) == 1
    assert dict(provider.cancel_reasons) == {"offers_switched_off": 1}


def lp_runner_sizing(side, price, contracts):
    from pmbot.blend import Sizing
    return Sizing(side, price, 0.0, 0.0, 0.0, contracts)


def test_a_quote_must_qualify_several_cycles_running_before_it_is_first_placed():
    """One placement in five was pulled a cycle later: the market had only looked good for one reading of the book."""
    provider, ledger = sticky_provider(enter_after_cycles=2)
    provider.risk.bankroll = 2000.0
    programs, quotes, books = {"T-1": program()}, {"T-1": quote()}, {"T-1": (YES, NO)}
    assert provider.place(programs, quotes, books, 0.0) == 0             # first sighting
    assert provider.place({}, quotes, books, 0.0) == 0                   # gone from the ranking: the count starts again
    assert provider.place(programs, quotes, books, 0.0) == 0
    assert provider.place(programs, quotes, books, 0.0) == 2             # two cycles running

    # A quote pulled to follow its price is placed again at once, in the same step.
    moved = [(0.41, 300)] + YES                                          # the YES reference is now two ticks above our bid
    assert provider.prune(provider.my_orders(), programs, quotes, {"T-1": (moved, NO)}, 0.0) == 1
    fresh = sticky_provider(enter_after_cycles=2)[0]                     # the same book seen by a bot with no history
    assert fresh.place(programs, quotes, {"T-1": (moved, NO)}, 0.0) == 0
    assert provider.place(programs, quotes, {"T-1": (moved, NO)}, 0.0) == 1
    assert sorted((o["side"], o["price"]) for o in provider.my_orders()) == [("no", 0.55), ("yes", 0.41)]


def test_bids_below_the_minimum_price_are_neither_placed_nor_kept():
    """A 1c bid is only filled by someone unloading a nearly worthless contract."""
    cheap = quote(yes_bid=0.02, yes_ask=0.05, last_price=0.03, previous_price=0.03)
    books = {"T-1": ([(0.02, 600), (0.01, 900)], [(0.95, 400), (0.94, 900)])}
    provider, ledger = sticky_provider()
    assert provider.place({"T-1": program()}, {"T-1": cheap}, books, 0.0) >= 1          # no minimum: the 2c bid is quoted
    assert any(o["price"] == 0.02 for o in provider.my_orders())
    provider.c = config.Config({**provider.base, "min_bid_price": 0.03})                # what a run-time change does at the next step
    provider.prune(provider.my_orders(), {"T-1": program()}, {"T-1": cheap}, books, 0.0)
    assert provider.cancel_reasons["bid_too_cheap"] == 1
    assert not any(o["price"] < 0.03 for o in provider.my_orders())
    provider.place({"T-1": program()}, {"T-1": cheap}, books, 0.0)
    assert not any(o["price"] < 0.03 for o in provider.my_orders())                      # and it does not come back


def test_budget_check_uses_risk_trimmed_size_when_position_already_held():
    """A held position trims a quote under the market cap; checking budget before that trim
    caused false no_room skips on requotes of held-position markets."""
    provider, ledger = sticky_provider(fill_prob_day=0.0, capital_fraction=0.05)  # $25 budget on $500 bankroll
    provider.risk.bankroll = 500.0                                                # 3% market cap = $15
    # Hold $9.00 in T-1 (leaves $6.00 under market cap -> 15 contracts at 39c = $5.85)
    # and $10.00 in T-2 (so total at_risk = $19.00, leaving $6.00 of budget room: enough for $5.85, not $19.50).
    for i, (ticker, price, contracts) in enumerate((("T-1", 0.30, 30), ("T-2", 0.50, 20))):
        did, cid = f"d-{i}", f"o-{i}"
        ledger.insert("decisions", {"id": did, "kind": "lp_quote", "ticker": ticker, "event_ticker": f"E-{i}",
                                    "cluster": f"E-{i}", "created_ts": 1, "mode": "shadow", "strategy": "lp",
                                    "side": "yes", "limit_price": price, "contracts": contracts, "action": "order"})
        ledger.insert("orders", {"client_order_id": cid, "decision_id": did, "ticker": ticker, "side": "yes",
                                 "price": price, "contracts": contracts, "mode": "shadow", "status": "filled",
                                 "created_ts": 1})
        ledger.insert("fills", {"client_order_id": cid, "ticker": ticker, "side": "yes",
                                "price": price, "contracts": contracts, "fee": 0.0, "ts": 1})
    # Generous reward_day so the 15-contract trimmed quote still easily reaches $1.
    programs = {"T-1": program(ticker="T-1", reward_day=400.0)}
    quotes = {"T-1": quote(ticker="T-1", event_ticker="E-0")}
    books = {"T-1": (YES, NO)}
    provider.moved = {"T-1"}
    assert provider.place(programs, quotes, books, 0.0) == 1
    assert [(o["ticker"], o["side"], o["remaining"]) for o in provider.my_orders()] == [("T-1", "yes", 15)]
    assert dict(provider.moved_not_requoted) == {}

    # When risk trims the quote below min_contracts while untrimmed size exceeds budget, it is other_rule, not no_room.
    provider.broker.cancel(provider.my_orders()[0]["client_order_id"], "reference_moved")
    # Add $3.00 more held in T-1 ($12.00 total -> $3.00 market room -> 7 YES or 5 NO, both < 10 min_contracts),
    # and raise budget to $27.00 ($5.00 room >= 10 * $0.39, still < $19.50 untrimmed).
    ledger.insert("orders", {"client_order_id": "o-extra", "decision_id": "d-0", "ticker": "T-1", "side": "yes",
                             "price": 0.30, "contracts": 10, "mode": "shadow", "status": "filled", "created_ts": 2})
    ledger.insert("fills", {"client_order_id": "o-extra", "ticker": "T-1", "side": "yes",
                            "price": 0.30, "contracts": 10, "fee": 0.0, "ts": 2})
    provider.c = config.Config({**dict(provider.c), "capital_fraction": 0.054})  # $27 budget; $22 held -> $5 room
    provider.moved = {"T-1"}
    assert provider.place(programs, quotes, books, 0.0) == 0
    assert provider.trimmed_away >= 1
    assert dict(provider.moved_not_requoted) == {"other_rule": 1}



