"""Which markets are worth forecasting. Plain rules, no model."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from .catalog import Quote

DAY = 86400


@dataclass
class Candidate:
    event_ticker: str
    category: str
    quotes: list[Quote]          # in-universe markets of the event
    tradable: bool               # False for shadow-only categories
    listing_age_days: float
    days_to_close: float

    @property
    def tickers(self) -> list[str]:
        return [q.ticker for q in self.quotes]


def market_reasons(q: Quote, u, now: float | None = None) -> list[str]:
    """Why a market is out of the universe; empty list means it is in."""
    now = now or time.time()
    out = []
    if q.category in u.exclude_categories:
        out.append("category_excluded")
    if q.fee_type == "flat":
        out.append("flat_fee_series")
    if not q.two_sided:
        return out + ["no_two_sided_quote"]
    if not u.mid_min <= q.mid <= u.mid_max:
        out.append("price_out_of_band")
    if q.spread > u.max_spread + 1e-9:
        out.append("spread_too_wide")
    if min(q.yes_bid_size, q.yes_ask_size) < u.min_top_size:
        out.append("book_too_thin")
    if not q.close_ts:
        out.append("no_close_time")
    else:
        days = (q.close_ts - now) / DAY
        if days < u.min_days_to_close:
            out.append("closes_too_soon")
        elif days > u.max_days_to_close:
            out.append("closes_too_late")
    return out


def candidates(quotes: list[Quote], u, now: float | None = None) -> list[Candidate]:
    """Events with at least one in-universe market, newest listings first."""
    now = now or time.time()
    by_event: dict[str, list[Quote]] = defaultdict(list)
    for q in quotes:
        if not market_reasons(q, u, now):
            by_event[q.event_ticker].append(q)
    out = []
    for event_ticker, qs in by_event.items():
        if len(qs) > u.max_markets_per_event:
            # Keep the markets nearest 50%, where a forecast can matter most.
            qs = sorted(qs, key=lambda q: abs(q.mid - 0.5))[: u.max_markets_per_event]
        q0 = qs[0]
        out.append(Candidate(
            event_ticker=event_ticker,
            category=q0.category,
            quotes=sorted(qs, key=lambda q: q.ticker),
            tradable=q0.category not in u.shadow_only_categories,
            listing_age_days=(now - min(q.open_ts or now for q in qs)) / DAY,
            days_to_close=(min(q.close_ts for q in qs) - now) / DAY,
        ))
    fresh = u.prefer_listing_age_days
    out.sort(key=lambda c: (c.listing_age_days > fresh, c.listing_age_days))
    return out
