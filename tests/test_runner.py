"""Decision logic of the forecast strategy, with the network and the model stubbed out."""

import copy

import pytest

from pmbot import config
from pmbot.execution.brokers import ShadowBroker
from pmbot.ledger.db import Ledger
from pmbot.runner import Runner
from test_core import Tape
from test_lp import quote


@pytest.fixture
def runner():
    cfg = config.Config(copy.deepcopy(dict(config.load("config/settings.yaml"))))
    cfg["lp"]["enabled"] = False
    cfg["trading"]["price_prior_a"], cfg["trading"]["price_prior_b"] = 0.0, 1.0     # tested separately below
    ledger = Ledger(":memory:")
    ledger.insert("markets", {"ticker": "T-1", "event_ticker": "T", "series_ticker": "S", "status": "active"})
    return Runner(cfg, ledger=ledger, market_data=object(), broker=ShadowBroker(ledger, Tape([])), forecaster=object())


def last_decision(runner):
    return runner.ledger.one("SELECT * FROM decisions ORDER BY created_ts DESC, rowid DESC LIMIT 1")


def test_buys_yes_one_tick_inside_the_spread_with_blended_edge(runner):
    q = quote(yes_bid=0.39, yes_ask=0.41)
    assert runner.decide("run", "forecast", q, 0.555, 0.02, True, False) == 1
    d = last_decision(runner)
    assert (d["side"], d["limit_price"], d["contracts"], d["action"]) == ("yes", 0.40, 42, "order")
    assert d["p_final"] == pytest.approx(0.4505, abs=1e-3) and d["edge"] == pytest.approx(0.0505, abs=1e-3)
    order = runner.ledger.one("SELECT * FROM orders")
    assert (order["side"], order["price"], order["contracts"], order["status"]) == ("yes", 0.40, 42, "resting")


def test_buys_no_when_model_is_below_market(runner):
    q = quote(yes_bid=0.53, yes_ask=0.55)
    runner.decide("run", "forecast", q, 0.34, 0.02, True, False)
    d = last_decision(runner)
    assert d["side"] == "no" and d["limit_price"] == pytest.approx(0.46)     # 1 - 0.55 + one tick


def test_joins_the_queue_when_spread_is_one_tick(runner):
    q = quote(yes_bid=0.40, yes_ask=0.41, yes_bid_size=300)
    runner.decide("run", "forecast", q, 0.62, 0.02, True, False)
    d = last_decision(runner)
    assert d["limit_price"] == 0.40
    coid = runner.ledger.one("SELECT client_order_id FROM orders")["client_order_id"]
    assert runner.ledger.get_state(f"queue:{coid}") == 300


def test_small_disagreement_is_not_traded(runner):
    q = quote(yes_bid=0.39, yes_ask=0.41)
    assert runner.decide("run", "forecast", q, 0.44, 0.02, True, False) == 0
    assert "edge_below_min" in last_decision(runner)["reasons"]


def test_edge_inside_ensemble_noise_is_not_traded(runner):
    q = quote(yes_bid=0.39, yes_ask=0.41)
    assert runner.decide("run", "forecast", q, 0.555, 0.20, True, False) == 0
    assert "edge_within_ensemble_noise" in last_decision(runner)["reasons"]


def test_one_position_per_market(runner):
    q = quote(yes_bid=0.39, yes_ask=0.41)
    runner.decide("run", "forecast", q, 0.555, 0.02, True, False)
    assert runner.decide("run2", "forecast", q, 0.555, 0.02, True, False) == 0
    assert "already_positioned" in last_decision(runner)["reasons"]


def test_every_forecast_is_recorded_even_without_a_trade(runner):
    q = quote(yes_bid=0.39, yes_ask=0.41)
    runner.decide("run", "forecast", q, 0.40, 0.01, False, True)
    d = last_decision(runner)
    assert d["action"] == "skip" and d["p_model"] == 0.40 and d["mid"] == pytest.approx(0.40) and d["holdout"] == 1


def test_price_correction_shifts_the_anchor(runner):
    runner.cfg["trading"]["price_prior_a"], runner.cfg["trading"]["price_prior_b"] = -0.05, 1.10
    q = quote(yes_bid=0.39, yes_ask=0.41)
    runner.decide("run", "forecast", q, 0.40, 0.01, True, False)     # model agrees with the raw price
    assert last_decision(runner)["p_final"] == pytest.approx(0.385, abs=2e-3)   # pulled below 0.40 by the correction


def test_baseline_logged_once_per_market(runner):
    from pmbot.universe import Candidate
    cand = Candidate("T", "Economics", [quote(yes_bid=0.39, yes_ask=0.41)], True, 1.0, 10.0)
    assert runner.record_baselines([cand]) == 1
    assert runner.record_baselines([cand]) == 0
    d = last_decision(runner)
    assert (d["kind"], d["strategy"], d["action"]) == ("baseline", "price_prior", "skip")


def test_sibling_series_count_as_one_family():
    from pmbot.runner import family
    assert family("KXAAAGASCDOK") == family("KXAAAGASCDNM")
    assert family("KXSUEZWEEKLY") != family("KXPANAMAWEEKLY")
