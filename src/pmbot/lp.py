"""Liquidity provision for Kalshi's Liquidity Incentive Program.

Kalshi pays a daily pool per market to resting orders near the top of the
book. This module scores live order books the way the program does, picks the
(market, side) quotes with the best reward per dollar at risk, and keeps
orders resting there.

Program rules (Kalshi CFTC filing, "Liquidity Incentive Program", and help centre):
- one snapshot per second while the market is open; it counts only when BOTH
  sides hold at least Target Size of resting orders
- qualifying bids on a side: walk down from the best bid, taking whole price
  levels, until cumulative size reaches Target Size
- reference price: the level where cumulative size first reaches Target Size / 5
- score(bid) = size x discount^(ticks below the reference); 1.0x at or above it
- each side's scores are normalised to sum to 1; a user's snapshot score is the
  sum of their normalised scores on both sides
- reward = pool x (user's total score / everyone's total score) x (share of
  snapshots that counted). Minimum payout $1 per program.

A NO bid at q is a YES ask at 1 - q, so "both sides" means YES bids and NO bids.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .catalog import Quote
from .kalshi.client import KalshiClient

DAY = 86400
Levels = list[tuple[float, float]]     # (price, size), best price first


@dataclass
class Program:
    ticker: str
    series_ticker: str
    reward_day: float       # dollars per day for the whole market
    target: float
    discount: float
    start_ts: float
    end_ts: float


@dataclass
class SideScore:
    qualifies: bool
    score: float            # sum of qualifying scores on this side
    ref: float | None       # reference price
    best: float | None
    depth: float


def _ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_programs(client: KalshiClient) -> dict[str, Program]:
    """Active liquidity programs by market. Overlapping programs on one market are summed."""
    out: dict[str, Program] = {}
    cursor = None
    while True:
        data = client.get("/incentive_programs", status="active", type="liquidity", limit=1000, cursor=cursor)
        for p in data.get("incentive_programs") or []:
            start, end = _ts(p["start_date"]), _ts(p["end_date"])
            per_day = p["period_reward"] / 10000 / max((end - start) / DAY, 1 / 24)   # centi-cents -> dollars
            prog = Program(p["market_ticker"], p.get("series_ticker", ""), per_day, float(p.get("target_size_fp") or 0),
                           (p.get("discount_factor_bps") or 10000) / 10000, start, end)
            if prog.ticker in out:
                out[prog.ticker].reward_day += prog.reward_day
                out[prog.ticker].end_ts = min(out[prog.ticker].end_ts, prog.end_ts)
            else:
                out[prog.ticker] = prog
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def fetch_books(client: KalshiClient, tickers: list[str]) -> dict[str, tuple[Levels, Levels]]:
    """ticker -> (yes bids, no bids), each best-first."""
    out = {}
    for i in range(0, len(tickers), 100):
        data = client.request("GET", "/markets/orderbooks", params={"tickers": tickers[i:i + 100]})
        for ob in data.get("orderbooks") or []:
            book = ob.get("orderbook_fp") or {}
            out[ob["ticker"]] = tuple(
                sorted(((float(p), float(s)) for p, s in book.get(side) or []), reverse=True)
                for side in ("yes_dollars", "no_dollars"))
    return out


def with_order(levels: Levels, price: float, size: float) -> Levels:
    """The book with one more order resting at `price`."""
    out, placed = [], False
    for p, s in levels:
        if abs(p - price) < 1e-9:
            out.append((p, s + size))
            placed = True
        else:
            if not placed and p < price:
                out.append((price, size))
                placed = True
            out.append((p, s))
    if not placed:
        out.append((price, size))
    return out


def score_side(levels: Levels, target: float, discount: float, tick: float) -> SideScore:
    depth = sum(s for _, s in levels)
    best = levels[0][0] if levels else None
    if not levels or depth < target:
        return SideScore(False, 0.0, None, best, depth)
    qualifying, cum, ref = [], 0.0, None
    for price, size in levels:
        qualifying.append((price, size))
        cum += size
        if ref is None and cum >= target / 5:
            ref = price
        if cum >= target:
            break
    score = sum(size * weight(price, ref, discount, tick) for price, size in qualifying)
    return SideScore(True, score, ref, best, depth)


def weight(price: float, ref: float, discount: float, tick: float) -> float:
    return discount ** max(0.0, round((ref - price) / tick))


def my_share(levels: Levels, target: float, discount: float, tick: float, price: float, size: float,
             already_in_book: bool) -> float:
    """Share of one side's score earned by `size` contracts resting at `price`.

    In shadow mode the order is not really in the book, so it is added before
    scoring (which can move the reference price and the qualifying set, exactly
    as a real order would). In live mode the book already contains it.
    """
    book = levels if already_in_book else with_order(levels, price, size)
    side = score_side(book, target, discount, tick)
    if not side.qualifies or side.score <= 0:
        return 0.0
    # The order qualifies only if its level is among those needed to reach Target Size.
    cum = 0.0
    for p, s in book:
        if p < price - 1e-9:
            return 0.0
        cum += s
        if abs(p - price) < 1e-9:
            break
        if cum >= target:
            return 0.0
    return size * weight(price, side.ref, discount, tick) / side.score


@dataclass
class SideQuote:
    ticker: str
    side: str               # 'yes' / 'no'
    price: float
    contracts: int
    share: float            # of this side's score
    reward_day: float       # expected dollars per day from this order
    at_risk: float          # dollars lost if it fills and the market goes fully against it
    queue_ahead: float

    @property
    def yield_day(self) -> float:
        return self.reward_day / self.at_risk if self.at_risk else 0.0

    def net_yield_day(self, lp) -> float:
        """Reward yield plus the expected daily cost (or gain) of being filled at this price."""
        return self.yield_day + lp.fill_prob_day * fill_return(self.price, lp)


def fill_return(price: float, lp) -> float:
    for below, ret in lp.fill_return:
        if price < below:
            return ret
    return 0.0


def plan_market(prog: Program, q: Quote, book: tuple[Levels, Levels], contracts: int, lp, now: float,
                in_book: dict[str, tuple[float, float]] | None = None) -> list[SideQuote]:
    """Candidate quotes for one market: at most one per side, resting at the reference price.

    Quoting at the reference rather than the best price earns the same full
    weight while standing behind whatever is ahead in the queue.
    `in_book` maps side -> (price, size) of our own orders already in this book (live mode).
    """
    tick = q.tick(q.mid if q.two_sided else 0.5)
    yes, no = book
    if not yes or not no:
        return []
    sy, sn = score_side(yes, prog.target, prog.discount, tick), score_side(no, prog.target, prog.discount, tick)
    if not (sy.qualifies and sn.qualifies):
        return []          # snapshot would not count; no reward to earn
    out = []
    for side, levels, s in (("yes", yes, sy), ("no", no, sn)):
        price = s.ref
        # Never cross: our bid on one side must stay below the other side's implied ask.
        other_best = (sn if side == "yes" else sy).best
        if price + other_best >= 1.0 - 1e-9:
            continue
        mine = (in_book or {}).get(side)
        share = (my_share(levels, prog.target, prog.discount, tick, mine[0], mine[1], True) if mine
                 else my_share(levels, prog.target, prog.discount, tick, price, contracts, False))
        queue = sum(sz for p, sz in levels if abs(p - price) < 1e-9)
        # Each side carries half of the snapshot's total score of 2.
        out.append(SideQuote(prog.ticker, side, price, contracts, share, prog.reward_day * share / 2,
                             price * contracts, queue))
    return out


def market_reasons(prog: Program, q: Quote, lp, now: float, committed: bool = False) -> list[str]:
    """Why a program market is not quoted; empty means it is eligible.

    `committed` is a market already quoted in the program's current period. It is not dropped for
    the program nearing its end: the share earned there pays only if it reaches $1 by the end, so
    leaving in the last hours forfeits it. Only a new market is kept out of a program about to end.
    """
    out = []
    if q.category in lp.exclude_categories:
        out.append("category_excluded")
    if any(q.ticker.startswith(prefix) for prefix in lp.get("exclude_families") or []):
        out.append("family_paused")             # switched off by hand (`pmbot pause`); also pulls quotes already resting
    if q.exchange_index not in lp.get("exchange_indexes", [0]):
        out.append("other_exchange_shard")      # the account holds no cash there, so the order would be refused
    if q.fee_type != "quadratic":
        out.append("maker_fee_series")          # a maker fee would come out of every fill
    if not q.decides_ts or (q.decides_ts - now) / 3600 < lp.min_hours_to_close:
        out.append("closes_too_soon")           # the final stretch is when informed flow arrives
    if not committed and (prog.end_ts - now) / 3600 < lp.min_hours_left_in_program:
        out.append("program_ending")
    if q.two_sided and q.previous_price and abs(q.mid - q.previous_price) > lp.max_day_move:
        out.append("price_moving")              # repricing in progress: stale quotes get picked off
    if q.volume_24h > lp.max_volume_24h:
        out.append("too_active")
    return out


MIN_PAYOUT = 1.0     # Kalshi issues no payout under $1 for a program's period


def worth_staying(accrued: float, net_yield_day: float, at_risk: float, days_left: float, lp) -> bool:
    """Whether to keep quoting a program where the reward no longer covers the expected fill cost.

    What is already earned there is lost if the bot leaves before the program reaches $1. So with
    `lp.keep_committed_while_accrued` on, a quote stays while the expected loss from resting to the end
    of the period (a negative net yield, on the dollars at risk, for the days left) is smaller than what
    leaving would forfeit. Once the program is past $1 nothing is forfeited, and the plain rule applies.
    The caller checks separately that the program can still reach $1.
    """
    if not lp.get("keep_committed_while_accrued") or not 0 < accrued < MIN_PAYOUT:
        return False
    return net_yield_day * at_risk * days_left + accrued >= 0


def resized(sq: SideQuote, contracts: int, prog: Program, q: Quote, book: tuple[Levels, Levels]) -> SideQuote:
    """The same quote at another size, with the share of the reward that size would earn."""
    tick = q.tick(q.mid if q.two_sided else 0.5)
    levels = book[0] if sq.side == "yes" else book[1]
    share = my_share(levels, prog.target, prog.discount, tick, sq.price, contracts, False)
    return SideQuote(sq.ticker, sq.side, sq.price, contracts, share, prog.reward_day * share / 2,
                     sq.price * contracts, sq.queue_ahead)


def worth_quoting(sq: SideQuote, prog: Program, lp, now: float, accrued: float, committed: bool) -> bool:
    """Whether a quote of this size earns its place: the program can reach its payout, and the reward covers the fills.

    A program pays nothing below $1 for the period, so what is already earned there (`accrued`) plus what
    this quote would add by the end has to clear it: with a margin for a new market, exactly for a
    `committed` one (already quoted this period).
    """
    days_left = max((prog.end_ts - now) / DAY, 0)
    floor = MIN_PAYOUT if committed else lp.min_expected_payout
    if accrued + sq.reward_day * days_left < floor:
        return False
    net = sq.net_yield_day(lp)
    return net >= lp.min_yield_day or (committed and worth_staying(accrued, net, sq.at_risk, days_left, lp))


def family(ticker: str, lp) -> str:
    """Markets that tend to move on the same news: the first letters of the series name.

    KXAAAGASCDAK-26NOV21-T3.2 and KXAAAGASCDTX-26NOV21-T2.9 (gas prices in two states) are both KXAAAGAS.
    It is a crude grouping, kept simple on purpose: it is used to cap how many markets of one kind are quoted.
    """
    return ticker.split("-")[0][: int(lp.get("family_prefix_len", 8))]


def rank(programs: dict[str, Program], quotes: dict[str, Quote], books: dict[str, tuple[Levels, Levels]],
         lp, bankroll: float, now: float, accrued: dict[str, float] | None = None,
         committed: set[str] | None = None) -> list[SideQuote]:
    """Every eligible side quote, best net yield (reward less expected fill cost) per dollar at risk first.

    `accrued` is what the account has already earned (estimated) in each program's current period.
    `committed` are markets already quoted this period: they only have to reach the payout floor itself,
    while a new market has to clear it with a margin.
    """
    accrued, committed = accrued or {}, committed or set()
    out: list[SideQuote] = []
    for ticker, prog in programs.items():
        q, book = quotes.get(ticker), books.get(ticker)
        if q is None or book is None or market_reasons(prog, q, lp, now, ticker in committed):
            continue
        for sq in plan_market(prog, q, book, lp.contracts_per_side, lp, now):
            if sq.price < lp.get("min_bid_price", 0) - 1e-9:
                continue        # a bid this cheap is only ever filled by someone unloading a nearly worthless contract
            # Size down expensive sides so no single quote risks more than the per-quote cap.
            cap = lp.max_at_risk_per_quote
            if sq.at_risk > cap:
                n = int(cap // sq.price)
                if n < lp.min_contracts:
                    continue
                sq = resized(sq, n, prog, q, book)
            if worth_quoting(sq, prog, lp, now, accrued.get(ticker, 0.0), ticker in committed):
                out.append(sq)
    out.sort(key=lambda s: -s.net_yield_day(lp))
    return out
