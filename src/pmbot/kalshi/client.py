"""Thin Kalshi REST client.

Market data is public; portfolio and order endpoints need a signed request.
Prices and counts are fixed-point strings on the wire ("0.5600", "10.00");
callers get them back untouched and convert with `dollars()` / `count()`.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROD = "https://external-api.kalshi.com"
DEMO = "https://external-api.demo.kalshi.co"
API_PREFIX = "/trade-api/v2"

RETRY_STATUS = {429, 500, 502, 503, 504}


class KalshiError(Exception):
    def __init__(self, status: int, body: str, path: str):
        super().__init__(f"{status} on {path}: {body[:300]}")
        self.status = status
        self.body = body
        self.path = path

    @property
    def code(self) -> str:
        """Kalshi's machine-readable error code, e.g. `order_already_exists`."""
        try:
            body = json.loads(self.body)
            return (body.get("error") or body).get("code", "")     # both {"error": {"code"}} and {"code"} occur
        except Exception:
            return ""


def dollars(value: Any) -> float:
    """Fixed-point dollar string -> float. Empty or missing -> 0.0."""
    return float(value) if value not in (None, "") else 0.0


def count(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


class KalshiClient:
    def __init__(
        self,
        base_url: str = PROD,
        key_id: str | None = None,
        private_key_pem: bytes | None = None,
        timeout: float = 30.0,
        max_retries: int = 8,
        max_rps: float = 8.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        # Set when the key is restricted to one subaccount: every portfolio read then names it, because
        # the exchange otherwise answers for the primary account (balance, positions) or all of them.
        self.subaccount: int | None = None
        self._key = (
            serialization.load_pem_private_key(private_key_pem, password=None)
            if private_key_pem
            else None
        )
        self.max_retries = max_retries
        # Shared across threads so parallel callers stay under the exchange's rate limit.
        self._min_interval = 1.0 / max_rps
        self._next_slot = 0.0
        self._slot_lock = threading.Lock()
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "pmbot/0.1"},
        )

    @classmethod
    def from_key_file(cls, base_url: str, key_id: str, key_path: str | Path, **kw) -> "KalshiClient":
        return cls(base_url, key_id, Path(key_path).read_bytes(), **kw)

    @property
    def authenticated(self) -> bool:
        return bool(self.key_id and self._key)

    def close(self) -> None:
        self._http.close()

    # --- signing -----------------------------------------------------------

    def sign(self, timestamp_ms: str, method: str, path: str) -> str:
        """Signature over timestamp + METHOD + path (path without query string)."""
        message = f"{timestamp_ms}{method.upper()}{path.split('?')[0]}".encode()
        if isinstance(self._key, Ed25519PrivateKey):
            sig = self._key.sign(message)
        else:
            sig = self._key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )
        return base64.b64encode(sig).decode()

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self.sign(ts, method, path),
        }

    # --- transport ---------------------------------------------------------

    def _throttle(self) -> None:
        with self._slot_lock:
            wait = self._next_slot - time.monotonic()
            self._next_slot = max(self._next_slot, time.monotonic()) + self._min_interval
        if wait > 0:
            time.sleep(wait)

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        auth: bool = False,
        retry: bool = True,
    ) -> Any:
        """`retry=False` for order writes: a retried POST could double-submit."""
        full = API_PREFIX + path
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        if json is None and method in ("POST", "PUT"):
            json = {}       # the exchange rejects body-less writes with invalid_content_type
        attempts = self.max_retries if retry else 1
        for attempt in range(attempts):
            self._throttle()
            headers = self._auth_headers(method, full) if auth else {}
            try:
                r = self._http.request(method, full, params=params, json=json, headers=headers)
            except httpx.TransportError:
                if attempt == attempts - 1:
                    raise
                time.sleep(min(0.5 * 2**attempt, 15))
                continue
            if r.status_code in RETRY_STATUS and attempt < attempts - 1:
                # Kalshi sends no Retry-After on 429.
                time.sleep(min(1.0 * 2**attempt, 30))
                continue
            if r.status_code >= 400:
                raise KalshiError(r.status_code, r.text, path)
            return r.json() if r.content else None
        raise KalshiError(0, "retries exhausted", path)

    def get(self, path: str, auth: bool = False, **params) -> Any:
        return self.request("GET", path, params=params, auth=auth)

    def paginate(self, path: str, key: str, auth: bool = False, max_pages: int | None = None, **params) -> Iterator[dict]:
        cursor, pages = None, 0
        while True:
            data = self.get(path, auth=auth, cursor=cursor, **params)
            yield from data.get(key) or []
            cursor = data.get("cursor")
            pages += 1
            if not cursor or (max_pages and pages >= max_pages):
                return

    # --- public market data ------------------------------------------------

    def exchange_status(self) -> dict:
        return self.get("/exchange/status")

    def series_list(self, **params) -> list[dict]:
        return self.get("/series", **params)["series"]

    def events(self, status: str = "open", with_nested_markets: bool = True, **params) -> Iterator[dict]:
        """Non-multivariate events (parlays are excluded by this endpoint)."""
        return self.paginate(
            "/events", "events", status=status, limit=200,
            with_nested_markets=str(with_nested_markets).lower(), **params,
        )

    def markets(self, **params) -> Iterator[dict]:
        params.setdefault("limit", 1000)
        return self.paginate("/markets", "markets", **params)

    def market(self, ticker: str) -> dict:
        return self.get(f"/markets/{ticker}")["market"]

    def orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self.get(f"/markets/{ticker}/orderbook", depth=depth)

    def trades(self, historical: bool = False, **params) -> Iterator[dict]:
        params.setdefault("limit", 1000)
        path = "/historical/trades" if historical else "/markets/trades"
        return self.paginate(path, "trades", **params)

    def historical_cutoff(self) -> dict:
        return self.get("/historical/cutoff")

    def incentive_programs(self, **params) -> Iterator[dict]:
        return self.paginate("/incentive_programs", "incentive_programs", **params)

    # --- portfolio (signed) ------------------------------------------------

    def _own(self, params: dict) -> dict:
        if self.subaccount is not None:
            params.setdefault("subaccount", self.subaccount)
        return params

    def balance(self) -> dict:
        return self.get("/portfolio/balance", auth=True, **self._own({}))

    def positions(self, **params) -> Iterator[dict]:
        return self.paginate("/portfolio/positions", "market_positions", auth=True, **self._own(params))

    def orders(self, **params) -> Iterator[dict]:
        return self.paginate("/portfolio/orders", "orders", auth=True, **self._own(params))

    def fills(self, **params) -> Iterator[dict]:
        return self.paginate("/portfolio/fills", "fills", auth=True, **self._own(params))

    def settlements(self, **params) -> Iterator[dict]:
        return self.paginate("/portfolio/settlements", "settlements", auth=True, **self._own(params))

    # --- orders (signed, V2) -----------------------------------------------

    def create_order(
        self,
        ticker: str,
        side: str,
        count: int,
        price: float,
        client_order_id: str,
        post_only: bool = True,
        expiration_ts: int | None = None,
        order_group_id: str | None = None,
        subaccount: int | None = None,
        time_in_force: str = "good_till_canceled",
        reduce_only: bool = False,
    ) -> dict:
        """`side` is YES-book vocabulary: "bid" buys YES, "ask" sells YES (= buys NO at 1 - price)."""
        if side not in ("bid", "ask"):
            raise ValueError("side must be 'bid' or 'ask'")
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "count": f"{count:.2f}",
            "price": f"{price:.4f}",
            "client_order_id": client_order_id,
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "post_only": post_only,
            "cancel_order_on_pause": True,
            "reduce_only": reduce_only,
        }
        if expiration_ts:
            body["expiration_time"] = expiration_ts
        if order_group_id:
            body["order_group_id"] = order_group_id
        if subaccount is not None:
            body["subaccount"] = subaccount
        return self.request("POST", "/portfolio/events/orders", json=body, auth=True, retry=False)

    def extend_order(self, order_id: str, ticker: str, side: str, count: float, price: float, expiration_ts: int) -> dict:
        """Move an order's expiry. Price and total size are resent unchanged, which keeps its queue position."""
        body = {"ticker": ticker, "side": side, "count": f"{count:.2f}", "price": f"{price:.4f}", "expiration_time": expiration_ts}
        return self.request("POST", f"/portfolio/events/orders/{order_id}/amend", json=body, auth=True, retry=False)

    def cancel_order(self, order_id: str) -> Any:
        return self.request("DELETE", f"/portfolio/events/orders/{order_id}", auth=True)

    def cancel_all(self, subaccount: int | None = None) -> Any:
        return self.request("DELETE", "/portfolio/events/orders", params={"subaccount": subaccount}, auth=True)

    def create_order_group(self, contracts_limit: int, subaccount: int | None = None) -> dict:
        body: dict[str, Any] = {"contracts_limit": contracts_limit}
        if subaccount is not None:
            body["subaccount"] = subaccount
        return self.request("POST", "/portfolio/order_groups/create", json=body, auth=True, retry=False)

    def trigger_order_group(self, order_group_id: str) -> Any:
        """Kill switch: cancels every order in the group and blocks new ones until reset."""
        return self.request("PUT", f"/portfolio/order_groups/{order_group_id}/trigger", auth=True)

    def reset_order_group(self, order_group_id: str) -> Any:
        return self.request("PUT", f"/portfolio/order_groups/{order_group_id}/reset", auth=True)
