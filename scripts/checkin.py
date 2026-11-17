"""Gather the state of both bots for a scheduled check-in. Prints JSON; changes nothing except
its own bookmark of when it last ran (data/checkin_state.json).

Usage: python scripts/checkin.py
"""

import json
import subprocess
import time
from pathlib import Path

from pmbot import config
from pmbot.ledger.db import Ledger
from pmbot.score import lp_report, report

BOTS = {
    "paper": {"config": "config/settings.yaml", "log": "logs/bot.log", "process": "pmbot cycle --every 600", "interval_s": 600},
    "demo": {"config": "config/demo.yaml", "log": "logs/demo.log", "process": "pmbot cycle --every 300", "interval_s": 300},
}
STATE = Path("data/checkin_state.json")
now = int(time.time())
since = json.loads(STATE.read_text())["ts"] if STATE.exists() else now - 6 * 3600


def running(pattern: str) -> bool:
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


out = {"checked_at": time.strftime("%Y-%m-%d %H:%M %Z"), "hours_since_last_checkin": round((now - since) / 3600, 1), "bots": {}}
for name, bot in BOTS.items():
    cfg = config.load(bot["config"])
    ledger = Ledger(cfg.ledger_path)
    mode = cfg.mode
    last_cycle = ledger.get_state(f"lp_last_step:{mode}") or 0
    log = Path(bot["log"]).read_text().splitlines() if Path(bot["log"]).exists() else []
    q = lambda sql, *a: ledger.one(sql, a)["n"]
    # Cycle start times, from the price snapshots each cycle writes. A long gap usually means the Mac slept.
    stamps = [since] + [r["ts"] for r in ledger.query("SELECT DISTINCT ts FROM snapshots WHERE ts>? ORDER BY ts", [since])] + [now]
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    info = {
        "mode": mode,
        "longest_gap_between_cycles_min": round(max(gaps) / 60, 1) if gaps else None,
        "gaps_over_30_min": sum(g > 1800 for g in gaps),
        "process_running": running(bot["process"]),
        "minutes_since_last_cycle": round((now - last_cycle) / 60, 1) if last_cycle else None,
        # A cycle with forecasts can take ~10 minutes on top of the interval.
        "stuck": bool(last_cycle) and now - last_cycle > bot["interval_s"] + 1800,
        "halted": ledger.get_state(f"halted:{mode}"),
        "cycles_logged_total": sum("cycle:" in line for line in log),
        "cycle_failures_total": sum("cycle failed" in line for line in log),
        "last_failure_line": next((line[:300] for line in reversed(log) if "cycle failed" in line), None),
        "since_last_checkin": {
            "orders_placed": q("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND created_ts>?", mode, since),
            "orders_cancelled": q("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND status='cancelled' AND updated_ts>?", mode, since),
            "fills": q("SELECT COUNT(*) AS n FROM fills f JOIN orders o ON o.client_order_id=f.client_order_id WHERE o.mode=? AND f.ts>?", mode, since),
            "markets_settled": q("SELECT COUNT(*) AS n FROM markets WHERE result IN ('yes','no') AND updated_ts>?", since),
            "risk_events": [dict(r) for r in ledger.query(
                "SELECT datetime(ts,'unixepoch','localtime') AS at, kind, substr(detail,1,200) AS detail FROM risk_events WHERE ts>? ORDER BY id DESC LIMIT 8", [since])],
        },
        "resting_orders": q("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND status IN ('resting','partial')", mode),
        "orders_in_last_hour": q("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND created_ts>?", mode, now - 3600),
        "hourly_order_cap": cfg.risk.max_orders_per_hour,
    }
    if mode == "shadow":
        info["reward_strategy"] = lp_report(ledger, mode)
        score = report(ledger, mode)
        info["forecasts"] = {k: score.get(k) for k in ("resolved_events", "target_events", "forecast_runs", "brier",
                                                        "confirmation_half", "simulated_pnl", "price_correction_baseline", "gate0")}
    else:
        info["self_check_last"] = ledger.get_state(f"last_consistency:{mode}")
        info["self_check_bad_streak"] = ledger.get_state(f"inconsistent_streak:{mode}") or 0
        try:
            from pmbot.consistency import check
            from pmbot.runner import trading_client
            client = trading_client(cfg)
            live = check(ledger, client, mode)
            info["exchange_check_now"] = {"ok": live.ok, "summary": live.summary()}
            info["exchange_balance"] = client.balance().get("balance_dollars")
        except Exception as e:
            info["exchange_check_now"] = {"ok": None, "error": repr(e)[:300]}
    out["bots"][name] = info

STATE.write_text(json.dumps({"ts": now}))
print(json.dumps(out, indent=1, default=str))
