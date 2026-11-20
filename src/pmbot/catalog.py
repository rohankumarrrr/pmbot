"""Market catalog: pull open events and markets from Kalshi into the ledger."""

from __future__ import annotations

import datetime as dt
import hashlib
import sys
from dataclasses import dataclass, field

from .kalshi.client import KalshiClient, count, dollars
from .ledger.db import Ledger, now


def ts(value: str | None) -> int | None:
    if not value:
        return None
    return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


@dataclass(slots=True)     # about 200,000 of these are held at once, so no per-object dict
class Quote:
    ticker: str
    event_ticker: str
    series_ticker: str
    category: str
    fee_type: str
    fee_multiplier: float
    title: str
    yes_sub_title: str
    mutually_exclusive: bool
    n_event_markets: int
    yes_bid: float
    yes_ask: float
    yes_bid_size: float
    yes_ask_size: float
    last_price: float
    volume: float
    volume_24h: float
    open_interest: float
    open_ts: int | None
    close_ts: int | None
    expected_expiration_ts: int | None
    can_close_early: bool
    rules: str               # empty after the catalog pull; attach_rules() fills it for the few markets being forecast
    price_ranges: list[tuple[float, float, float]] = field(default_factory=list)   # (start, end, step)
    previous_price: float = 0.0    # last trade price a day earlier; 0 if none

    def tick(self, price: float) -> float:
        """Minimum price increment at this price level."""
        for start, end, step in self.price_ranges:
            if start - 1e-9 <= price < end + 1e-9:
                return step
        return 0.01

    @property
    def decides_ts(self) -> int | None:
        """When the outcome is expected to be known: the earlier of the close and the expected expiration.
        Daily markets can stay open a week past the day that decides them; the close alone hid that, and
        the live bot bid on gas-price buckets whose answer was hours away (2026-11-20)."""
        times = [t for t in (self.close_ts, self.expected_expiration_ts) if t]
        return min(times) if times else None

    @property
    def two_sided(self) -> bool:
        return 0.0 < self.yes_bid < self.yes_ask < 1.0

    @property
    def mid(self) -> float:
        return (self.yes_bid + self.yes_ask) / 2

    @property
    def spread(self) -> float:
        return self.yes_ask - self.yes_bid


def rules_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def sync_series(client: KalshiClient, ledger: Ledger) -> dict[str, dict]:
    rows = client.series_list()
    stamp = now()
    ledger.insert_many("series", [
        {"ticker": s["ticker"], "title": s.get("title"), "category": s.get("category"),
         "frequency": s.get("frequency"), "fee_type": s.get("fee_type"),
         "fee_multiplier": s.get("fee_multiplier"), "tags": s.get("tags") or [], "updated_ts": stamp}
        for s in rows
    ], replace=True)
    return {s["ticker"]: s for s in rows}


def load_series(ledger: Ledger) -> dict[str, dict]:
    return {r["ticker"]: dict(r) for r in ledger.query("SELECT * FROM series")}


def _known(ledger: Ledger) -> tuple[set[str], set[str]]:
    """(event tickers, market tickers) already in the ledger. Read once per process, then kept up to date."""
    cache = getattr(ledger, "_catalog_known", None)
    if cache is None:
        cache = ({r["event_ticker"] for r in ledger.query("SELECT event_ticker FROM events")},
                 {r["ticker"] for r in ledger.query("SELECT ticker FROM markets")})
        ledger._catalog_known = cache
    return cache


def pull_open_quotes(client: KalshiClient, ledger: Ledger, series: dict[str, dict] | None = None) -> list[Quote]:
    """Every open market in a non-parlay event, with the event and market rows upserted.

    The catalog is about 200,000 markets, so this is written to stay small in memory: rows go to the
    ledger in batches as pages arrive, rules text (most of the bytes) is stored but not kept on the
    quotes, and values that repeat across markets are shared. That took a cycle's peak memory from
    about 980 MB to about 500 MB, which is what lets the bot run on a 1 GB server.
    """
    series = series or load_series(ledger) or sync_series(client, ledger)
    stamp = now()
    quotes: list[Quote] = []
    event_rows, market_rows = [], []
    shared_ranges: dict[tuple, list[tuple[float, float, float]]] = {}
    # Rows already in the ledger are never rewritten (first_seen_ts is kept), so only new ones are
    # built and sent. Writing all 200,000 every cycle was about 40% of the cycle's CPU time.
    known_events, known_markets = _known(ledger)

    def flush() -> None:
        ledger.insert_many("events", event_rows)
        ledger.insert_many("markets", market_rows)  # INSERT OR IGNORE keeps first_seen_ts
        event_rows.clear()
        market_rows.clear()

    for ev in client.events(status="open", with_nested_markets=True):
        markets = [m for m in ev.get("markets") or [] if m.get("status") == "active" and m.get("market_type") == "binary"]
        if not markets:
            continue
        ser = series.get(ev["series_ticker"], {})
        event_ticker, series_ticker = sys.intern(ev["event_ticker"]), sys.intern(ev["series_ticker"])
        category = sys.intern(ser.get("category") or ev.get("category") or "")
        fee_type = sys.intern(ser.get("fee_type") or "quadratic")
        fee_multiplier = float(ser.get("fee_multiplier") or 1.0)
        if event_ticker not in known_events:
            known_events.add(event_ticker)
            event_rows.append({
                "event_ticker": event_ticker, "series_ticker": series_ticker, "title": ev.get("title"),
                "sub_title": ev.get("sub_title"), "mutually_exclusive": ev.get("mutually_exclusive"),
                "first_seen_ts": stamp,
            })
        for m in markets:
            ranges = tuple((float(r["start"]), float(r["end"]), float(r["step"])) for r in m.get("price_ranges") or [])
            q = Quote(
                ticker=m["ticker"], event_ticker=event_ticker, series_ticker=series_ticker,
                category=category, fee_type=fee_type, fee_multiplier=fee_multiplier,
                title=m.get("title") or ev.get("title") or "", yes_sub_title=m.get("yes_sub_title") or "",
                mutually_exclusive=bool(ev.get("mutually_exclusive")), n_event_markets=len(markets),
                yes_bid=dollars(m.get("yes_bid_dollars")), yes_ask=dollars(m.get("yes_ask_dollars")),
                yes_bid_size=count(m.get("yes_bid_size_fp")), yes_ask_size=count(m.get("yes_ask_size_fp")),
                last_price=dollars(m.get("last_price_dollars")), volume=count(m.get("volume_fp")),
                volume_24h=count(m.get("volume_24h_fp")), open_interest=count(m.get("open_interest_fp")),
                open_ts=ts(m.get("open_time")), close_ts=ts(m.get("close_time")),
                expected_expiration_ts=ts(m.get("expected_expiration_time")),
                can_close_early=bool(m.get("can_close_early")), rules="",
                price_ranges=shared_ranges.setdefault(ranges, list(ranges)),
                previous_price=dollars(m.get("previous_price_dollars")),
            )
            quotes.append(q)
            if q.ticker in known_markets:
                continue
            known_markets.add(q.ticker)
            market_rows.append({
                "ticker": q.ticker, "event_ticker": q.event_ticker, "series_ticker": q.series_ticker,
                "title": q.title, "yes_sub_title": q.yes_sub_title, "rules_primary": m.get("rules_primary"),
                "rules_secondary": m.get("rules_secondary"), "open_ts": q.open_ts, "close_ts": q.close_ts,
                "expected_expiration_ts": q.expected_expiration_ts, "can_close_early": q.can_close_early,
                "status": "active", "result": None, "settlement_ts": None,
                "first_seen_ts": stamp, "updated_ts": stamp,
            })
        if len(market_rows) >= 2000:
            flush()
    flush()
    return quotes


def attach_rules(client: KalshiClient, quotes: list[Quote]) -> None:
    """Fill in the exchange's current rules text for a few markets (the ones about to be forecast)."""
    live = {m["ticker"]: m for m in client.get("/markets", tickers=",".join(q.ticker for q in quotes), limit=1000).get("markets") or []}
    for q in quotes:
        m = live.get(q.ticker) or {}
        q.rules = "\n\n".join(x for x in (m.get("rules_primary"), m.get("rules_secondary")) if x)


def snapshot(ledger: Ledger, quotes: list[Quote], stamp: int | None = None) -> None:
    stamp = stamp or now()
    ledger.insert_many("snapshots", [
        {"ticker": q.ticker, "ts": stamp, "yes_bid": q.yes_bid, "yes_ask": q.yes_ask,
         "yes_bid_size": q.yes_bid_size, "yes_ask_size": q.yes_ask_size, "last_price": q.last_price,
         "volume": q.volume, "volume_24h": q.volume_24h, "open_interest": q.open_interest}
        for q in quotes
    ])


def sync_settlements(client: KalshiClient, ledger: Ledger, tickers: list[str]) -> int:
    """Refresh status and result for markets we hold an interest in. Returns how many settled."""
    settled = 0
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i + 40]
        found = {m["ticker"]: m for m in client.get("/markets", tickers=",".join(chunk), limit=1000).get("markets") or []}
        missing = [t for t in chunk if t not in found]
        if missing:
            hist = client.get("/historical/markets", tickers=",".join(missing), limit=1000).get("markets") or []
            found.update({m["ticker"]: m for m in hist})
        for t, m in found.items():
            result = m.get("result") or None
            ledger.execute(
                "UPDATE markets SET status=?, result=?, settlement_ts=?, updated_ts=? WHERE ticker=?",
                [m.get("status"), result, ts(m.get("settlement_ts")), now(), t],
            )
            settled += result in ("yes", "no")
    return settled
