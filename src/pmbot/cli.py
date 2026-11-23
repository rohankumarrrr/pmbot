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


def _show_settings(ledger, cfg) -> None:
    from . import overrides
    base = dict(cfg["lp"])
    changed, now_ = overrides.load(ledger, cfg.mode), overrides.effective(base, ledger, cfg.mode)
    print(json.dumps({
        "mode": cfg.mode,
        "changed_at_run_time": {f"lp.{k}": {"config_file": base.get(k), "now": now_.get(k)} for k in sorted(changed)},
        "paused_families": now_.get("exclude_families") or [],
        "hard_limits_not_adjustable_here": {f"lp.{k}": base.get(k) for k in sorted(overrides.LOCKED) if k in base},
        "adjustable": {f"lp.{k}": now_[k] for k in sorted(now_) if k not in overrides.LOCKED},
    }, indent=2))


def cmd_set(args, cfg) -> None:
    from . import overrides
    ledger, base = Ledger(cfg.ledger_path), dict(cfg["lp"])
    try:
        before = overrides.put(ledger, cfg.mode, base, args.setting, overrides.parse(args.value), args.why)
    except ValueError as e:
        raise SystemExit(f"not changed: {e}")
    print(f"{cfg.mode}: {args.setting} was {before!r}, now {overrides.parse(args.value)!r}; takes effect on the next cycle")


def cmd_unset(args, cfg) -> None:
    from . import overrides
    ledger, base = Ledger(cfg.ledger_path), dict(cfg["lp"])
    try:
        had = overrides.drop(ledger, cfg.mode, base, args.setting, args.why)
    except ValueError as e:
        raise SystemExit(f"not changed: {e}")
    print(f"{cfg.mode}: {args.setting} is back to the config file's value" if had else f"{cfg.mode}: {args.setting} was not changed at run time")


def cmd_pause(args, cfg) -> None:
    from . import overrides
    ledger, base = Ledger(cfg.ledger_path), dict(cfg["lp"])
    fn = overrides.unpause if args.cmd == "unpause" else overrides.pause
    families = fn(ledger, cfg.mode, base, args.prefix, args.why)
    print(f"{cfg.mode}: paused families now {families}; takes effect on the next cycle"
          + ("" if args.cmd == "unpause" else " (quotes resting there are pulled)"))


def cmd_settings(args, cfg) -> None:
    _show_settings(Ledger(cfg.ledger_path), cfg)


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
    st = sub.add_parser("set", help="change a reward-strategy setting while the bot runs (next cycle, no restart)")
    st.add_argument("setting", help="for example lp.max_markets_per_family")
    st.add_argument("value", help="for example 2, 0.35, true or '[[0.15, -0.45], [0.50, -0.35]]'")
    st.add_argument("--why", default="", help="reason, written to the risk-event log")
    st.set_defaults(fn=cmd_set)
    us = sub.add_parser("unset", help="go back to the config file's value for a setting")
    us.add_argument("setting")
    us.add_argument("--why", default="")
    us.set_defaults(fn=cmd_unset)
    for name, text in (("pause", "stop quoting every market whose ticker starts with PREFIX and pull its quotes"),
                       ("unpause", "quote that family again")):
        pz = sub.add_parser(name, help=text)
        pz.add_argument("prefix", help="for example KXAAAGAS")
        pz.add_argument("--why", default="")
        pz.set_defaults(fn=cmd_pause)
    sub.add_parser("settings", help="reward-strategy settings in force, and what was changed at run time").set_defaults(fn=cmd_settings)
    args = ap.parse_args()
    args.fn(args, config.load(args.config))


if __name__ == "__main__":
    main()
