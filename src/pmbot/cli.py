from __future__ import annotations

import argparse
import json
import time

from . import catalog, config
from .kalshi.client import KalshiClient
from .ledger.db import Ledger
from .portfolio import account, mark_to_market
from .universe import candidates


def cmd_cycle(args, cfg) -> None:
    from .runner import Runner, log
    runner = Runner(cfg)
    while True:
        started = time.time()
        try:
            log("cycle:", json.dumps(runner.cycle(forecast=not args.no_forecast), default=str))
        except Exception as e:
            # Keep the loop alive; a run of failures is visible in the log and risk_events.
            log("cycle failed:", repr(e)[:300])
            runner.ledger.risk_event("cycle_error", repr(e)[:500])
            if not args.every:
                raise
        if not args.every:
            return
        time.sleep(max(5, args.every - (time.time() - started)))


def cmd_universe(args, cfg) -> None:
    ledger, client = Ledger(cfg.ledger_path), KalshiClient()
    quotes = catalog.pull_open_quotes(client, ledger)
    cands = candidates(quotes, cfg.universe)
    print(f"{len(quotes)} open markets -> {len(cands)} candidate events ({sum(c.tradable for c in cands)} tradable)")
    for c in cands[: args.limit]:
        q = c.quotes[0]
        print(f"{c.event_ticker:36s} {c.category[:12]:12s} {'T' if c.tradable else 's'} age {c.listing_age_days:5.1f}d "
              f"closes {c.days_to_close:5.1f}d {len(c.quotes)}m {q.yes_bid:.2f}/{q.yes_ask:.2f} {q.title[:60]}")


def cmd_score(args, cfg) -> None:
    from .score import report
    print(json.dumps(report(Ledger(cfg.ledger_path), cfg.mode), indent=2, default=str))


def cmd_lp(args, cfg) -> None:
    from .score import lp_report
    print(json.dumps(lp_report(Ledger(cfg.ledger_path), cfg.mode), indent=2))


def start_balance(cfg) -> float:
    """Shadow uses the configured bankroll; demo and live start from what the ledger has spent plus
    what the exchange holds now, so cash reported here matches the exchange."""
    if cfg.mode == "shadow":
        return float(cfg.bankroll_usd)
    from .runner import trading_client
    ledger = Ledger(cfg.ledger_path)
    spent = account(ledger, cfg.mode, 0.0)
    return float(trading_client(cfg).balance()["balance_dollars"]) - spent.cash


def cmd_status(args, cfg) -> None:
    ledger = Ledger(cfg.ledger_path)
    acct = account(ledger, cfg.mode, start_balance(cfg))
    resting = ledger.one("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND status IN ('resting','partial')", [cfg.mode])["n"]
    print(json.dumps({
        "mode": cfg.mode, "halted": ledger.get_state(f"halted:{cfg.mode}"),
        "cash": round(acct.cash, 2), "open_positions": len(acct.open_positions), "open_cost": round(acct.open_cost, 2),
        "realized_pnl": round(acct.realized, 2), "equity_marked": round(mark_to_market(ledger, acct), 2),
        "resting_orders": resting,
        "recent_risk_events": [dict(r) for r in ledger.query("SELECT ts, kind, detail FROM risk_events ORDER BY id DESC LIMIT 5")],
    }, indent=2))


def cmd_dashboard(args, cfg) -> None:
    from .dashboard import write
    print(write(Ledger(cfg.ledger_path), cfg, args.out))


def cmd_halt(args, cfg) -> None:
    from .runner import Runner
    runner = Runner(cfg)
    runner.risk.halt(args.reason)
    runner.broker.cancel_all(args.reason)
    print("halted; all resting orders cancelled")


def cmd_resume(args, cfg) -> None:
    from .risk import RiskManager
    ledger = Ledger(cfg.ledger_path)
    RiskManager(ledger, cfg, cfg.mode, float(cfg.bankroll_usd)).resume()
    if cfg.mode != "shadow":
        # The kill switch also tripped the exchange-side order group; without a reset every new order is refused.
        from .runner import trading_client
        gid = ledger.get_state(f"order_group:{cfg.mode}")
        if gid:
            trading_client(cfg).reset_order_group(gid)
    print("resumed")


def main() -> None:
    ap = argparse.ArgumentParser(prog="pmbot")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle", help="run one cycle, or loop with --every")
    c.add_argument("--no-forecast", action="store_true", help="catalog, fills and settlements only; no model calls")
    c.add_argument("--every", type=int, default=0, help="seconds between cycles; 0 runs once")
    c.set_defaults(fn=cmd_cycle)
    u = sub.add_parser("universe", help="list candidate events")
    u.add_argument("--limit", type=int, default=40)
    u.set_defaults(fn=cmd_universe)
    sub.add_parser("score", help="score resolved forecasts and check gate 0").set_defaults(fn=cmd_score)
    sub.add_parser("lp", help="liquidity-reward strategy: estimated rewards vs fill costs").set_defaults(fn=cmd_lp)
    sub.add_parser("status", help="account, orders and risk state").set_defaults(fn=cmd_status)
    d = sub.add_parser("dashboard", help="write a one-page HTML view of the account")
    d.add_argument("--out", default="data/dashboard.html")
    d.set_defaults(fn=cmd_dashboard)
    h = sub.add_parser("halt", help="kill switch: stop trading and cancel everything")
    h.add_argument("reason", nargs="?", default="manual")
    h.set_defaults(fn=cmd_halt)
    sub.add_parser("resume", help="clear a halt").set_defaults(fn=cmd_resume)
    args = ap.parse_args()
    args.fn(args, config.load(args.config))


if __name__ == "__main__":
    main()
