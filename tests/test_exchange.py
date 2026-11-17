"""KalshiBroker against an in-process fake exchange: signing, idempotency, crash recovery, kill switch."""

import base64
import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pmbot.execution.brokers import KalshiBroker, client_order_id
from pmbot.kalshi.client import KalshiClient, KalshiError
from pmbot.ledger.db import Ledger

P = "/trade-api/v2"


class FakeExchange:
    """Just enough of Kalshi's order API to exercise the broker, with real signature checks."""

    def __init__(self, public_key):
        self.public_key = public_key
        self.orders: dict[str, dict] = {}      # order_id -> order
        self.fills: list[dict] = []
        self.group_triggered = False
        self.fail_next_create: str | None = None   # 'drop' = accept the order but lose the response
        self.requests: list[tuple[str, str]] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.requests.append((req.method, path))
        ts, sig = req.headers.get("KALSHI-ACCESS-TIMESTAMP"), req.headers.get("KALSHI-ACCESS-SIGNATURE")
        try:
            self.public_key.verify(base64.b64decode(sig), f"{ts}{req.method}{path}".encode())
        except Exception:
            return httpx.Response(401, json={"error": {"code": "invalid_signature"}})
        if abs(time.time() * 1000 - int(ts)) > 30_000:
            return httpx.Response(401, json={"error": {"code": "header_timestamp_expired"}})
        if req.method in ("POST", "PUT") and "application/json" not in req.headers.get("content-type", ""):
            return httpx.Response(400, json={"code": "invalid_content_type", "message": "invalid_content_type"})

        if req.method == "POST" and path == f"{P}/portfolio/order_groups/create":
            return httpx.Response(201, json={"order_group_id": "grp-1"})
        if req.method == "PUT" and path == f"{P}/portfolio/order_groups/grp-1/trigger":
            self.group_triggered = True
            self._cancel_everything()
            return httpx.Response(200, json={})
        if req.method == "POST" and path == f"{P}/portfolio/events/orders":
            body = json.loads(req.content)
            if any(o["client_order_id"] == body["client_order_id"] and o["status"] == "resting" for o in self.orders.values()):
                return httpx.Response(409, json={"error": {"code": "order_already_exists"}})
            if self.group_triggered:
                return httpx.Response(400, json={"error": {"code": "exceeded_order_group_contracts_limit"}})
            assert body["post_only"] is True and body["order_group_id"] == "grp-1"
            oid = f"ord-{len(self.orders) + 1}"
            self.orders[oid] = {"order_id": oid, "client_order_id": body["client_order_id"], "ticker": body["ticker"],
                                "book_side": body["side"], "yes_price_dollars": body["price"], "status": "resting",
                                "fill_count_fp": "0.00", "initial_count_fp": body["count"]}
            if self.fail_next_create == "drop":
                self.fail_next_create = None
                raise httpx.ReadTimeout("response lost", request=req)
            return httpx.Response(201, json={"order_id": oid, "client_order_id": body["client_order_id"],
                                             "fill_count": "0.00", "remaining_count": body["count"], "ts_ms": 1})
        if req.method == "DELETE" and path == f"{P}/portfolio/events/orders":
            self._cancel_everything()
            return httpx.Response(204)
        if req.method == "DELETE" and path.startswith(f"{P}/portfolio/events/orders/"):
            oid = path.rsplit("/", 1)[1]
            if oid not in self.orders:
                return httpx.Response(404, json={"error": {"code": "not_found"}})
            self.orders[oid]["status"] = "canceled"
            return httpx.Response(200, json={})
        if req.method == "GET" and path == f"{P}/portfolio/orders":
            want = req.url.params.get("status")
            return httpx.Response(200, json={"orders": [o for o in self.orders.values() if not want or o["status"] == want],
                                             "cursor": ""})
        if req.method == "GET" and path == f"{P}/portfolio/fills":
            return httpx.Response(200, json={"fills": self.fills, "cursor": ""})
        return httpx.Response(404, json={"error": {"code": "no_route", "path": path}})

    def _cancel_everything(self):
        for o in self.orders.values():
            if o["status"] == "resting":
                o["status"] = "canceled"

    def execute(self, order_id: str, count: float, fee: str = "0.0000"):
        o = self.orders[order_id]
        o["status"], o["fill_count_fp"] = "executed", f"{count:.2f}"
        self.fills.append({"fill_id": f"fill-{len(self.fills) + 1}", "order_id": order_id, "ticker": o["ticker"],
                           "count_fp": f"{count:.2f}", "fee_cost": fee, "created_time": "2026-11-16T12:00:00Z"})


@pytest.fixture
def rig():
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    exchange = FakeExchange(key.public_key())
    client = KalshiClient("https://fake.exchange", "key-1", pem, max_rps=1000)
    client._http = httpx.Client(base_url="https://fake.exchange", transport=httpx.MockTransport(exchange.handler))
    ledger = Ledger(":memory:")
    ledger.insert("markets", {"ticker": "T-1", "event_ticker": "T", "series_ticker": "S", "status": "active"})
    return exchange, KalshiBroker(ledger, client, "demo"), ledger


def status(ledger, decision):
    return ledger.one("SELECT status FROM orders WHERE client_order_id=?", [client_order_id(decision)])["status"]


def test_signed_order_rests_and_buying_no_becomes_a_yes_ask(rig):
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "no", 0.60, 10, 3600)
    (order,) = exchange.orders.values()
    assert (order["book_side"], order["yes_price_dollars"], order["initial_count_fp"]) == ("ask", "0.4000", "10.00")
    assert status(ledger, "d1") == "resting"


def test_bad_signature_is_rejected(rig):
    exchange, broker, ledger = rig
    exchange.public_key = Ed25519PrivateKey.generate().public_key()
    assert broker.place("d1", "T-1", "yes", 0.40, 10, 3600) is None
    assert not exchange.orders


def test_replaying_a_decision_sends_one_order(rig):
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    assert len(exchange.orders) == 1


def test_order_writes_are_never_retried(rig):
    exchange, broker, ledger = rig
    exchange.fail_next_create = "drop"
    with pytest.raises(httpx.ReadTimeout):
        broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    creates = [r for r in exchange.requests if r == ("POST", f"{P}/portfolio/events/orders")]
    assert len(creates) == 1


def test_crash_after_submit_is_recovered_by_reconciliation(rig):
    """The exchange accepted the order but we never saw the reply: the ledger row must not stay orphaned."""
    exchange, broker, ledger = rig
    exchange.fail_next_create = "drop"
    with pytest.raises(httpx.ReadTimeout):
        broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    assert status(ledger, "d1") == "submitting"
    broker.sync()
    assert status(ledger, "d1") == "resting"
    assert ledger.one("SELECT exchange_order_id FROM orders")["exchange_order_id"] == "ord-1"
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)      # restart replays the decision
    assert len(exchange.orders) == 1


def test_fills_are_ingested_once(rig):
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    exchange.execute("ord-1", 10)
    assert broker.sync() == 1
    assert broker.sync() == 0
    row = ledger.one("SELECT side, price, contracts, simulated FROM fills")
    assert (row["side"], row["price"], row["contracts"], row["simulated"]) == ("yes", 0.40, 10, 0)
    assert status(ledger, "d1") == "filled"


def test_kill_switch_cancels_on_exchange_and_blocks_new_orders(rig):
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    broker.place("d2", "T-1", "yes", 0.39, 10, 3600)
    broker.cancel_all("test")
    assert all(o["status"] == "canceled" for o in exchange.orders.values())
    assert exchange.group_triggered
    assert status(ledger, "d1") == status(ledger, "d2") == "cancelled"
    assert broker.place("d3", "T-1", "yes", 0.40, 10, 3600) is None
    assert status(ledger, "d3") == "rejected"


def test_cancelling_an_order_the_exchange_forgot_is_not_an_error(rig):
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    exchange.orders.clear()
    broker.cancel(client_order_id("d1"), "test")
    assert status(ledger, "d1") == "cancelled"


# --- self-check ---------------------------------------------------------------

def age(ledger, seconds=600):
    """Make every order old enough that listing lag no longer excuses a mismatch."""
    ledger.execute("UPDATE orders SET created_ts = created_ts - ?", [seconds])


def test_self_check_passes_when_ledger_and_exchange_agree(rig):
    from pmbot.consistency import check
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    broker.place("d2", "T-1", "no", 0.55, 10, 3600)
    exchange.execute("ord-2", 10)
    broker.sync()
    age(ledger)
    r = check(ledger, broker.client, "demo")
    assert r.ok and r.exchange_resting == 1 and r.ledger_resting == 1


def test_self_check_finds_orphans_stale_orders_and_missing_fills(rig):
    from pmbot.consistency import check
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    broker.place("d2", "T-1", "yes", 0.39, 10, 3600)
    broker.place("d3", "T-1", "yes", 0.38, 10, 3600)
    age(ledger)
    ledger.execute("UPDATE orders SET status='cancelled' WHERE client_order_id=?", [client_order_id("d1")])   # ledger forgot it
    exchange.orders["ord-2"]["status"] = "canceled"                                                            # exchange dropped it
    exchange.execute("ord-3", 10)                                                                              # filled, never synced
    r = check(ledger, broker.client, "demo")
    assert r.orphans == [client_order_id("d1")]
    assert r.stale == sorted([client_order_id("d2"), client_order_id("d3")])
    assert len(r.missing_fills) == 1 and not r.ok


def test_self_check_ignores_orders_too_new_for_the_listing_and_other_peoples_orders(rig):
    from pmbot.consistency import check
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    exchange.orders["ord-1"]["status"] = "canceled"          # looks missing, but the order is seconds old
    exchange.orders["manual"] = {"order_id": "manual", "client_order_id": "placed-by-hand", "status": "resting"}
    assert check(ledger, broker.client, "demo").ok


def test_one_bad_check_warns_and_a_second_in_a_row_halts(rig):
    from pmbot.consistency import check_and_react
    exchange, broker, ledger = rig
    broker.place("d1", "T-1", "yes", 0.40, 10, 3600)
    age(ledger)
    exchange.orders["ord-1"]["status"] = "canceled"
    assert check_and_react(ledger, broker.client, "demo")[1] is False
    assert ledger.one("SELECT COUNT(*) AS n FROM risk_events WHERE kind='consistency_warning'")["n"] == 1
    assert check_and_react(ledger, broker.client, "demo")[1] is True
    exchange.orders["ord-1"]["status"] = "resting"           # back in agreement: the streak resets
    assert check_and_react(ledger, broker.client, "demo")[1] is False
    assert ledger.get_state("inconsistent_streak:demo") == 0
