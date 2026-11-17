"""Risk manager. Has a veto over every order and can halt trading."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .blend import Sizing
from .ledger.db import Ledger
from .portfolio import Account, account, mark_to_market

DAY = 86400


@dataclass
class Verdict:
    ok: bool
    contracts: int
    reasons: list[str]


class RiskManager:
    def __init__(self, ledger: Ledger, cfg, mode: str, bankroll: float):
        self.ledger, self.cfg, self.mode, self.bankroll = ledger, cfg, mode, bankroll
        self.t = cfg.trading
        self.r = cfg.risk

    # --- halting -----------------------------------------------------------

    @property
    def halted(self) -> str | None:
        return self.ledger.get_state(f"halted:{self.mode}")

    def halt(self, reason: str) -> None:
        self.ledger.set_state(f"halted:{self.mode}", reason)
        self.ledger.risk_event("halt", f"{self.mode}: {reason}")

    def resume(self) -> None:
        """Manual only: a human clears a halt after looking at why it fired."""
        self.ledger.execute("DELETE FROM kv WHERE key=?", [f"halted:{self.mode}"])
        self.ledger.risk_event("resume", self.mode)

    # --- account-level checks ----------------------------------------------

    def check_account(self) -> str | None:
        """Run every cycle. Returns the halt reason if a limit is breached."""
        if self.halted:
            return self.halted
        acct = account(self.ledger, self.mode, self.bankroll)
        equity = mark_to_market(self.ledger, acct)
        peak = max(self.ledger.get_state(f"peak_equity:{self.mode}", self.bankroll), equity)
        self.ledger.set_state(f"peak_equity:{self.mode}", peak)
        if equity < peak * (1 - self.r.max_drawdown):
            self.halt(f"drawdown: equity {equity:.2f} is more than {self.r.max_drawdown:.0%} below peak {peak:.2f}")
            return self.halted
        day_key = f"day_open_equity:{self.mode}:{time.strftime('%Y-%m-%d', time.gmtime())}"
        day_open = self.ledger.get_state(day_key)
        if day_open is None:
            self.ledger.set_state(day_key, equity)
        elif equity < day_open - self.r.daily_loss_limit * self.bankroll:
            self.halt(f"daily loss: equity {equity:.2f} vs {day_open:.2f} at start of day")
            return self.halted
        return None

    # --- per-order checks --------------------------------------------------

    def review(self, sizing: Sizing, ticker: str, cluster: str, acct: Account | None = None) -> Verdict:
        reasons: list[str] = []
        if self.halted:
            return Verdict(False, 0, ["halted"])
        if sizing.side is None or sizing.contracts < 1:
            return Verdict(False, 0, [sizing.reason or "no_trade"])
        acct = acct or account(self.ledger, self.mode, self.bankroll)
        unit = sizing.price + sizing.fee

        # Only the unfilled remainder of an order is still at risk of filling; the filled part is a position.
        resting = self.ledger.query(
            "SELECT o.ticker, m.event_ticker, o.price * (o.contracts - COALESCE("
            "(SELECT SUM(f.contracts) FROM fills f WHERE f.client_order_id = o.client_order_id), 0)) AS cost "
            "FROM orders o LEFT JOIN markets m ON m.ticker = o.ticker "
            "WHERE o.mode=? AND o.status IN ('resting','partial','submitting')", [self.mode])
        if len(resting) >= self.r.max_open_orders:
            return Verdict(False, 0, ["max_open_orders"])
        recent = self.ledger.one("SELECT COUNT(*) AS n FROM orders WHERE mode=? AND created_ts>?",
                                 [self.mode, int(time.time()) - 3600])["n"]
        if recent >= self.r.max_orders_per_hour:
            return Verdict(False, 0, ["max_orders_per_hour"])

        def exposure(match) -> float:
            held = sum(p.cost for p in acct.open_positions if match(p.ticker, p.event_ticker))
            return held + sum(r["cost"] for r in resting if match(r["ticker"], r["event_ticker"]))

        market_room = self.t.max_fraction_per_market * self.bankroll - exposure(lambda t, e: t == ticker)
        cluster_room = self.t.max_fraction_per_cluster * self.bankroll - exposure(lambda t, e: e == cluster)
        cash_room = acct.cash - sum(r["cost"] for r in resting)
        room = min(market_room, cluster_room, cash_room)
        n = min(sizing.contracts, int((room + 1e-9) // unit)) if room > 0 else 0
        if n < sizing.contracts:
            reasons.append("trimmed_market_cap" if room == market_room else
                           "trimmed_cluster_cap" if room == cluster_room else "trimmed_cash")
        if n < 1:
            return Verdict(False, 0, reasons or ["no_room"])
        return Verdict(True, n, reasons)
