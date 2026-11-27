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


def add_run(runner, hours_ago, skipped=None, cost=0.3):
    from pmbot.ledger.db import new_id, now
    runner.ledger.insert("forecast_runs", {"id": new_id(), "event_ticker": "E", "created_ts": now() - int(hours_ago * 3600),
                                           "skipped": skipped, "cost_usd": cost})


def test_forecast_budget_is_paced_across_the_day(runner):
    # 12 a day at 2 per cycle: 2 forecasts per 4 hours.
    assert runner.budget_left()[0] == 2
    add_run(runner, 1)
    add_run(runner, 3)
    assert runner.budget_left()[0] == 0          # this 4-hour share is used
    add_run(runner, 5)
    assert runner.budget_left()[0] == 0
    runner.ledger.execute("UPDATE forecast_runs SET created_ts = created_ts - 4*3600")
    assert runner.budget_left()[0] == 2          # four hours later the next share opens


def test_forecast_budget_rolls_over_24_hours_and_ignores_skipped_runs(runner):
    for h in range(12):
        add_run(runner, 5 + h)                   # 12 forecasts between 5 and 16 hours ago
    assert runner.budget_left()[0] == 0          # daily budget used, whatever the clock says
    runner.ledger.execute("UPDATE forecast_runs SET created_ts = created_ts - 30600")
    assert runner.budget_left()[0] == 1          # 8.5 hours later the oldest has aged out
    add_run(runner, 0.1, skipped="screen:rules_unclear", cost=0.001)
    slots, dollars = runner.budget_left()
    assert slots == 1                            # a screened-out run does not use a slot
    assert dollars == pytest.approx(8.0 - 11 * 0.3 - 0.001)   # but its cost counts


def test_claude_cli_recreates_workdir_if_removed(tmp_path, monkeypatch):
    import json, os, shutil, subprocess, tempfile
    from pmbot.llm.backend import ClaudeCLI

    ephemeral = tmp_path / "gone"
    ephemeral.mkdir()
    monkeypatch.setenv("TMPDIR", str(ephemeral))
    monkeypatch.setattr(tempfile, "tempdir", None)
    cli = ClaudeCLI(binary="claude")
    assert cli.workdir.startswith(str(ephemeral))
    shutil.rmtree(ephemeral)                     # caller's ephemeral TMPDIR cleaned up after launch

    seen_cwd = []
    def fake_run(cmd, **kw):
        seen_cwd.append(kw["cwd"])
        assert os.path.isdir(kw["cwd"])
        assert "TMPDIR" not in kw["env"]
        out = json.dumps({"is_error": False, "subtype": "success", "structured_output": {"ok": True}, "total_cost_usd": 0.0})
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = cli.run("hi", {"type": "object"}, "haiku", "sys")
    assert res.data == {"ok": True}
    assert seen_cwd and os.path.isdir(seen_cwd[0])
    shutil.rmtree(cli.workdir, ignore_errors=True)

