"""One cycle of the bot: catalog -> sync -> risk -> forecast -> decide -> order."""

from __future__ import annotations

import random
import time
from pathlib import Path

from . import catalog
from .blend import blend, calibrate, debias, size_order
from .catalog import Quote
from .config import Config
from .execution.brokers import Broker, KalshiBroker, ShadowBroker
from .kalshi.client import DEMO, PROD, KalshiClient
from .kalshi.fees import fee_per_contract
from .ledger.db import Ledger, new_id, now
from .llm.pipeline import PIPELINE_VERSION, EventForecast, Forecaster
from .lp_runner import LiquidityProvider
from .portfolio import account
from .risk import RiskManager
from .universe import Candidate, candidates

HOUR = 3600


def family(series_ticker: str) -> str:
    return series_ticker[:9]


def log(*parts) -> None:
    print(time.strftime("%H:%M:%S"), *parts, flush=True)


def trading_client(cfg: Config) -> KalshiClient:
    creds = Path(cfg.kalshi.credentials_dir).expanduser() / cfg.mode
    key_id, key_file = creds / "key_id", creds / "private_key.pem"
    if not key_id.exists() or not key_file.exists():
        raise SystemExit(f"{cfg.mode} mode needs {key_id} and {key_file}")
    client = KalshiClient.from_key_file(DEMO if cfg.mode == "demo" else PROD, key_id.read_text().strip(), key_file)
    client.subaccount = cfg.kalshi.subaccount
    return client


class Runner:
    def __init__(self, cfg: Config, ledger: Ledger | None = None, market_data: KalshiClient | None = None,
                 broker: Broker | None = None, forecaster: Forecaster | None = None):
        self.cfg, self.mode = cfg, cfg.mode
        self.ledger = ledger or Ledger(cfg.ledger_path)
        # Market data comes from the exchange we trade on: demo prices differ from production.
        self.data = market_data or KalshiClient(DEMO if self.mode == "demo" else PROD)
        lease_s = int(cfg.risk.get("order_lease_minutes", 0) * 60) or None
        if broker:
            self.broker = broker
        elif self.mode == "shadow":
            self.broker = ShadowBroker(self.ledger, self.data, lease_s)
        else:
            self.broker = KalshiBroker(self.ledger, trading_client(cfg), self.mode, cfg.kalshi.subaccount,
                                       cfg.risk.order_group_contracts_limit, lease_s)
        self.forecaster = forecaster or Forecaster(config=dict(cfg.forecast))
        bankroll = self.bankroll()
        # Equity is measured from the cash the account began with: the balance now, less what the ledger's fills explain.
        start_cash = bankroll - account(self.ledger, self.mode, 0.0).cash if self.mode in ("demo", "live") else bankroll
        self.risk = RiskManager(self.ledger, cfg, self.mode, bankroll, start_cash)
        self.lp = LiquidityProvider(cfg, self.ledger, self.data, self.broker, self.risk, self.mode) if cfg.lp.enabled else None
        self.rng = random.Random()

    def bankroll(self) -> float:
        if self.mode in ("demo", "live"):
            return float(self.broker.client.balance()["balance_dollars"])
        return float(self.cfg.bankroll_usd)

    # --- the cycle ---------------------------------------------------------

    def cycle(self, forecast: bool = True) -> dict:
        stats: dict = {"mode": self.mode}
        # Kalshi may also cancel orders placed in the minute after a cancel-all, so hold off.
        since = now() - (self.ledger.get_state(f"last_cancel_all:{self.mode}") or 0)
        if since < 75:
            time.sleep(75 - since)
        quotes = catalog.pull_open_quotes(self.data, self.ledger)
        by_ticker = {q.ticker: q for q in quotes}
        cands = candidates(quotes, self.cfg.universe)
        watched = self.watched_tickers()
        catalog.snapshot(self.ledger, [q for c in cands for q in c.quotes] + [by_ticker[t] for t in watched if t in by_ticker])
        stats.update(open_markets=len(quotes), candidate_events=len(cands))

        stats["fills"] = self.broker.sync()
        stats["settled"] = catalog.sync_settlements(self.data, self.ledger, self.unsettled_tickers())

        if self.mode != "shadow":
            from .consistency import check_and_react
            report, must_halt = check_and_react(self.ledger, self.broker.client, self.mode)
            stats["consistency"] = report.summary()
            if must_halt and not self.risk.halted:
                self.risk.halt(f"ledger and exchange disagree two cycles running: {report.summary()}")

        halted = self.risk.check_account()
        if halted:
            self.broker.cancel_all(halted)
            stats["halted"] = halted
            log("HALTED:", halted)
            return stats

        stats["cancelled_stale"] = self.cancel_stale(by_ticker)
        stats["requoted"] = self.requote(by_ticker)
        if self.lp:
            stats.update(self.lp.step(by_ticker))
        stats["baselines"] = self.record_baselines(cands)
        # Every order the cycle decided to keep gets its lease renewed. If the bot stops, they lapse.
        stats["leases_renewed"] = self.broker.renew()
        if forecast:
            stats.update(self.forecast_events(cands))
            self.broker.renew()          # forecasts take minutes
        return stats

    def record_baselines(self, cands: list[Candidate]) -> int:
        """Log the bias-corrected price for every universe market, once a week per market.

        Costs nothing and resolves by the hundred, so it shows quickly whether the price
        correction holds up, and gives the model forecasts a benchmark to beat.
        """
        t = self.cfg.trading
        seen = {r["ticker"] for r in self.ledger.query(
            "SELECT ticker FROM decisions WHERE kind='baseline' AND created_ts>?", [now() - 7 * 86400])}
        rows = []
        for c in cands:
            for q in c.quotes:
                if q.ticker in seen or not q.two_sided:
                    continue
                anchor = debias(q.mid, t.price_prior_a, t.price_prior_b)
                rows.append({
                    "id": new_id(), "kind": "baseline", "ticker": q.ticker, "event_ticker": q.event_ticker,
                    "cluster": q.event_ticker, "created_ts": now(), "mode": self.mode, "strategy": "price_prior",
                    "pipeline_version": PIPELINE_VERSION, "holdout": False, "tradable": c.tradable,
                    "yes_bid": q.yes_bid, "yes_ask": q.yes_ask, "mid": q.mid, "p_model": anchor, "p_final": anchor,
                    "w_market": 0.0, "action": "skip", "reasons": ["baseline"],
                })
        self.ledger.insert_many("decisions", rows)
        return len(rows)

    def watched_tickers(self) -> list[str]:
        rows = self.ledger.query(
            "SELECT DISTINCT ticker FROM orders WHERE mode=? AND status IN ('resting','partial','filled','partial_cancelled')",
            [self.mode])
        return [r["ticker"] for r in rows]

    def unsettled_tickers(self) -> list[str]:
        rows = self.ledger.query(
            "SELECT DISTINCT d.ticker FROM decisions d JOIN markets m ON m.ticker = d.ticker "
            "WHERE m.result IS NULL AND m.close_ts < ?", [now() + HOUR])
        return [r["ticker"] for r in rows]

    # --- forecasting -------------------------------------------------------

    def budget_left(self) -> tuple[int, float]:
        """(forecast slots open now, dollars left), both over a rolling 24 hours.

        Slots are paced: at most `max_events_per_cycle` forecasts per equal share of the day, so the
        budget is spread across the day instead of being spent in its first hour. Runs that were
        skipped (screened out, rules unclear) cost almost nothing and do not use a slot; the dollar
        cap still counts them.
        """
        f = self.cfg.forecast
        pace_s = 86400 * f.max_events_per_cycle / f.daily_event_budget
        made = "SELECT COUNT(*) AS n FROM forecast_runs WHERE skipped IS NULL AND created_ts>?"
        in_day = self.ledger.one(made, [now() - 86400])["n"]
        in_pace = self.ledger.one(made, [now() - pace_s])["n"]
        spent = self.ledger.one("SELECT COALESCE(SUM(cost_usd),0) AS c FROM forecast_runs WHERE created_ts>?", [now() - 86400])["c"]
        return min(f.daily_event_budget - in_day, f.max_events_per_cycle - in_pace), f.daily_cost_cap_usd - spent

    def pick_events(self, cands: list[Candidate], slots: int) -> list[tuple[Candidate, bool]]:
        """(candidate, holdout). Holdout events are drawn at random and skip the screen."""
        if self.mode != "shadow":
            cands = [c for c in cands if c.tradable]
        recent = {r["event_ticker"] for r in self.ledger.query(
            "SELECT event_ticker FROM forecast_runs WHERE created_ts>?", [now() - self.cfg.forecast.reforecast_after_hours * HOUR])}
        # One event per family per day. Kalshi lists sibling questions (the same gas-price question
        # for each state) as separate series whose tickers share a prefix; forecasting each one adds
        # cost without adding independent evidence.
        busy = {family(r["series_ticker"]) for r in self.ledger.query(
            "SELECT DISTINCT e.series_ticker FROM forecast_runs f JOIN events e ON e.event_ticker = f.event_ticker "
            "WHERE f.created_ts>?", [now() - 24 * HOUR])}
        eligible, taken = [], set(busy)
        for c in cands:
            fam = family(c.quotes[0].series_ticker)
            if c.event_ticker in recent or fam in taken:
                continue
            taken.add(fam)
            eligible.append(c)
        picks: list[tuple[Candidate, bool]] = []
        while eligible and len(picks) < slots:
            holdout = self.rng.random() < self.cfg.forecast.holdout_fraction
            c = self.rng.choice(eligible) if holdout else eligible[0]
            eligible.remove(c)
            picks.append((c, holdout))
        return picks

    def forecast_events(self, cands: list[Candidate]) -> dict:
        slots, dollars_left = self.budget_left()
        stats = {"forecast_runs": 0, "forecast_cost": 0.0, "orders": 0}
        for cand, holdout in self.pick_events(cands, max(min(slots, self.cfg.forecast.max_events_per_cycle), 0)):
            if dollars_left - stats["forecast_cost"] <= 0:
                break
            started = time.time()
            try:
                catalog.attach_rules(self.data, cand.quotes)      # the catalog pull does not keep rules text
                fc = self.forecaster.run(cand.quotes, skip_screen=holdout)
            except Exception as e:  # one bad event must not stop the cycle
                log("forecast failed:", cand.event_ticker, str(e)[:200])
                self.ledger.risk_event("forecast_error", f"{cand.event_ticker}: {e}")
                continue
            run_id = self.record_run(cand, fc, holdout, time.time() - started)
            stats["forecast_runs"] += 1
            stats["forecast_cost"] += fc.cost_usd
            log(f"forecast {cand.event_ticker} ${fc.cost_usd:.2f}", fc.skipped or "ok")
            if fc.skipped:
                continue
            # Research takes minutes: re-read prices before deciding.
            fresh = self.refresh(cand.quotes)
            for q in fresh:
                stats["orders"] += self.decide(run_id, "forecast", q, fc.median(q.ticker), fc.spread(q.ticker),
                                               cand.tradable, holdout)
        return stats

    def refresh(self, quotes: list[Quote]) -> list[Quote]:
        live = {m["ticker"]: m for m in self.data.get("/markets", tickers=",".join(q.ticker for q in quotes), limit=1000)["markets"]}
        out = []
        for q in quotes:
            m = live.get(q.ticker)
            if not m or m.get("status") != "active":
                continue
            q.yes_bid, q.yes_ask = catalog.dollars(m.get("yes_bid_dollars")), catalog.dollars(m.get("yes_ask_dollars"))
            q.yes_bid_size, q.yes_ask_size = catalog.count(m.get("yes_bid_size_fp")), catalog.count(m.get("yes_ask_size_fp"))
            out.append(q)
        catalog.snapshot(self.ledger, out)
        return out

    def record_run(self, cand: Candidate, fc: EventForecast, holdout: bool, duration: float) -> str:
        run_id = new_id()
        self.ledger.insert("forecast_runs", {
            "id": run_id, "event_ticker": cand.event_ticker, "created_ts": now(), "pipeline_version": PIPELINE_VERSION,
            "holdout": holdout, "tradable": cand.tradable, "screen": fc.screen, "dossier": fc.dossier,
            "skipped": fc.skipped, "cost_usd": fc.cost_usd, "duration_s": duration,
        })
        self.ledger.insert_many("forecasts", [
            {"id": new_id(), "run_id": run_id, "ticker": t, "model": s["model"], "sample_idx": s["sample_idx"],
             "p": p, "rationale": s.get("reasoning"), "cost_usd": s.get("cost_usd")}
            for s in fc.samples for t, p in s["probs"].items()
        ])
        for q in cand.quotes:
            self.ledger.insert("rules_text", {"hash": catalog.rules_hash(q.rules), "ticker": q.ticker, "ts": now(), "text": q.rules})
        return run_id

    # --- deciding ----------------------------------------------------------

    def quote_prices(self, q: Quote) -> tuple[float, float, float, float]:
        """Resting limit prices for buying YES and buying NO, and the size queued ahead of each.

        Step one tick inside the spread when there is room (front of the queue);
        otherwise join the best price behind the size already there.
        """
        tick = q.tick(q.mid)
        if q.spread >= 2 * tick - 1e-9:
            return round(q.yes_bid + tick, 4), round(1 - q.yes_ask + tick, 4), 0.0, 0.0
        return q.yes_bid, round(1 - q.yes_ask, 4), q.yes_bid_size, q.yes_ask_size

    def decide(self, run_id: str, kind: str, q: Quote, p_model: float | None, p_spread: float,
               tradable: bool, holdout: bool) -> int:
        """Record a decision for one market and place the order if there is one. Returns orders placed."""
        t = self.cfg.trading
        base = {
            "id": new_id(), "run_id": run_id, "kind": kind, "ticker": q.ticker, "event_ticker": q.event_ticker,
            "cluster": q.event_ticker, "created_ts": now(), "mode": self.mode, "strategy": "llm_blend",
            "pipeline_version": PIPELINE_VERSION, "holdout": holdout, "tradable": tradable,
            "yes_bid": q.yes_bid, "yes_ask": q.yes_ask, "mid": q.mid if q.two_sided else None,
            "p_model": p_model, "p_spread": p_spread, "w_market": t.w_market,
        }
        if p_model is None or not q.two_sided:
            self.ledger.insert("decisions", {**base, "action": "skip", "reasons": ["no_forecast" if p_model is None else "no_two_sided_quote"]})
            return 0
        # Anchor on the price corrected for how such prices have resolved, not the raw mid.
        anchor = debias(q.mid, t.price_prior_a, t.price_prior_b)
        p_final = blend(calibrate(p_model, t.platt_a, t.platt_b), anchor, t.w_market)
        yes_px, no_px, yes_queue, no_queue = self.quote_prices(q)
        bankroll = self.risk.bankroll
        s = size_order(p_final, yes_px, no_px, bankroll, True, q.fee_type, q.fee_multiplier,
                       t.kelly_mult, t.max_fraction_per_market, t.min_edge)
        reasons: list[str] = []
        contracts = 0
        if s.side is None:
            reasons.append(s.reason)
        elif s.edge < t.spread_edge_mult * (1 - t.w_market) * p_spread:
            reasons.append("edge_within_ensemble_noise")
        elif self.has_exposure(q.ticker):
            reasons.append("already_positioned")
        elif not tradable and self.mode != "shadow":
            reasons.append("shadow_only_category")
        else:
            verdict = self.risk.review(s, q.ticker, q.event_ticker)
            reasons += verdict.reasons
            contracts = verdict.contracts if verdict.ok else 0
        row = {**base, "p_final": p_final, "side": s.side, "limit_price": s.price, "fee": s.fee, "edge": s.edge,
               "kelly": s.kelly, "contracts": contracts, "action": "order" if contracts else "skip", "reasons": reasons}
        self.ledger.insert("decisions", row)
        if not contracts:
            return 0
        try:
            placed = self.broker.place(row["id"], q.ticker, s.side, s.price, contracts, int(t.order_ttl_hours * HOUR),
                                       queue_ahead=yes_queue if s.side == "yes" else no_queue)
        except Exception as e:
            # The request may or may not have reached the exchange. The order row stays
            # 'submitting' and the next sync() settles which.
            self.ledger.risk_event("order_submit_error", f"{q.ticker}: {e!r}"[:500])
            return 0
        log(f"order {q.ticker} buy {s.side} {contracts}@{s.price:.3f} edge {s.edge:.3f} p_final {p_final:.3f} mid {q.mid:.3f}")
        return int(bool(placed))

    def has_exposure(self, ticker: str) -> bool:
        return bool(self.ledger.one(
            "SELECT 1 FROM orders WHERE mode=? AND ticker=? AND status IN ('resting','partial','filled','submitting','partial_cancelled')",
            [self.mode, ticker]))

    # --- order upkeep ------------------------------------------------------

    def cancel_stale(self, by_ticker: dict[str, Quote]) -> int:
        """Pull resting orders whose market has moved since the decision: the forecast no longer describes it."""
        n = 0
        rows = self.ledger.query(
            "SELECT o.client_order_id, o.ticker, d.mid FROM orders o JOIN decisions d ON d.id = o.decision_id "
            "WHERE o.mode=? AND d.strategy='llm_blend' AND o.status IN ('resting','partial')", [self.mode])
        for r in rows:
            q = by_ticker.get(r["ticker"])
            if q is None or not q.two_sided or abs(q.mid - r["mid"]) > self.cfg.trading.max_mid_move:
                self.broker.cancel(r["client_order_id"], "market_moved")
                n += 1
        return n

    def requote(self, by_ticker: dict[str, Quote]) -> int:
        """Re-enter for forecasts that are still fresh but whose order expired or was pulled unfilled."""
        t = self.cfg.trading
        rows = self.ledger.query(
            """SELECT d.run_id, d.ticker, d.p_model, d.p_spread, d.mid, d.tradable, d.holdout, MAX(d.created_ts) AS last_ts
               FROM decisions d JOIN forecast_runs r ON r.id = d.run_id
               WHERE d.mode=? AND r.created_ts > ? AND d.p_model IS NOT NULL
               GROUP BY d.run_id, d.ticker""",
            [self.mode, now() - int(t.forecast_ttl_hours * HOUR)])
        n = 0
        for r in rows:
            q = by_ticker.get(r["ticker"])
            if q is None or not q.two_sided or self.has_exposure(r["ticker"]):
                continue
            first_mid = self.ledger.one("SELECT mid FROM decisions WHERE run_id=? AND ticker=? AND kind='forecast'",
                                        [r["run_id"], r["ticker"]])
            if first_mid is None or first_mid["mid"] is None or abs(q.mid - first_mid["mid"]) > t.max_mid_move:
                continue
            if now() - r["last_ts"] < t.order_ttl_hours * HOUR:
                continue   # the last decision for this forecast is still current
            n += self.decide(r["run_id"], "requote", q, r["p_model"], r["p_spread"], bool(r["tradable"]), bool(r["holdout"]))
        return n
