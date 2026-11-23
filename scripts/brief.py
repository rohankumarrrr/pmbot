"""Compact view of scripts/checkin.py output, for the hourly check-in.

  python scripts/checkin.py | python scripts/brief.py                 paper, demo and twin (this machine)
  ssh server '... scripts/checkin.py live; ...' | python scripts/brief.py
  python scripts/brief.py --twin                                      the twin's open-experiment numbers

Reads the JSON on stdin (anything after it, such as log lines, is echoed), and prints the fields a
check-in compares hour to hour.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time

KEEP = ["process_running", "minutes_since_last_cycle", "halted", "gaps_over_30_min", "cycles_logged_total",
        "cycle_failures_total", "last_failure_line", "since_last_checkin", "resting_orders", "orders_in_last_hour",
        "exchange_check_now", "self_check_bad_streak", "exchange_balance", "money"]
REWARD = ["resting_quotes", "dollars_at_risk_resting", "offers_on_held_positions", "estimated_rewards", "estimated_rewards_per_day", "fills",
          "inventory_cost", "inventory_marked", "trading_pnl_realized", "trading_pnl_unrealized"]


def checkin() -> None:
    raw = sys.stdin.read()
    end = raw.rfind("\n}") + 2
    data, rest = json.loads(raw[:end]), raw[end:].strip()
    print(data["checked_at"], "| hours since last check-in:", data["hours_since_last_checkin"])
    for name, bot in data["bots"].items():
        print("==", name)
        since = dict(bot.get("since_last_checkin") or {})
        events = since.pop("risk_events", [])
        kinds: dict[str, int] = {}
        for e in events:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        for key in KEEP:
            if key in bot:
                print("  ", key, since if key == "since_last_checkin" else bot[key])
        if kinds:
            print("   risk events:", kinds, "| latest:", (events[0].get("detail") or "")[:160])
        strategy = bot.get("reward_strategy") or {}
        print("   reward:", {k: strategy.get(k) for k in REWARD})
        print("   programs:", strategy.get("rewards_by_program"))
        forecasts = bot.get("forecasts")
        if forecasts:
            print("   forecasts:", forecasts["resolved_events"], "resolved;", forecasts["forecast_runs"], "| brier", forecasts.get("brier"))
    if rest:
        print(rest[:700])


def twin(path: str = "data/ledger_twin.sqlite") -> None:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    one = lambda sql, *a: db.execute(sql, a).fetchone()
    now = time.time()
    print("twin resting: quotes %d, at risk $%.2f, average $%.2f" % one(
        "SELECT COUNT(*), COALESCE(SUM(price*contracts),0), COALESCE(AVG(price*contracts),0) FROM orders o "
        "WHERE status IN ('resting','partial') AND (SELECT kind FROM decisions d WHERE d.id=o.decision_id) != 'lp_close'"))
    print("  offers on held positions:", one("SELECT COUNT(*) FROM orders o WHERE status IN ('resting','partial') "
                                             "AND (SELECT kind FROM decisions d WHERE d.id=o.decision_id) = 'lp_close'")[0])
    for band, n, risk in db.execute(
            "SELECT CASE WHEN price<0.15 THEN 'under 15c' WHEN price<0.50 THEN '15-50c' ELSE '50c+' END, COUNT(*), SUM(price*contracts) "
            "FROM orders o WHERE status IN ('resting','partial') "
            "AND (SELECT kind FROM decisions d WHERE d.id=o.decision_id) != 'lp_close' GROUP BY 1"):
        print(f"  {band}: {n} quotes, ${risk:.2f}")
    print("  largest family (markets):", one("SELECT COALESCE(MAX(n),0) FROM (SELECT COUNT(DISTINCT ticker) n FROM orders "
                                           "WHERE status IN ('resting','partial') GROUP BY substr(ticker,1,8))")[0])
    print("  new markets in the last hour:", one("SELECT COUNT(*) FROM (SELECT MIN(created_ts) f FROM orders WHERE status!='rejected' "
                                                "GROUP BY ticker) WHERE f>?", now - 3600)[0])
    print("  accrued in the last hour: $%.3f" % (one("SELECT COALESCE(SUM(usd),0) FROM lp_accruals WHERE ts>?", now - 3600)[0]))
    quoted = {r[0] for r in db.execute("SELECT DISTINCT ticker FROM orders WHERE status IN ('resting','partial')")}
    # Markets dropped by the minimum-bid experiment are not that experiment's "abandoned programs".
    cheap = {r[0] for r in db.execute("SELECT ticker FROM orders o WHERE created_ts=(SELECT MAX(created_ts) FROM orders x "
                                      "WHERE x.ticker=o.ticker AND x.status!='rejected') AND price<=0.02")}
    for label, since in (("since 09:12 today's experiment 3 began (2026-11-23 15:12 UTC)", 1795446720.0), ("last 24h", now - 86400)):
        total = left = 0.0
        for ticker, usd, whole in db.execute(
                "SELECT ticker, SUM(CASE WHEN ts>? THEN usd ELSE 0 END), SUM(usd) FROM lp_accruals GROUP BY ticker", (since,)):
            if ticker in cheap and ticker not in quoted:
                continue
            total += usd
            if ticker not in quoted and whole < 1.0:
                left += usd
        if total:
            print(f"  accrual {label} (leaving out markets last quoted at 1c-2c and since dropped): ${total:.2f}, of which in programs under $1 no longer quoted ${left:.2f} ({100 * left / total:.0f}%)")
    fills = db.execute("SELECT COUNT(*), COALESCE(SUM(price*contracts+fee),0), MAX(ts) FROM fills").fetchone()
    try:    # why quotes were pulled in the last hour (recorded per order since 2026-11-23)
        for r in db.execute("SELECT ticker, side, price, reason, detail FROM lp_cancels WHERE ts>? ORDER BY ts", (now - 3600,)):
            print(f"  pulled {r[0][:34]} {r[1]}@{r[2]:.2f} {r[3]} {r[4]}")
    except sqlite3.OperationalError:
        pass    # a ledger from before the table existed
    print("  fills: %d, cost $%.2f, latest %s UTC" % (fills[0], fills[1], time.strftime("%m-%d %H:%M", time.gmtime(fills[2])) if fills[2] else "none"))


if __name__ == "__main__":
    twin() if "--twin" in sys.argv else checkin()
