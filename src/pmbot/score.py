"""Score resolved forecasts against the market and check the gates."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from .blend import logit
from .ledger.db import Ledger
from .portfolio import mark_price, positions


def resolved(ledger: Ledger, mode: str) -> pd.DataFrame:
    """One row per forecast-time decision in a market that has resolved yes or no."""
    rows = ledger.query(
        """SELECT d.ticker, d.event_ticker, d.created_ts, d.mid, d.p_model, d.p_final, d.holdout, d.tradable,
                  d.action, m.result, s.category
           FROM decisions d JOIN markets m ON m.ticker = d.ticker LEFT JOIN series s ON s.ticker = m.series_ticker
           WHERE d.mode=? AND d.kind='forecast' AND d.p_model IS NOT NULL AND d.mid IS NOT NULL
             AND m.result IN ('yes','no')
           ORDER BY d.created_ts""",
        [mode])
    df = pd.DataFrame([dict(r) for r in rows])
    if len(df):
        df["y"] = (df["result"] == "yes").astype(float)
    return df


def brier(p, y) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def bootstrap_diff(df: pd.DataFrame, a: str, b: str, n_boot: int = 4000, seed: int = 0) -> tuple[float, float, float]:
    """Mean Brier(a) - Brier(b) with a 95% interval, resampling whole events."""
    per_event = df.assign(d=(df[a] - df["y"]) ** 2 - (df[b] - df["y"]) ** 2).groupby("event_ticker")["d"].agg(["sum", "count"])
    sums, counts = per_event["sum"].to_numpy(), per_event["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(n_boot, len(sums)))
    boots = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return float(sums.sum() / counts.sum()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def fit_logistic(X: np.ndarray, y: np.ndarray, ridge: float = 1e-3, iters: int = 50) -> np.ndarray:
    """Newton's method with a small ridge so separable samples still converge."""
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        grad = X.T @ (p - y) + ridge * w
        hess = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def information_test(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict:
    """outcome ~ logit(market) + logit(model). A positive model coefficient means the model
    knows something the price does not; the fitted weights are also the best blend."""
    X = np.column_stack([np.ones(len(df)), df["mid"].map(logit), df["p_model"].map(logit)])
    y = df["y"].to_numpy()
    w = fit_logistic(X, y)
    events = df["event_ticker"].to_numpy()
    uniq = np.unique(events)
    rows_of = {e: np.flatnonzero(events == e) for e in uniq}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        take = np.concatenate([rows_of[e] for e in rng.choice(uniq, len(uniq))])
        boots.append(fit_logistic(X[take], y[take])[2])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    total = w[1] + w[2]
    return {"intercept": float(w[0]), "beta_market": float(w[1]), "beta_model": float(w[2]),
            "beta_model_ci": (float(lo), float(hi)),
            "implied_w_market": float(w[1] / total) if total else None}


def baseline_report(ledger: Ledger, mode: str) -> dict:
    """Does the bias-corrected price beat the raw price on markets that have resolved?"""
    rows = ledger.query(
        """SELECT d.ticker, d.event_ticker, d.mid, d.p_final, m.result FROM decisions d JOIN markets m ON m.ticker=d.ticker
           WHERE d.mode=? AND d.kind='baseline' AND m.result IN ('yes','no')""", [mode])
    logged = ledger.one("SELECT COUNT(*) AS n FROM decisions WHERE mode=? AND kind='baseline'", [mode])["n"]
    if len(rows) < 20:
        return {"logged": logged, "resolved": len(rows)}
    df = pd.DataFrame([dict(r) for r in rows])
    df["y"] = (df["result"] == "yes").astype(float)
    d, lo, hi = bootstrap_diff(df, "p_final", "mid")
    return {"logged": logged, "resolved": len(df), "events": int(df["event_ticker"].nunique()),
            "brier_market": round(brier(df["mid"], df["y"]), 4), "brier_corrected": round(brier(df["p_final"], df["y"]), 4),
            "corrected_minus_market": round(d, 5), "ci95": (round(lo, 5), round(hi, 5)), "beats_market": hi < 0,
            "yes_rate": round(df["y"].mean(), 3), "avg_price": round(df["mid"].mean(), 3)}


def realized_pnl(ledger: Ledger, mode: str) -> pd.DataFrame:
    rows = [{"event_ticker": p.event_ticker, "ticker": p.ticker, "cost": p.cost, "pnl": p.payout - p.cost}
            for p in positions(ledger, mode) if p.settled]
    return pd.DataFrame(rows, columns=["event_ticker", "ticker", "cost", "pnl"])


def report(ledger: Ledger, mode: str, gates_path: str = "config/gates.yaml") -> dict:
    gates = yaml.safe_load(open(gates_path))["gate0"]
    df = resolved(ledger, mode)
    out: dict = {"mode": mode, "resolved_markets": len(df),
                 "resolved_events": int(df["event_ticker"].nunique()) if len(df) else 0,
                 "target_events": gates["min_resolved_events"]}
    runs = ledger.one("SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd),0) AS c, SUM(skipped IS NULL) AS ok FROM forecast_runs")
    out["forecast_runs"] = {"total": runs["n"], "produced_forecast": runs["ok"] or 0, "inference_cost_usd": round(runs["c"], 2)}
    out["price_correction_baseline"] = baseline_report(ledger, mode)
    if len(df) < 5:
        return out
    out["brier"] = {k: round(brier(df[c], df["y"]), 4) for k, c in (("market", "mid"), ("model", "p_model"), ("blend", "p_final"))}
    out["log_loss"] = {k: round(log_loss(df[c], df["y"]), 4) for k, c in (("market", "mid"), ("model", "p_model"), ("blend", "p_final"))}
    if df["event_ticker"].nunique() >= 20:
        # Split by event so one event never straddles the two halves.
        first_seen = df.groupby("event_ticker")["created_ts"].min().sort_values()
        cut = int(len(first_seen) * (1 - gates["confirmation_fraction"]))
        confirm = df[df["event_ticker"].isin(first_seen.index[cut:])]
        d, lo, hi = bootstrap_diff(confirm, "p_final", "mid")
        out["confirmation_half"] = {"events": int(confirm["event_ticker"].nunique()),
                                    "blend_minus_market_brier": round(d, 5), "ci95": (round(lo, 5), round(hi, 5)),
                                    "beats_market": hi < 0}
        out["information_test"] = information_test(df)
    pnl = realized_pnl(ledger, mode)
    if len(pnl):
        by_event = pnl.groupby("event_ticker")["pnl"].sum()
        out["simulated_pnl" if mode == "shadow" else "pnl"] = {
            "settled_positions": len(pnl), "staked": round(pnl["cost"].sum(), 2), "profit": round(pnl["pnl"].sum(), 2),
            "profit_without_best_event": round(pnl["pnl"].sum() - by_event.max(), 2),
        }
    enough = out["resolved_events"] >= gates["min_resolved_events"]
    conf = out.get("confirmation_half", {})
    sim = out.get("simulated_pnl", out.get("pnl", {}))
    out["gate0"] = {
        "enough_events": enough,
        "blend_beats_market": bool(conf.get("beats_market")),
        "profit_positive": sim.get("profit", 0) > 0,
        "profit_positive_without_best_event": sim.get("profit_without_best_event", 0) > 0,
    }
    out["gate0"]["verdict"] = ("PASS" if all(out["gate0"].values()) else "FAIL") if enough else "collecting"
    return out


def lp_report(ledger: Ledger, mode: str) -> dict:
    """Liquidity-reward strategy so far: estimated rewards against what the fills cost."""
    acc = ledger.one("SELECT COUNT(*) AS n, COALESCE(SUM(usd),0) AS usd, MIN(ts) AS t0, MAX(ts) AS t1 "
                     "FROM lp_accruals WHERE mode=?", [mode])
    first_order = ledger.one("SELECT MIN(o.created_ts) AS t FROM orders o JOIN decisions d ON d.id=o.decision_id "
                             "WHERE o.mode=? AND d.strategy='lp'", [mode])["t"]
    hours = ((acc["t1"] or 0) - (first_order or 0)) / 3600 if acc["n"] else 0.0
    resting = ledger.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(o.price*o.contracts),0) AS at_risk FROM orders o JOIN decisions d ON d.id=o.decision_id "
        "WHERE o.mode=? AND d.strategy='lp' AND o.status IN ('resting','partial')", [mode])
    lp_tickers = {r["ticker"] for r in ledger.query("SELECT DISTINCT ticker FROM decisions WHERE mode=? AND strategy='lp'", [mode])}
    held = [p for p in positions(ledger, mode) if p.ticker in lp_tickers]
    realized = sum(p.payout - p.cost for p in held if p.settled)
    open_cost, open_value = 0.0, 0.0
    for p in held:
        if p.settled or p.contracts <= 0:
            continue
        mid = mark_price(ledger, p.ticker)
        open_cost += p.cost
        open_value += p.contracts * (mid if p.side == "yes" else 1 - mid) if mid is not None else p.cost
    fills = ledger.one("SELECT COUNT(*) AS n, COALESCE(SUM(f.contracts),0) AS c FROM fills f JOIN orders o ON o.client_order_id=f.client_order_id "
                       "JOIN decisions d ON d.id=o.decision_id WHERE o.mode=? AND d.strategy='lp'", [mode])
    rewards = acc["usd"]
    return {
        "mode": mode, "hours_running": round(hours, 2),
        "resting_quotes": resting["n"], "dollars_at_risk_resting": round(resting["at_risk"], 2),
        "estimated_rewards": round(rewards, 4),
        "estimated_rewards_per_day": round(rewards / hours * 24, 2) if hours > 0 else None,
        "fills": fills["n"], "contracts_filled": fills["c"],
        "inventory_cost": round(open_cost, 2), "inventory_marked": round(open_value, 2),
        "trading_pnl_realized": round(realized, 4), "trading_pnl_unrealized": round(open_value - open_cost, 4),
        "net_estimate": round(rewards + realized + open_value - open_cost, 4),
        "note": "rewards are estimated from order-book snapshots, not credited by Kalshi" if mode == "shadow" else "compare with Kalshi's credited rewards",
    }
