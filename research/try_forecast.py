"""Run the full forecast pipeline on a few live events and print what it produced."""
import json, pickle, sys, time
from pmbot import config
from pmbot.universe import candidates
from pmbot.llm.pipeline import Forecaster

qs = pickle.load(open("/tmp/quotes.pkl", "rb"))
cfg = config.load()
cs = candidates(qs, cfg.universe)
want = sys.argv[1:]  # event tickers
picked = [c for c in cs if c.event_ticker in want] if want else cs[:2]
fc = Forecaster(config=dict(cfg.forecast))
results = []
for c in picked:
    t = time.time()
    out = fc.run(c.quotes)
    print(f"\n##### {c.event_ticker} ({c.category}) cost ${out.cost_usd:.3f} in {time.time()-t:.0f}s skipped={out.skipped}", flush=True)
    print("screen:", json.dumps(out.screen))
    if out.dossier:
        d = out.dossier
        print("summary:", d["summary"][:700])
        print("resolution:", json.dumps(d["resolution"])[:700])
        print("base_rate:", d["base_rate"][:300])
        print(f"research cost ${d['_cost_usd']:.3f}, {d['_duration_s']:.0f}s, {len(d['sources'])} sources, {len(d['key_facts'])} facts")
    for s in out.samples:
        print(f"  {s['model']:7s} #{s['sample_idx']} ${s.get('cost_usd',0):.3f} {s.get('duration_s',0):.0f}s", {k: round(v, 3) for k, v in s["probs"].items()}, s.get("error", ""))
    for q in c.quotes:
        print(f"  {q.ticker}: median {out.median(q.ticker)} sd {out.spread(q.ticker):.3f} | market {q.yes_bid:.2f}/{q.yes_ask:.2f} | {q.title[:60]} [{q.yes_sub_title}]")
    if out.samples and out.samples[0].get("reasoning"):
        print("reasoning[0]:", out.samples[0]["reasoning"][:900])
    results.append({"event": c.event_ticker, "cost": out.cost_usd, "skipped": out.skipped})
print("\nTOTAL", json.dumps(results))
