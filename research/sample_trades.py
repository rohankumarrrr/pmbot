"""Pull a time-random sample of Kalshi trades, plus the outcome of every market traded.

Each sampled window is a few seconds of *all* trades on the exchange, chosen
uniformly at random within a month, so within a month the sample is
representative of trades by count. Months are sampled at different rates;
`window_seconds` and `windows` per month are written out so results can be
reweighted.

Usage: python research/sample_trades.py --start 2025-01 --end 2026-11 --out research/out
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from pmbot.kalshi import KalshiClient

UTC = dt.timezone.utc


def month_range(start: str, end: str) -> list[tuple[dt.datetime, dt.datetime]]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        a = dt.datetime(y, m, 1, tzinfo=UTC)
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((a, dt.datetime(y2, m2, 1, tzinfo=UTC)))
        y, m = y2, m2
    return out


def fetch_window(client: KalshiClient, t0: int, seconds: int, historical: bool, max_pages: int) -> list[dict]:
    rows, pages, cursor = [], 0, None
    path = "/historical/trades" if historical else "/markets/trades"
    while True:
        try:
            data = client.get(path, limit=1000, min_ts=t0, max_ts=t0 + seconds, cursor=cursor)
        except Exception as e:
            # Drop the whole window: a partial window would over-weight its first seconds.
            print("window failed:", t0, str(e)[:100], file=sys.stderr)
            return []
        rows.extend(data.get("trades") or [])
        cursor = data.get("cursor")
        pages += 1
        if not cursor or pages >= max_pages:
            break
    for r in rows:
        r["window_t0"] = t0
    return rows


def sample_month(client, a, b, cutoff, target_trades, rng, workers) -> tuple[pd.DataFrame, dict]:
    """Adaptive: probe a few windows to learn the trade rate, then size the windows."""
    lo, hi = int(a.timestamp()), int(min(b, dt.datetime.now(UTC) - dt.timedelta(hours=1)).timestamp())
    if hi <= lo:
        return pd.DataFrame(), {}
    hist = lambda t: t < cutoff
    probe_secs = 60
    probes = [rng.randrange(lo, hi - probe_secs) for _ in range(12)]
    with ThreadPoolExecutor(workers) as ex:
        probe_rows = list(ex.map(lambda t: fetch_window(client, t, probe_secs, hist(t), 40), probes))
    rate = max(sum(len(r) for r in probe_rows) / (len(probes) * probe_secs), 0.02)  # trades/sec
    # Aim for ~1500 trades per window so most windows are 1-2 pages, min 3s, max 600s.
    seconds = int(min(600, max(3, round(1500 / rate))))
    n_windows = min(400, max(40, int(target_trades / max(rate * seconds, 1))))
    starts = [rng.randrange(lo, hi - seconds) for _ in range(n_windows)]
    rows: list[dict] = []
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(fetch_window, client, t, seconds, hist(t), 60) for t in starts]
        for f in as_completed(futs):
            rows.extend(f.result())
    meta = {"month": a.strftime("%Y-%m"), "window_seconds": seconds, "windows": n_windows,
            "trades": len(rows), "est_trades_per_sec": rate, "span_seconds": hi - lo}
    return pd.DataFrame(rows), meta


def fetch_markets(client: KalshiClient, tickers: list[str], workers: int) -> pd.DataFrame:
    """Outcome and timing for each ticker. Live endpoint first, then the historical archive."""
    keep = ["ticker", "event_ticker", "status", "result", "open_time", "close_time", "settlement_ts",
            "expiration_value", "volume_fp", "market_type", "title", "yes_sub_title", "settlement_value_dollars"]

    def batch(path: str, chunk: list[str]) -> list[dict]:
        try:
            data = client.get(path, tickers=",".join(chunk), limit=1000)
        except Exception as e:  # one bad ticker should not sink the batch
            print("market batch failed:", path, str(e)[:120], file=sys.stderr)
            return []
        return [{k: m.get(k) for k in keep} for m in data.get("markets") or []]

    chunks = [tickers[i:i + 40] for i in range(0, len(tickers), 40)]
    found: dict[str, dict] = {}
    for path in ("/markets", "/historical/markets"):
        todo = [c for c in ([t for t in ch if t not in found] for ch in chunks) if c]
        with ThreadPoolExecutor(workers) as ex:
            for rows in ex.map(lambda c: batch(path, c), todo):
                for r in rows:
                    found[r["ticker"]] = r
        print(f"{path}: have {len(found)}/{len(tickers)} markets", flush=True)
    return pd.DataFrame(found.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01")
    ap.add_argument("--end", default="2026-11")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--target-per-month", type=int, default=120_000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = KalshiClient()
    rng = random.Random(args.seed)
    cutoff = int(dt.datetime.fromisoformat(
        client.historical_cutoff()["trades_created_ts"].replace("Z", "+00:00")).timestamp())

    frames, metas = [], []
    for a, b in month_range(args.start, args.end):
        t = time.time()
        df, meta = sample_month(client, a, b, cutoff, args.target_per_month, rng, args.workers)
        if not len(df):
            continue
        frames.append(df)
        metas.append(meta)
        print(f"{meta['month']}: {meta['trades']:>7} trades, {meta['windows']} x {meta['window_seconds']}s windows, "
              f"{time.time() - t:.0f}s", flush=True)
        pd.concat(frames).to_parquet(out / "trades_sample.parquet")
        json.dump(metas, open(out / "trades_sample_meta.json", "w"), indent=1)

    trades = pd.concat(frames).drop_duplicates("trade_id")
    trades.to_parquet(out / "trades_sample.parquet")
    tickers = sorted(trades["ticker"].unique())
    print(f"{len(trades)} trades across {len(tickers)} markets; fetching outcomes", flush=True)
    fetch_markets(client, tickers, args.workers).to_parquet(out / "markets_sample.parquet")
    print("done", flush=True)


if __name__ == "__main__":
    main()
