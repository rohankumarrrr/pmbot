"""Fetch the result of every market in the trade sample. Batches of 300 tickers per call."""
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from pmbot.kalshi import KalshiClient

OUT = "research/out"
KEEP = ["ticker", "event_ticker", "status", "result", "open_time", "close_time", "settlement_ts", "volume_fp", "title"]
t = pd.read_parquet(f"{OUT}/trades_sample.parquet", columns=["ticker", "created_time"])
last = t.groupby("ticker")["created_time"].max().str[:7]
client = KalshiClient(max_rps=5)
found: dict[str, dict] = {}


def batch(path: str, chunk: list[str]) -> list[dict]:
    try:
        return [{k: m.get(k) for k in KEEP} for m in client.get(path, tickers=",".join(chunk), limit=1000).get("markets") or []]
    except Exception as e:
        print("batch failed:", path, str(e)[:120], file=sys.stderr, flush=True)
        return []


def sweep(path: str, tickers: list[str]) -> None:
    todo = [x for x in tickers if x not in found]
    chunks = [todo[i:i + 300] for i in range(0, len(todo), 300)]
    with ThreadPoolExecutor(4) as ex:
        for i, rows in enumerate(ex.map(lambda c: batch(path, c), chunks)):
            for r in rows:
                found[r["ticker"]] = r
            if i % 100 == 99:
                print(f"  {path}: {i + 1}/{len(chunks)} batches, {len(found)} markets", flush=True)
    print(f"{path}: have {len(found)}/{len(last)}", flush=True)


old, new = last[last <= "2026-08"].index.tolist(), last[last > "2026-08"].index.tolist()
sweep("/markets", new)                 # settled after the historical cutoff, or still open
sweep("/historical/markets", old)
sweep("/historical/markets", new)      # stragglers either side of the cutoff
sweep("/markets", old)
pd.DataFrame(found.values()).to_parquet(f"{OUT}/markets_sample.parquet")
print("done", flush=True)
