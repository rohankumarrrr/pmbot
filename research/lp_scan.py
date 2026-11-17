"""Rank current liquidity-reward opportunities from a saved book snapshot (or live with --live)."""
import pickle, sys, time
from collections import Counter

import pandas as pd

from pmbot import config, lp
from pmbot.kalshi import KalshiClient

pd.set_option("display.width", 230)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
cfg = config.load()
c = KalshiClient(max_rps=3)
quotes = {q.ticker: q for q in pickle.load(open("/tmp/quotes.pkl", "rb"))}
progs = lp.load_programs(c)
print(f"programs: {len(progs)}, pool ${sum(p.reward_day for p in progs.values()):,.0f}/day")
if "--live" in sys.argv:
    books = lp.fetch_books(c, sorted(progs))
else:
    raw = pickle.load(open("/tmp/lip_books.pkl", "rb"))
    books = {t: tuple(sorted(((float(a), float(b)) for a, b in ob.get(k) or []), reverse=True)
                      for k in ("yes_dollars", "no_dollars")) for t, ob in raw.items()}
now = time.time()
why = Counter()
for t, p in progs.items():
    q = quotes.get(t)
    for r in (["not_open"] if q is None else lp.market_reasons(p, q, cfg.lp, now) or ["eligible"]):
        why[r] += 1
print(why.most_common())
ranked = lp.rank(progs, quotes, books, cfg.lp, 1000, now)
df = pd.DataFrame([{**s.__dict__, "yield_day": s.yield_day, "cat": quotes[s.ticker].category[:10],
                    "vol24": quotes[s.ticker].volume_24h, "days": (quotes[s.ticker].close_ts - now) / 86400,
                    "pool": progs[s.ticker].reward_day} for s in ranked])
print(f"{len(df)} eligible side quotes at >= {cfg.lp.min_yield_day:.0%}/day: "
      f"${df.reward_day.sum():,.0f}/day on ${df.at_risk.sum():,.0f} at risk")
print(df.yield_day.describe(percentiles=[.25, .5, .75, .9]).to_string())
for n in (30, 60, 120):
    top = df.head(n)
    print(f"top {n}: ${top.reward_day.sum():.2f}/day on ${top.at_risk.sum():,.0f} at risk "
          f"({top.reward_day.sum() / top.at_risk.sum():.1%}/day)")
cols = ["ticker", "side", "price", "contracts", "share", "reward_day", "at_risk", "yield_day", "queue_ahead", "cat", "vol24", "days", "pool"]
print(df.head(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30)[cols].to_string(index=False))
df.to_parquet("research/out/lp_scan.parquet")
