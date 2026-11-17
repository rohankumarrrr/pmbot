"""Who made money on Kalshi? Maker and taker returns by price, category, month and time to close.

Reads the time-random trade sample from sample_trades.py. For every trade both
sides are scored: the buyer of YES at price p and the buyer of NO at 1 - p,
one of whom was the taker (paid the fee) and the other the maker.

Return on a side = (payout - price - fee) / price, weighted by dollars staked.
Standard errors are clustered by event, because trades in one event share an outcome.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "research/out")
TAKER, MAKER_SHARE = 0.07, {"quadratic": 0.0, "quadratic_with_maker_fees": 0.25, "quadratic_with_combo_maker_fees": 0.5}

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", lambda x: f"{x:,.4f}")


def load() -> pd.DataFrame:
    t = pd.read_parquet(OUT / "trades_sample.parquet")
    m = pd.read_parquet(OUT / "markets_sample.parquet")
    series = {s["ticker"]: s for s in json.load(open("/tmp/kalshi_series.json"))}
    t["yes_price"] = t["yes_price_dollars"].astype(float)
    t["count"] = t["count_fp"].astype(float)
    t["ts"] = pd.to_datetime(t["created_time"], format="ISO8601", utc=True)
    t["month"] = t["ts"].dt.strftime("%Y-%m")
    t = t[~t["is_block_trade"]]
    t["series"] = t["ticker"].str.split("-").str[0]
    t["category"] = t["series"].map(lambda s: series.get(s, {}).get("category", "Unknown"))
    t.loc[t["ticker"].str.startswith("KXMVE"), "category"] = "Parlay"
    t["fee_type"] = t["series"].map(lambda s: series.get(s, {}).get("fee_type", "quadratic"))
    t["fee_mult"] = t["series"].map(lambda s: series.get(s, {}).get("fee_multiplier", 1.0)).astype(float)
    t = t.merge(m[["ticker", "event_ticker", "result", "open_time", "close_time"]], on="ticker", how="left")
    total = len(t)
    t = t[t["result"].isin(["yes", "no"])].copy()
    print(f"trades: {total:,} sampled, {len(t):,} in markets that resolved yes/no ({len(t)/total:.1%})")
    t["yes_won"] = (t["result"] == "yes").astype(float)
    t["close_ts"] = pd.to_datetime(t["close_time"], format="ISO8601", utc=True)
    t["open_ts"] = pd.to_datetime(t["open_time"], format="ISO8601", utc=True)
    t["hours_to_close"] = (t["close_ts"] - t["ts"]).dt.total_seconds() / 3600
    t["hours_since_open"] = (t["ts"] - t["open_ts"]).dt.total_seconds() / 3600
    return t


def sides(t: pd.DataFrame) -> pd.DataFrame:
    """Two rows per trade: the YES buyer and the NO buyer, each tagged maker or taker."""
    quad = t["yes_price"] * (1 - t["yes_price"])
    taker_fee = TAKER * t["fee_mult"] * quad
    maker_fee = taker_fee * t["fee_type"].map(MAKER_SHARE).fillna(0.0)
    taker_yes = t["taker_outcome_side"] == "yes"
    base = ["ticker", "event_ticker", "category", "series", "month", "count", "hours_to_close", "hours_since_open", "ts"]
    yes = t[base].copy()
    yes["side"], yes["price"], yes["won"] = "yes", t["yes_price"], t["yes_won"]
    yes["role"] = np.where(taker_yes, "taker", "maker")
    yes["fee"] = np.where(taker_yes, taker_fee, maker_fee)
    no = t[base].copy()
    no["side"], no["price"], no["won"] = "no", 1 - t["yes_price"], 1 - t["yes_won"]
    no["role"] = np.where(taker_yes, "maker", "taker")
    no["fee"] = np.where(taker_yes, maker_fee, taker_fee)
    s = pd.concat([yes, no], ignore_index=True)
    s = s[(s["price"] > 0) & (s["price"] < 1)]
    s["stake"] = s["price"] * s["count"]
    s["pnl"] = (s["won"] - s["price"] - s["fee"]) * s["count"]
    s["gross"] = (s["won"] - s["price"]) * s["count"]
    return s


def summarize(s: pd.DataFrame, by: list[str], min_events: int = 30) -> pd.DataFrame:
    """Dollar-weighted return with event-clustered standard error."""
    rows = []
    for key, g in s.groupby(by, observed=True):
        ev = g.groupby("event_ticker").agg(pnl=("pnl", "sum"), stake=("stake", "sum"), gross=("gross", "sum"))
        n = len(ev)
        if n < min_events:
            continue
        stake = ev["stake"].sum()
        ret = ev["pnl"].sum() / stake
        # Ratio estimator, linearised: residual per cluster = pnl_e - ret * stake_e.
        resid = ev["pnl"] - ret * ev["stake"]
        se = np.sqrt(n / (n - 1) * (resid**2).sum()) / stake
        key = key if isinstance(key, tuple) else (key,)
        rows.append((*key, len(g), n, g["price"].mean(), g["won"].mean(), ev["gross"].sum() / stake, ret, se, ret / se if se else 0))
    return pd.DataFrame(rows, columns=[*by, "fills", "events", "avg_price", "win_rate", "gross_ret", "net_ret", "se", "t"])


def main() -> None:
    t = load()
    s = sides(t)
    bins = [0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.0]
    s["price_bin"] = pd.cut(s["price"], bins, right=False)
    s["year"] = s["month"].str[:4]
    s["period"] = np.where(s["month"] < "2025-07", "2025H1", np.where(s["month"] < "2026-01", "2025H2",
                           np.where(s["month"] < "2026-07", "2026H1", "2026H2")))

    print("\n=== 1. Overall, by role and period (dollar-weighted net return after fees) ===")
    print(summarize(s, ["period", "role"]).to_string(index=False))

    print("\n=== 2. By role and price paid, 2026 only ===")
    s26 = s[s["year"] == "2026"]
    print(summarize(s26, ["role", "price_bin"]).to_string(index=False))

    print("\n=== 3. Makers by category, 2026 ===")
    print(summarize(s26[s26["role"] == "maker"], ["category"]).sort_values("net_ret", ascending=False).to_string(index=False))

    print("\n=== 4. Takers by category, 2026 ===")
    print(summarize(s26[s26["role"] == "taker"], ["category"]).sort_values("net_ret", ascending=False).to_string(index=False))

    print("\n=== 5. Makers by category and coarse price, 2026 ===")
    s26 = s26.copy()
    s26["price_band"] = pd.cut(s26["price"], [0, 0.15, 0.5, 0.85, 1.0], right=False, labels=["<15c", "15-50c", "50-85c", ">=85c"])
    tab = summarize(s26[s26["role"] == "maker"], ["category", "price_band"], min_events=40)
    print(tab.sort_values(["category", "price_band"]).to_string(index=False))

    print("\n=== 6. Makers by time to close, 2026, excluding Sports/Parlay/Crypto ===")
    slow = s26[~s26["category"].isin(["Sports", "Parlay", "Crypto"])].copy()
    slow["ttc"] = pd.cut(slow["hours_to_close"], [-1e9, 1, 6, 24, 72, 168, 720, 1e9],
                         labels=["<1h", "1-6h", "6-24h", "1-3d", "3-7d", "7-30d", ">30d"])
    print(summarize(slow[slow["role"] == "maker"], ["ttc"]).to_string(index=False))
    print(summarize(slow[slow["role"] == "taker"], ["ttc"]).to_string(index=False))

    print("\n=== 7. Makers by month (all categories) ===")
    print(summarize(s[s["role"] == "maker"], ["month"]).to_string(index=False))

    # What a resting order in a reward-paying market should expect when it is filled.
    prog_series = {p["series_ticker"] for p in json.load(open("/tmp/incentives.json"))}
    lip = s[s["series"].isin(prog_series) & (s["role"] == "maker") & (s["month"] >= "2026-05")
            & ~s["category"].isin(["Sports", "Crypto", "Mentions", "Parlay"])].copy()
    lip["price_band"] = pd.cut(lip["price"], [0, 0.05, 0.15, 0.5, 0.85, 1.0], right=False,
                               labels=["<5c", "5-15c", "15-50c", "50-85c", ">=85c"])
    lip["far"] = np.where(lip["hours_to_close"] >= 48, ">=48h to close", "<48h to close")
    print("\n=== 8. Makers in series that pay liquidity rewards today, May-Nov 2026, by time to close ===")
    print(summarize(lip, ["far"]).to_string(index=False))
    print("\n=== 9. Same, >=48h to close, by price paid ===")
    print(summarize(lip[lip["far"] == ">=48h to close"], ["price_band"], min_events=20).to_string(index=False))
    print("\n=== 10. Same, >=48h to close, by category ===")
    print(summarize(lip[lip["far"] == ">=48h to close"], ["category"], min_events=20).sort_values("net_ret").to_string(index=False))

    s.to_parquet(OUT / "sides.parquet")


if __name__ == "__main__":
    main()
