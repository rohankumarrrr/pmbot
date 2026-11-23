"""Keeps liquidity-reward quotes resting: accrue, prune, place."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict

from . import lp, overrides
from .blend import Sizing
from .catalog import Quote
from .execution.brokers import Broker
from .kalshi.client import KalshiClient
from .ledger.db import Ledger, new_id, now
from .portfolio import positions
from .risk import RiskManager

DAY = 86400
LIVE_STATUSES = "('resting','partial','submitting')"


class LiquidityProvider:
    def __init__(self, cfg, ledger: Ledger, data: KalshiClient, broker: Broker, risk: RiskManager, mode: str):
        self.cfg, self.base = cfg, dict(cfg["lp"])
        self.c = cfg.lp          # replaced at the top of every step with the settings in force (see overrides.py)
        self.ledger, self.data, self.broker, self.risk, self.mode = ledger, data, broker, risk, mode
        self._programs: dict[str, lp.Program] = {}
        self._programs_ts = 0.0
        self.cancel_reasons: Counter = Counter()
        self.trimmed_away = 0                   # quotes skipped this step because the risk limits left too small a part
        self.offered_out = 0                    # offers placed this step on positions already held
        self.earned: dict[str, float] = {}      # estimated dollars accrued per program this period; set each step

    def programs(self) -> dict[str, lp.Program]:
        if time.time() - self._programs_ts > self.c.refresh_programs_minutes * 60:
            self._programs = lp.load_programs(self.data)
            self._programs_ts = time.time()
        return self._programs

    def synthetic_programs(self, by_ticker: dict[str, Quote], stamp: float) -> dict[str, lp.Program]:
        """Demo exchange only: stand-in programs so the strategy has something to quote."""
        syn = self.c.get("synthetic_programs")
        if self.mode != "demo" or not syn:
            return {}
        busiest = sorted((q for q in by_ticker.values() if q.two_sided), key=lambda q: -q.volume_24h)
        keep = {o["ticker"] for o in self.my_orders()}     # keep managing what we already quote
        picked = [q for q in busiest if not lp.market_reasons(
            lp.Program(q.ticker, q.series_ticker, 0, 0, 0, 0, stamp + 30 * DAY), q, self.c, stamp)][: syn["max_markets"]]
        return {t: lp.Program(t, by_ticker[t].series_ticker, syn["reward_day"], syn["target"], syn["discount"],
                              stamp - DAY, stamp + 30 * DAY)
                for t in {q.ticker for q in picked} | (keep & by_ticker.keys())}

    def my_orders(self) -> list:
        return self.ledger.query(
            f"""SELECT o.client_order_id, o.ticker, o.side, o.price, o.contracts, o.created_ts, d.kind,
                       o.contracts - COALESCE((SELECT SUM(f.contracts) FROM fills f WHERE f.client_order_id = o.client_order_id), 0) AS remaining
                FROM orders o JOIN decisions d ON d.id = o.decision_id
                WHERE o.mode=? AND d.strategy='lp' AND o.status IN {LIVE_STATUSES}""", [self.mode])

    def step(self, by_ticker: dict[str, Quote]) -> dict:
        stamp = time.time()
        # Settings changed from the command line take effect here, on the next cycle, with no restart.
        self.c = overrides.effective(self.base, self.ledger, self.mode)
        programs = self.programs() or self.synthetic_programs(by_ticker, stamp)
        orders = self.my_orders()
        committed = self.committed(programs)
        eligible = [t for t, p in programs.items()
                    if t in by_ticker and not lp.market_reasons(p, by_ticker[t], self.c, stamp, t in committed)]
        books = lp.fetch_books(self.data, sorted(set(eligible) | {o["ticker"] for o in orders}))
        stats = {"lp_programs": len(programs), "lp_eligible_markets": len(eligible)}
        changed = sorted(overrides.load(self.ledger, self.mode))
        if changed:
            stats["lp_settings_changed_at_run_time"] = changed
        stats["lp_accrued"] = round(self.accrue(orders, programs, by_ticker, books, stamp), 4)
        self.ledger.insert_many("lp_programs", [
            {"mode": self.mode, "ticker": t, "start_ts": int(programs[t].start_ts), "end_ts": int(programs[t].end_ts),
             "reward_day": programs[t].reward_day} for t in {o["ticker"] for o in orders} if t in programs], replace=True)
        self.earned = self.accrued(programs)
        stats["lp_cancelled"] = self.prune(orders, programs, by_ticker, books, stamp)
        if self.cancel_reasons:
            stats["lp_cancel_reasons"] = dict(self.cancel_reasons)   # logged so churn can be diagnosed
        stats["lp_placed"] = self.place(programs, by_ticker, books, stamp)
        if self.trimmed_away:
            stats["lp_too_small_after_risk_trim"] = self.trimmed_away
        if self.offered_out:
            stats["lp_offers_on_held_positions"] = self.offered_out
        self.ledger.set_state(f"lp_last_step:{self.mode}", stamp)
        return stats

    def committed(self, programs: dict[str, lp.Program]) -> set[str]:
        """Markets where an order of ours has rested during the program's current period."""
        rows = self.ledger.query(
            "SELECT o.ticker, MAX(o.created_ts) AS t FROM orders o JOIN decisions d ON d.id = o.decision_id "
            "WHERE o.mode=? AND d.strategy='lp' AND o.status != 'rejected' AND o.created_ts>? GROUP BY o.ticker",
            [self.mode, now() - 8 * DAY])
        return {r["ticker"] for r in rows if r["ticker"] in programs and r["t"] >= programs[r["ticker"]].start_ts}

    def accrued(self, programs: dict[str, lp.Program]) -> dict[str, float]:
        """Estimated dollars already earned in each program's current period, by ticker."""
        out: dict[str, float] = {}
        for r in self.ledger.query("SELECT ticker, ts, usd FROM lp_accruals WHERE mode=? AND ts>?", [self.mode, now() - 8 * DAY]):
            prog = programs.get(r["ticker"])
            if prog and r["ts"] >= prog.start_ts:
                out[r["ticker"]] = out.get(r["ticker"], 0.0) + r["usd"]
        return out

    # --- reward accounting -------------------------------------------------

    def accrue(self, orders, programs, by_ticker, books, stamp: float) -> float:
        """Credit each resting order its estimated share of the pool since the last step.

        Uses the book as it is now for the whole interval, so it is an estimate.
        """
        last = self.ledger.get_state(f"lp_last_step:{self.mode}")
        if not last:
            return 0.0
        total, rows = 0.0, []
        in_book = self.mode != "shadow"     # a shadow order is not actually in the exchange's book
        for o in orders:
            prog, q, book = programs.get(o["ticker"]), by_ticker.get(o["ticker"]), books.get(o["ticker"])
            seconds = stamp - max(last, o["created_ts"])
            if not prog or not q or not book or seconds <= 0 or o["remaining"] <= 0 or stamp > prog.end_ts:
                continue
            tick = q.tick(q.mid if q.two_sided else 0.5)
            yes, no = book
            mine, other = (yes, no) if o["side"] == "yes" else (no, yes)
            # The snapshot counts only if both sides reach Target Size (ours with our order in it).
            mine_scored = mine if in_book else lp.with_order(mine, o["price"], o["remaining"])
            if not (lp.score_side(mine_scored, prog.target, prog.discount, tick).qualifies
                    and lp.score_side(other, prog.target, prog.discount, tick).qualifies):
                continue
            share = lp.my_share(mine, prog.target, prog.discount, tick, o["price"], o["remaining"], in_book)
            usd = prog.reward_day * share / 2 * seconds / DAY
            total += usd
            rows.append({"ts": int(stamp), "mode": self.mode, "ticker": o["ticker"], "side": o["side"],
                         "client_order_id": o["client_order_id"], "seconds": seconds, "share": share, "usd": usd})
        self.ledger.insert_many("lp_accruals", rows)
        return total

    # --- order upkeep ------------------------------------------------------

    def prune(self, orders, programs, by_ticker, books, stamp: float) -> int:
        """Cancel quotes that stopped earning or drifted away from the reference price."""
        n = 0
        self.cancel_reasons = Counter()
        rate = self.reward_rates(orders, programs, by_ticker, books)
        sides = Counter(o["ticker"] for o in orders)
        held = self.exposure()[1]
        for o in orders:
            prog, q, book = programs.get(o["ticker"]), by_ticker.get(o["ticker"]), books.get(o["ticker"])
            reason, why = None, {}
            closing = o["kind"] == "lp_close"
            if closing and not self.c.get("offer_out_positions"):
                reason = "offers_switched_off"
            elif closing and o["remaining"] > held.get((o["ticker"], "no" if o["side"] == "yes" else "yes"), 0) + 1e-9:
                # The position it was closing is gone or smaller (settled, or closed another way). Left resting,
                # the rest of this order would open a position on the other side, at a size no cap ever checked.
                reason = "position_gone"
            elif not prog or not q or not book:
                reason = "program_or_market_gone"
            elif lp.market_reasons(prog, q, self.c, stamp, committed=True):      # an order here means we are committed
                reason = ",".join(lp.market_reasons(prog, q, self.c, stamp, committed=True))
            else:
                tick = q.tick(q.mid if q.two_sided else 0.5)
                levels = book[0] if o["side"] == "yes" else book[1]
                other = book[1] if o["side"] == "yes" else book[0]
                side = lp.score_side(levels if self.mode != "shadow" else lp.with_order(levels, o["price"], o["remaining"]),
                                     prog.target, prog.discount, tick)
                why = {"ref": side.ref, "best": levels[0][0] if levels else None}
                if o["price"] < self.c.get("min_bid_price", 0) - 1e-9 and not closing:
                    reason = "bid_too_cheap"
                elif not side.qualifies:
                    reason = "side_below_target"
                elif other and o["price"] + other[0][0] >= 1.0 - 1e-9:
                    reason = "would_cross"          # the other side came to us: this is now the touch
                elif abs(side.ref - o["price"]) >= self.c.requote_ticks * tick - 1e-9:
                    reason = "reference_moved"
                elif closing:
                    pass        # nothing at risk and no payout floor to reach: it rests until it fills or the price moves
                else:
                    share = lp.my_share(levels, prog.target, prog.discount, tick, o["price"], o["remaining"], self.mode != "shadow")
                    gross = prog.reward_day * share / 2 / (o["price"] * o["remaining"])
                    days_left = max((prog.end_ts - stamp) / DAY, 0)
                    net = gross + self.c.fill_prob_day * lp.fill_return(o["price"], self.c)
                    # The program's accrual is shared between our quotes there, so each side protects its part.
                    banked = self.earned.get(o["ticker"], 0.0) / max(sides.get(o["ticker"], 1), 1)
                    why.update(share=round(share, 4), gross_yield_day=round(gross, 4), net_yield_day=round(net, 4),
                               banked=round(self.earned.get(o["ticker"], 0.0), 4), days_left=round(days_left, 2),
                               program_rate_day=round(rate.get(o["ticker"], 0.0), 4))
                    if net < 0 and not lp.worth_staying(banked, net, o["price"] * o["remaining"], days_left, self.c):
                        reason = "yield_below_fill_cost"     # the pool got crowded, or the ranking rules changed
                    elif self.earned.get(o["ticker"], 0.0) + rate.get(o["ticker"], 0.0) * days_left < lp.MIN_PAYOUT:
                        reason = "cannot_reach_payout"       # resting here takes fill risk for a reward that will not be paid
            if reason:
                self.broker.cancel(o["client_order_id"], reason)
                # Kept per order: which rule pulled a quote, and on what numbers, is how a leak of rewards is traced.
                self.ledger.insert("lp_cancels", {
                    "ts": int(stamp), "mode": self.mode, "ticker": o["ticker"], "side": o["side"],
                    "client_order_id": o["client_order_id"], "price": o["price"], "contracts": o["remaining"],
                    "reason": reason, "detail": json.dumps(why)})
                self.cancel_reasons[reason] += 1
                n += 1
        return n

    def reward_rates(self, orders, programs, by_ticker, books) -> dict[str, float]:
        """Estimated dollars a day our resting orders are earning in each market, both sides together."""
        out: dict[str, float] = {}
        for o in orders:
            prog, q, book = programs.get(o["ticker"]), by_ticker.get(o["ticker"]), books.get(o["ticker"])
            if not prog or not q or not book or o["remaining"] <= 0:
                continue
            tick = q.tick(q.mid if q.two_sided else 0.5)
            levels = book[0] if o["side"] == "yes" else book[1]
            share = lp.my_share(levels, prog.target, prog.discount, tick, o["price"], o["remaining"], self.mode != "shadow")
            out[o["ticker"]] = out.get(o["ticker"], 0.0) + prog.reward_day * share / 2
        return out

    # --- placing -----------------------------------------------------------

    def exposure(self) -> tuple[float, dict[tuple[str, str], float], set[tuple[str, str]]]:
        """(dollars at risk in LP orders and inventory, contracts held by (ticker, side), sides with a live order)."""
        orders = self.my_orders()
        resting = sum(o["price"] * o["remaining"] for o in orders if o["kind"] != "lp_close")
        lp_tickers = {r["ticker"] for r in self.ledger.query(
            "SELECT DISTINCT ticker FROM decisions WHERE mode=? AND strategy='lp'", [self.mode])}
        held = {(p.ticker, p.side): p.contracts for p in positions(self.ledger, self.mode)
                if p.ticker in lp_tickers and not p.decided and p.contracts > 0}
        # A position paired off by an offer holds no contracts and ties up nothing, whatever it cost.
        inventory = sum(max(p.cost, 0.0) for p in positions(self.ledger, self.mode)
                        if p.ticker in lp_tickers and not p.decided and p.contracts > 0)
        return resting + inventory, held, {(o["ticker"], o["side"]) for o in orders}

    def place(self, programs, by_ticker, books, stamp: float) -> int:
        at_risk, held, quoted = self.exposure()
        budget = self.c.capital_fraction * self.risk.bankroll
        # Offers on held positions do not take a quote's place: they need no budget.
        slots = self.c.max_quotes - sum(1 for o in self.my_orders() if o["kind"] != "lp_close")
        placed = 0
        self.trimmed_away = self.offered_out = 0
        # A post-only order is refused when the book moved between reading it and placing the order.
        # That market is repricing; leave it alone for a while instead of trying again every cycle.
        cooling = {r["ticker"] for r in self.ledger.query(
            "SELECT DISTINCT ticker FROM orders WHERE mode=? AND status='rejected' AND created_ts>?",
            [self.mode, now() - self.c.get("reject_cooldown_hours", 6) * 3600])}
        # Stay where the account has already quoted this period: a program pays only once its share reaches
        # $1, so handing a slot to whichever market ranks best this cycle throws away what the last one earned.
        # A quote pulled because its reference moved comes straight back here at the new reference.
        committed = self.committed(programs)
        ranked = lp.rank(programs, by_ticker, books, self.c, self.risk.bankroll, stamp, self.earned, committed, held)
        # Stable sort: markets not yet quoted keep their net-yield order, after the committed ones.
        # Offers on held positions come first: they need no budget and free some when they fill.
        ranked.sort(key=lambda s: (not s.closing, s.ticker not in committed, -self.earned.get(s.ticker, 0.0)))
        # One piece of news can fill every quote in a family at once (17 gas-price markets on 2026-11-20),
        # so no family gets more than a few markets, counting the ones where a position is already held.
        family_cap = int(self.c.get("max_markets_per_family") or 0)
        in_family: dict[str, set[str]] = defaultdict(set)
        for ticker, _ in list(quoted) + list(held):
            in_family[lp.family(ticker, self.c)].add(ticker)
        for sq in ranked:
            if not sq.closing and (slots <= 0 or at_risk >= budget):
                break
            if sq.ticker in cooling:
                continue
            fam = in_family[lp.family(sq.ticker, self.c)]
            if family_cap and sq.ticker not in fam and len(fam) >= family_cap:
                continue        # this family already has its share of markets
            key = (sq.ticker, sq.side)
            if key in quoted or held.get(key, 0) >= self.c.contracts_per_side:
                continue        # already quoting, or already carrying a full position on this side
            if not sq.closing and at_risk + sq.at_risk > budget:
                continue
            q = by_ticker[sq.ticker]
            verdict = self.risk.review(Sizing(sq.side, sq.price, 0.0, 0.0, 0.0, sq.contracts), sq.ticker, q.event_ticker,
                                       closing=sq.closing)
            if set(verdict.reasons) & {"halted", "max_open_orders", "max_orders_per_hour"}:
                break           # an account-wide limit: nothing further can be placed this cycle
            if verdict.ok and verdict.contracts < sq.contracts:
                # The risk limits left room for part of this quote only (a position already held in the market,
                # or its event near its cap). Its reward was worked out for the whole quote, so work it out
                # again for the part. A few contracts cannot earn a program's $1: placed anyway, they were
                # pulled within minutes as `cannot_reach_payout` and placed again, cycle after cycle.
                part = lp.resized(sq, verdict.contracts, programs[sq.ticker], q, books[sq.ticker])
                if verdict.contracts < self.c.min_contracts or not lp.worth_quoting(
                        part, programs[sq.ticker], self.c, stamp, self.earned.get(sq.ticker, 0.0), sq.ticker in committed):
                    self.trimmed_away += 1
                    continue
                sq = part
            decision = {
                "id": new_id(), "kind": "lp_close" if sq.closing else "lp_quote", "ticker": sq.ticker, "event_ticker": q.event_ticker,
                "cluster": q.event_ticker, "created_ts": now(), "mode": self.mode, "strategy": "lp",
                "yes_bid": q.yes_bid, "yes_ask": q.yes_ask, "mid": q.mid if q.two_sided else None,
                "side": sq.side, "limit_price": sq.price, "fee": 0.0, "edge": sq.net_yield_day(self.c),
                "contracts": verdict.contracts if verdict.ok else 0,
                "action": "order" if verdict.ok else "skip",
                "reasons": verdict.reasons + [f"reward_day={sq.reward_day:.3f}", f"share={sq.share:.3f}"],
            }
            self.ledger.insert("decisions", decision)
            if not verdict.ok:
                continue
            try:
                # Rewards need orders that rest, so these carry a long expiry and are managed by prune().
                ok = self.broker.place(decision["id"], sq.ticker, sq.side, sq.price, verdict.contracts,
                                       ttl_s=7 * DAY, queue_ahead=sq.queue_ahead)
            except Exception as e:
                self.ledger.risk_event("order_submit_error", f"lp {sq.ticker}: {e!r}"[:500])
                continue
            if ok:
                placed += 1
                slots -= 0 if sq.closing else 1
                quoted.add(key)
                fam.add(sq.ticker)
                at_risk += 0.0 if sq.closing else sq.price * verdict.contracts
                self.offered_out += sq.closing
        return placed
