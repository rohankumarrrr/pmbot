"""Does the ledger agree with the exchange about our resting orders and fills?"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .kalshi.client import KalshiClient, count
from .ledger.db import Ledger, now

OURS = "pm-"            # client-order-ID prefix; anything else on the account is not the bot's
LISTING_LAG_S = 30      # Kalshi's order listing trails a new order by a few seconds
IN_FLIGHT_S = 150       # a 'submitting' row is settled by sync() within this window


@dataclass
class Report:
    exchange_resting: int = 0
    ledger_resting: int = 0
    duplicates: list[str] = field(default_factory=list)        # one client ID resting twice
    orphans: list[str] = field(default_factory=list)           # resting on the exchange, not in the ledger
    stale: list[str] = field(default_factory=list)             # resting in the ledger, not on the exchange
    missing_fills: list[str] = field(default_factory=list)     # exchange fills the ledger never recorded
    fill_mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.duplicates or self.orphans or self.stale or self.missing_fills or self.fill_mismatches)

    def summary(self) -> str:
        if self.ok:
            return f"consistent ({self.exchange_resting} resting)"
        parts = [f"{len(v)} {name}" for name, v in (
            ("duplicate", self.duplicates), ("orphan", self.orphans), ("stale", self.stale),
            ("missing fill", self.missing_fills), ("fill size mismatch", self.fill_mismatches)) if v]
        return "INCONSISTENT: " + ", ".join(parts)


def check(ledger: Ledger, client: KalshiClient, mode: str) -> Report:
    """Run after sync(). Orders too new for the listing, or still in flight, are left out of the comparison."""
    stamp = now()
    listing = [o for o in client.orders(status="resting") if (o.get("client_order_id") or "").startswith(OURS)]
    on_exchange = {o["client_order_id"] for o in listing}
    rows = ledger.query("SELECT client_order_id, status, created_ts, exchange_order_id FROM orders WHERE mode=?", [mode])
    by_id = {r["client_order_id"]: r for r in rows}
    resting = {r["client_order_id"] for r in rows if r["status"] in ("resting", "partial")}
    in_flight = {r["client_order_id"] for r in rows if r["status"] == "submitting" and stamp - r["created_ts"] < IN_FLIGHT_S}
    too_new = {r["client_order_id"] for r in rows if stamp - r["created_ts"] < LISTING_LAG_S}

    report = Report(exchange_resting=len(on_exchange), ledger_resting=len(resting))
    report.duplicates = sorted(k for k, n in Counter(o["client_order_id"] for o in listing).items() if n > 1)
    report.orphans = sorted(on_exchange - resting - in_flight - too_new)
    report.stale = sorted(resting - on_exchange - too_new)

    order_of = {r["exchange_order_id"]: r["client_order_id"] for r in rows if r["exchange_order_id"]}
    recorded = {r["id"]: r["contracts"] for r in ledger.query(
        "SELECT f.id, f.contracts FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id WHERE o.mode=?", [mode])}
    oldest = min((r["created_ts"] for r in rows), default=stamp)
    for f in client.fills(min_ts=oldest - 60):
        if f.get("order_id") not in order_of:
            continue                                   # a fill on an order the bot did not place
        if f["fill_id"] not in recorded:
            if stamp - by_id[order_of[f["order_id"]]]["created_ts"] >= LISTING_LAG_S:
                report.missing_fills.append(f["fill_id"])
        elif abs(recorded[f["fill_id"]] - count(f.get("count_fp"))) > 1e-9:
            report.fill_mismatches.append(f["fill_id"])
    return report


def check_and_react(ledger: Ledger, client: KalshiClient, mode: str) -> tuple[Report, bool]:
    """Log every result. One bad check is a warning; a second in a row means the bot should halt.

    Returns (report, should_halt). Requiring two in a row keeps a slow listing from stopping the bot.
    """
    report = check(ledger, client, mode)
    key = f"inconsistent_streak:{mode}"
    streak = 0 if report.ok else (ledger.get_state(key) or 0) + 1
    ledger.set_state(key, streak)
    ledger.set_state(f"last_consistency:{mode}", {"ts": now(), "ok": report.ok, "summary": report.summary()})
    if not report.ok:
        detail = {k: v[:5] for k, v in vars(report).items() if isinstance(v, list) and v}
        ledger.risk_event("consistency_warning", f"{report.summary()} {detail}"[:500])
    return report, streak >= 2
