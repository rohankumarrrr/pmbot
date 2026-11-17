"""What do Kalshi's liquidity rewards pay per dollar of resting orders, right now?

For every market with an active liquidity incentive, score the live order book
the way the program does and work out what a small participant would earn by
adding S contracts on each side at the best price.

Rules (Kalshi help centre, "Liquidity Incentive Program"):
- one snapshot per second; it counts only if BOTH sides hold at least Target Size
- reference price = first level, walking down from the best bid, where cumulative
  size reaches Target Size / 5
- an order's score = size x discount^(ticks below the reference); 1.0x at or above it
- each side's scores are normalised to sum to 1; a participant's snapshot score is
  their yes-side share plus their no-side share (2.0 in total per snapshot)
- reward = pool x (your score / everyone's score) x (share of snapshots that counted)
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pmbot.kalshi import KalshiClient

S = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0   # contracts added per side
pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")


def parse(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))


def side_score(levels: list[tuple[float, float]], target: float, discount: float, tick: float) -> dict:
    """levels: (price, size) with best first. Scores the side as one program snapshot would.

    Per the CFTC filing: walk down from the best bid adding *whole* price levels until
    cumulative size reaches Target Size; every order at those levels qualifies. The
    reference price is the level where cumulative size first reaches Target Size / 5
    (help-centre wording; the Feb 2026 filing used the best bid itself).
    """
    depth = sum(s for _, s in levels)
    out = {"qualifies": False, "depth": depth, "score": 0.0, "best": levels[0][0] if levels else None,
           "ref": None, "best_size": levels[0][1] if levels else 0.0}
    if depth < target or not levels:
        return out
    qualifying, cum, ref = [], 0.0, None
    for price, size in levels:
        qualifying.append((price, size))
        cum += size
        if ref is None and cum >= target / 5:
            ref = price
        if cum >= target:
            break
    score = sum(size * discount ** max(0.0, round((ref - price) / tick)) for price, size in qualifying)
    return {**out, "qualifies": True, "score": score, "ref": ref}


def main() -> None:
    progs = [p for p in json.load(open("/tmp/incentives.json")) if p["incentive_type"] == "liquidity"]
    quotes = {q.ticker: q for q in pickle.load(open("/tmp/quotes.pkl", "rb"))}
    client = KalshiClient(max_rps=3)
    tickers = sorted({p["market_ticker"] for p in progs})
    cache = Path("/tmp/lip_books.pkl")
    books: dict[str, dict] = pickle.load(open(cache, "rb")) if cache.exists() and "--refresh" not in sys.argv else {}
    if not books:
        for i in range(0, len(tickers), 100):
            data = client.request("GET", "/markets/orderbooks", params={"tickers": tickers[i:i + 100]})
            for ob in data.get("orderbooks") or []:
                books[ob["ticker"]] = ob.get("orderbook_fp") or ob.get("orderbook") or ob
        pickle.dump(books, open(cache, "wb"))
    print(f"{len(progs)} programs on {len(tickers)} markets; {len(books)} order books fetched")

    rows = []
    for p in progs:
        t = p["market_ticker"]
        ob, q = books.get(t), quotes.get(t)
        if not ob or not q:
            continue
        days = max((parse(p["end_date"]) - parse(p["start_date"])).total_seconds() / 86400, 1 / 24)
        reward_day = p["period_reward"] / 10000 / days
        target = float(p.get("target_size_fp") or 0)
        discount = (p.get("discount_factor_bps") or 10000) / 10000
        tick = q.tick(q.mid if q.two_sided else 0.5)
        yes = sorted(((float(a), float(b)) for a, b in ob.get("yes_dollars") or []), reverse=True)
        no = sorted(((float(a), float(b)) for a, b in ob.get("no_dollars") or []), reverse=True)
        ys, ns = side_score(yes, target, discount, tick), side_score(no, target, discount, tick)
        valid = ys["qualifies"] and ns["qualifies"]
        # Joining at the best price scores 1.0 per contract (it is at or above the reference).
        share = (S / (ys["score"] + S) + S / (ns["score"] + S)) / 2 if valid else 0.0
        capital = S * ((ys["best"] or 0) + (ns["best"] or 0))
        rows.append({
            "ticker": t, "series": p["series_ticker"], "category": q.category, "title": q.title[:60],
            "reward_day": reward_day, "period_days": days, "target": target, "discount": discount,
            "yes_bid": ys["best"], "no_bid": ns["best"], "spread": 1 - (ys["best"] or 0) - (ns["best"] or 0),
            "yes_depth": ys["depth"], "no_depth": ns["depth"], "valid": valid,
            "yes_score": ys["score"], "no_score": ns["score"], "yes_best_size": ys["best_size"], "no_best_size": ns["best_size"],
            "my_share": share, "my_reward_day": reward_day * share, "capital": capital,
            "yield_day": reward_day * share / capital if capital > 0 else 0.0,
            "volume_24h": q.volume_24h, "close_days": ((q.close_ts or 0) - dt.datetime.now(dt.timezone.utc).timestamp()) / 86400,
            "mid": q.mid if q.two_sided else np.nan,
        })
    df = pd.DataFrame(rows)
    df.to_parquet("research/out/lip_yield.parquet")

    print(f"\nreward pool: ${df['reward_day'].sum():,.0f}/day across {len(df)} markets; "
          f"{df['valid'].mean():.0%} of books currently meet Target Size on both sides "
          f"(${df.loc[df['valid'], 'reward_day'].sum():,.0f}/day of the pool)")
    print("\npool by category ($/day), markets, share of books valid, median daily yield on capital for a valid book:")
    g = df.groupby("category").agg(pool=("reward_day", "sum"), markets=("ticker", "count"), valid=("valid", "mean"))
    g["median_yield_valid"] = df[df["valid"]].groupby("category")["yield_day"].median()
    g["median_target"] = df.groupby("category")["target"].median()
    print(g.sort_values("pool", ascending=False).to_string())

    v = df[df["valid"]].copy()
    print(f"\nadding {S:.0f} contracts per side at the best price, valid books only ({len(v)} markets):")
    print(v[["my_reward_day", "capital", "yield_day", "my_share", "spread", "volume_24h"]].describe(percentiles=[.1, .25, .5, .75, .9]).to_string())
    for cut in (0.002, 0.005, 0.01, 0.02):
        sub = v[v["yield_day"] >= cut]
        print(f"  yield >= {cut:.1%}/day: {len(sub):>5} markets, ${sub['my_reward_day'].sum():>8,.2f}/day on ${sub['capital'].sum():>9,.0f} capital")

    print("\ntop 25 by my reward per day (valid books):")
    cols = ["ticker", "category", "reward_day", "target", "discount", "yes_bid", "no_bid", "yes_score", "no_score",
            "my_reward_day", "capital", "yield_day", "volume_24h", "close_days"]
    print(v.sort_values("my_reward_day", ascending=False)[cols].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
