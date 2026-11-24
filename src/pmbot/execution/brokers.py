"""Order placement: a simulated broker for shadow mode and the real exchange for demo/live.

Both write the same `orders` and `fills` rows, so everything downstream
(positions, risk, scoring) is identical across modes.

Orders are stored by the side bought ('yes' or 'no') and the price paid for
that side. On Kalshi's single book, buying NO at q is an ask on YES at 1 - q.
"""

from __future__ import annotations

import time
from typing import Protocol

from ..catalog import ts as parse_ts
from ..kalshi.client import KalshiClient, KalshiError, count, dollars
from ..kalshi.fees import order_fee
from ..ledger.db import Ledger, new_id, now


class Broker(Protocol):
    mode: str

    def place(self, decision_id: str, ticker: str, side: str, price: float, contracts: int, ttl_s: int,
              queue_ahead: float = 0.0, closing: bool = False) -> str | None: ...
    def cancel(self, client_order_id: str, reason: str) -> None: ...
    def cancel_all(self, reason: str) -> None: ...
    def sync(self) -> int: ...
    def renew(self) -> int: ...


def client_order_id(decision_id: str) -> str:
    """One order per decision: a restart that replays a decision reuses the same ID."""
    return f"pm-{decision_id}"


def book_order(side: str, price: float) -> tuple[str, float]:
    """(side bought, price paid) -> (YES-book side, YES price)."""
    return ("bid", price) if side == "yes" else ("ask", round(1 - price, 4))


class _Base:
    """Order leases: with `lease_s` set, an order is placed to expire after that long instead of after its
    full lifetime, and renew() pushes the expiry forward each cycle. If the bot stops, its orders lapse on
    the exchange within one lease instead of resting unattended at stale prices (which is how a paper
    order was filled 11 cents through the market while the machine slept, 2026-11-18).
    """

    mode: str

    def __init__(self, ledger: Ledger, lease_s: int | None = None):
        self.ledger, self.lease_s = ledger, lease_s

    def _record(self, coid: str, decision_id: str, ticker: str, side: str, price: float, contracts: int,
                ttl_s: int, status: str, exchange_id: str | None = None) -> int:
        """Write the order row. Returns the expiry to give the exchange."""
        stamp = now()
        expires = stamp + (min(ttl_s, self.lease_s) if self.lease_s else ttl_s)
        self.ledger.insert("orders", {
            "client_order_id": coid, "decision_id": decision_id, "ticker": ticker, "side": side, "price": price,
            "contracts": contracts, "mode": self.mode, "status": status, "exchange_order_id": exchange_id,
            "created_ts": stamp, "expires_ts": expires, "updated_ts": stamp,
        })
        if expires < stamp + ttl_s:
            self.ledger.set_state(f"deadline:{coid}", stamp + ttl_s)     # the lease is never renewed past this
        return expires

    def _due(self) -> list[tuple]:
        """(order row, new expiry) for resting orders whose expiry should move by a minute or more."""
        if not self.lease_s:
            return []
        stamp, out = now(), []
        for o in self._resting():
            if o["expires_ts"] <= stamp:
                continue            # already lapsed: sync() will mark it, and the strategy may place a fresh one
            key = f"deadline:{o['client_order_id']}"
            deadline = self.ledger.get_state(key)
            if deadline is None:
                deadline = o["expires_ts"]
                if deadline > stamp + self.lease_s:      # placed before leases existed: bring it under one
                    self.ledger.set_state(key, deadline)
            target = min(stamp + self.lease_s, deadline)
            if abs(target - o["expires_ts"]) >= 60:
                out.append((o, int(target)))
        return out

    def _set_expiry(self, coid: str, expires: int) -> None:
        self.ledger.execute("UPDATE orders SET expires_ts=?, updated_ts=? WHERE client_order_id=?", [expires, now(), coid])

    def _set_status(self, coid: str, status: str) -> None:
        self.ledger.execute("UPDATE orders SET status=?, updated_ts=? WHERE client_order_id=?", [status, now(), coid])

    def _resting(self) -> list:
        return self.ledger.query("SELECT * FROM orders WHERE mode=? AND status IN ('resting','partial')", [self.mode])

    def _filled(self, coid: str) -> float:
        return self.ledger.one("SELECT COALESCE(SUM(contracts),0) AS n FROM fills WHERE client_order_id=?", [coid])["n"]

    def _fee_terms(self, ticker: str) -> tuple[str, float]:
        row = self.ledger.one(
            "SELECT s.fee_type, s.fee_multiplier FROM markets m JOIN series s ON s.ticker = m.series_ticker WHERE m.ticker=?",
            [ticker])
        return (row["fee_type"], row["fee_multiplier"]) if row else ("quadratic", 1.0)


class ShadowBroker(_Base):
    """No orders leave the machine. Fills are inferred from the public trade tape.

    A resting buy fills when a taker sells into it. We count a fill when trades
    print *through* our price, or *at* our price once the size that was queued
    ahead of us has traded. That is deliberately strict: paper fills that never
    would have happened are the classic way a simulation flatters itself.
    """

    mode = "shadow"

    def __init__(self, ledger: Ledger, client: KalshiClient, lease_s: int | None = None):
        super().__init__(ledger, lease_s)
        self.client = client

    def renew(self) -> int:
        due = self._due()
        for o, expires in due:
            self._set_expiry(o["client_order_id"], expires)
        return len(due)

    def place(self, decision_id, ticker, side, price, contracts, ttl_s, queue_ahead=0.0, closing=False) -> str | None:
        coid = client_order_id(decision_id)
        if self.ledger.one("SELECT 1 FROM orders WHERE client_order_id=?", [coid]):
            return coid
        self._record(coid, decision_id, ticker, side, price, contracts, ttl_s, "resting")
        self.ledger.set_state(f"queue:{coid}", queue_ahead)
        return coid

    def cancel(self, client_order_id: str, reason: str) -> None:
        self._set_status(client_order_id, "cancelled")

    def cancel_all(self, reason: str) -> None:
        for o in self._resting():
            self._set_status(o["client_order_id"], "cancelled")

    def sync(self) -> int:
        fills = 0
        for o in self._resting():
            fills += self._simulate(o)
        return fills

    def _simulate(self, o) -> int:
        coid = o["client_order_id"]
        since = self.ledger.get_state(f"tape:{coid}", o["created_ts"])
        until = min(now(), o["expires_ts"])
        book_side, yes_price = book_order(o["side"], o["price"])
        # Our bid is hit by takers selling YES (outcome side 'no'); our ask by takers buying YES.
        hitting = "no" if book_side == "bid" else "yes"
        queue = float(self.ledger.get_state(f"queue:{coid}", 0.0))
        remaining = o["contracts"] - self._filled(coid)
        fee_type, fee_mult = self._fee_terms(o["ticker"])
        made = 0
        trades = sorted(self.client.trades(ticker=o["ticker"], min_ts=since, max_ts=until),
                        key=lambda t: t["created_time"])
        for t in trades:
            if remaining <= 0:
                break
            if t.get("is_block_trade") or t["taker_outcome_side"] != hitting:
                continue
            p, size = dollars(t["yes_price_dollars"]), count(t["count_fp"])
            through = p < yes_price - 1e-9 if book_side == "bid" else p > yes_price + 1e-9
            at = abs(p - yes_price) < 1e-9
            if at:
                take = min(queue, size)       # orders ahead of ours fill first
                queue, size = queue - take, size - take
            if not (through or (at and size > 0)):
                continue
            qty = remaining if through else min(remaining, size)
            self.ledger.insert("fills", {
                "id": new_id(), "client_order_id": coid, "ticker": o["ticker"], "side": o["side"],
                "price": o["price"], "contracts": qty,
                "fee": order_fee(o["price"], qty, True, fee_type, fee_mult),
                "ts": parse_ts(t["created_time"]), "simulated": True,
            })
            remaining -= qty
            made += 1
        self.ledger.set_state(f"tape:{coid}", until)
        self.ledger.set_state(f"queue:{coid}", queue)
        if remaining <= 0:
            self._set_status(coid, "filled")
        elif now() >= o["expires_ts"]:
            self._set_status(coid, "expired")
        elif remaining < o["contracts"]:
            self._set_status(coid, "partial")
        return made


class KalshiBroker(_Base):
    """Real orders on Kalshi (demo or live). Post-only, so every fill is a maker fill."""

    def __init__(self, ledger: Ledger, client: KalshiClient, mode: str, subaccount: int | None = None,
                 group_contracts_limit: int = 500, lease_s: int | None = None):
        if mode not in ("demo", "live"):
            raise ValueError(mode)
        if not client.authenticated:
            raise ValueError("KalshiBroker needs an authenticated client")
        super().__init__(ledger, lease_s)
        self.client, self.mode, self.subaccount = client, mode, subaccount
        self.group_contracts_limit = group_contracts_limit

    def order_group(self) -> str:
        """All orders share one group: its rolling contract limit is an exchange-side runaway stop."""
        key = f"order_group:{self.mode}"
        gid = self.ledger.get_state(key)
        if not gid:
            gid = self.client.create_order_group(self.group_contracts_limit, self.subaccount)["order_group_id"]
            self.ledger.set_state(key, gid)
        return gid

    def place(self, decision_id, ticker, side, price, contracts, ttl_s, queue_ahead=0.0, closing=False) -> str | None:
        coid = client_order_id(decision_id)
        if self.ledger.one("SELECT 1 FROM orders WHERE client_order_id=?", [coid]):
            return coid
        book_side, yes_price = book_order(side, price)
        if closing and not self.holds(ticker, "no" if side == "yes" else "yes", contracts):
            # An offer on a held position pairs it off; without the position it would open one on the other
            # side, at a size no cap checked. Kalshi's reduce_only flag would enforce that, but it is refused
            # on resting orders ("reduce_only can only be used with IoC orders", demo, 2026-11-23), so the
            # position is read from the exchange before every such order.
            self.ledger.risk_event("offer_refused", f"{ticker} {side}@{price} x{contracts}: the exchange does not show that position")
            return None
        # Write the order row first: if we crash mid-request, sync() finds it by client ID.
        expires = self._record(coid, decision_id, ticker, side, price, contracts, ttl_s, "submitting")
        try:
            resp = self.client.create_order(
                ticker, book_side, contracts, yes_price, coid, post_only=True,
                expiration_ts=expires, order_group_id=self.order_group(), subaccount=self.subaccount)
        except KalshiError as e:
            if e.code == "order_already_exists":   # an earlier attempt got through
                self._set_status(coid, "resting")
                return coid
            self._set_status(coid, "rejected")
            self.ledger.risk_event("order_rejected", f"{ticker} {side}@{price}: {e}")
            return None
        self.ledger.execute("UPDATE orders SET status='resting', exchange_order_id=?, updated_ts=? WHERE client_order_id=?",
                            [resp["order_id"], now(), coid])
        return coid

    def cancel(self, client_order_id: str, reason: str) -> None:
        row = self.ledger.one("SELECT exchange_order_id FROM orders WHERE client_order_id=?", [client_order_id])
        if row and row["exchange_order_id"]:
            try:
                self.client.cancel_order(row["exchange_order_id"])
            except KalshiError as e:
                if e.status != 404:
                    raise
        self._set_status(client_order_id, "cancelled")

    def holds(self, ticker: str, side: str, contracts: float) -> bool:
        """Whether the exchange shows at least `contracts` held on `side` of this market (positive is YES)."""
        net = sum(float(r["position_fp"]) for r in self.client.positions(ticker=ticker) if r["ticker"] == ticker)
        return (net if side == "yes" else -net) >= contracts - 1e-9

    def renew(self) -> int:
        """Push each resting order's expiry forward on the exchange. A failure leaves the order to lapse,
        which is the safe direction; sync() then records what the exchange did with it."""
        renewed, failed = 0, []
        for o, expires in self._due():
            if not o["exchange_order_id"]:
                continue
            book_side, yes_price = book_order(o["side"], o["price"])
            try:
                self.client.extend_order(o["exchange_order_id"], o["ticker"], book_side, o["contracts"], yes_price, expires)
            except KalshiError as e:
                failed.append(f"{o['ticker']}: {e}"[:160])
                continue
            self._set_expiry(o["client_order_id"], expires)
            renewed += 1
        if failed:
            self.ledger.risk_event("lease_renew_failed", f"{len(failed)} order(s) left to lapse; first: {failed[0]}")
        return renewed

    def cancel_all(self, reason: str) -> None:
        self.client.cancel_all(self.subaccount)
        self.ledger.set_state(f"last_cancel_all:{self.mode}", now())
        for o in self._resting():
            self._set_status(o["client_order_id"], "cancelled")
        self.ledger.risk_event("cancel_all", reason)
        gid = self.ledger.get_state(f"order_group:{self.mode}")
        if gid:
            # Second line of defence. Orders are already cancelled; if this fails, say so loudly
            # rather than leave the ledger thinking they still rest.
            try:
                self.client.trigger_order_group(gid)
            except KalshiError as e:
                self.ledger.risk_event("order_group_trigger_failed", str(e)[:400])
                raise

    def sync(self) -> int:
        """Reconcile with the exchange, which is the source of truth for orders and fills."""
        ours = {o["client_order_id"]: o for o in self.ledger.query(
            "SELECT * FROM orders WHERE mode=? AND status IN ('resting','partial','submitting')", [self.mode])}
        if not ours:
            return 0
        oldest = min(o["created_ts"] for o in ours.values())
        by_exchange_id: dict[str, str] = {}
        for eo in self.client.orders(min_ts=oldest - 60):
            coid = eo.get("client_order_id")
            if coid not in ours:
                continue
            by_exchange_id[eo["order_id"]] = coid
            status = {"resting": "resting", "canceled": "cancelled", "executed": "filled"}.get(eo.get("status"), "resting")
            if status == "cancelled" and count(eo.get("fill_count_fp")) > 0:
                status = "partial_cancelled"
            self.ledger.execute("UPDATE orders SET status=?, exchange_order_id=?, updated_ts=? WHERE client_order_id=?",
                                [status, eo["order_id"], now(), coid])
        made = 0
        for f in self.client.fills(min_ts=oldest - 60):
            coid = by_exchange_id.get(f.get("order_id"))
            if not coid or self.ledger.one("SELECT 1 FROM fills WHERE id=?", [f["fill_id"]]):
                continue
            o = ours[coid]
            self.ledger.insert("fills", {
                "id": f["fill_id"], "client_order_id": coid, "ticker": o["ticker"], "side": o["side"],
                "price": o["price"], "contracts": count(f.get("count_fp")), "fee": dollars(f.get("fee_cost")),
                "ts": parse_ts(f.get("created_time")) or now(), "simulated": False,
            })
            made += 1
        # A 'submitting' row the exchange has never heard of was a request that never arrived.
        for coid, o in ours.items():
            if o["status"] == "submitting" and coid not in by_exchange_id.values() and now() - o["created_ts"] > 120:
                self._set_status(coid, "rejected")
        return made
