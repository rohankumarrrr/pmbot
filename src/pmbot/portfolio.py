"""Positions, cash and equity, derived from the fills and settlements in the ledger."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger.db import Ledger


@dataclass
class Position:
    ticker: str
    event_ticker: str
    side: str            # 'yes' / 'no'
    contracts: float     # net of offsetting fills on the other side
    cost: float          # dollars paid for the net position, fees included
    result: str | None   # market result if settled

    @property
    def settled(self) -> bool:
        return self.result in ("yes", "no")

    @property
    def payout(self) -> float:
        return self.contracts if self.settled and self.result == self.side else 0.0


def positions(ledger: Ledger, mode: str) -> list[Position]:
    """Net position per market. A YES and a NO contract in one market pair off into $1."""
    rows = ledger.query(
        """SELECT f.ticker, m.event_ticker, m.result,
                  SUM(CASE WHEN f.side='yes' THEN f.contracts ELSE 0 END) AS yes_n,
                  SUM(CASE WHEN f.side='no'  THEN f.contracts ELSE 0 END) AS no_n,
                  SUM(f.price * f.contracts + f.fee) AS paid
           FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id
           LEFT JOIN markets m ON m.ticker = f.ticker
           WHERE o.mode = ? GROUP BY f.ticker""",
        [mode],
    )
    out = []
    for r in rows:
        paired = min(r["yes_n"], r["no_n"])           # each pair is worth exactly $1
        net = r["yes_n"] - r["no_n"]
        side = "yes" if net >= 0 else "no"
        out.append(Position(r["ticker"], r["event_ticker"] or "", side, abs(net), r["paid"] - paired, r["result"]))
    return out


@dataclass
class Account:
    start: float
    cash: float            # start - money paid + settled payouts
    open_cost: float       # cost of positions not yet settled
    realized: float        # profit on settled positions
    open_positions: list[Position]

    @property
    def equity_at_cost(self) -> float:
        """Cash plus open positions carried at cost: conservative, ignores unrealised gains and losses."""
        return self.cash + self.open_cost


def account(ledger: Ledger, mode: str, start: float) -> Account:
    pos = positions(ledger, mode)
    settled = [p for p in pos if p.settled]
    open_ = [p for p in pos if not p.settled and p.contracts > 0]
    paid = sum(p.cost for p in pos)
    payouts = sum(p.payout for p in settled)
    return Account(
        start=start,
        cash=start - paid + payouts,
        open_cost=sum(p.cost for p in open_),
        realized=payouts - sum(p.cost for p in settled),
        open_positions=open_,
    )


def mark_to_market(ledger: Ledger, acct: Account) -> float:
    """Equity with open positions valued at the latest snapshot mid."""
    value = 0.0
    for p in acct.open_positions:
        snap = ledger.one("SELECT yes_bid, yes_ask FROM snapshots WHERE ticker=? ORDER BY ts DESC LIMIT 1", [p.ticker])
        if snap and snap["yes_ask"] and snap["yes_ask"] > snap["yes_bid"]:
            mid = (snap["yes_bid"] + snap["yes_ask"]) / 2
            value += p.contracts * (mid if p.side == "yes" else 1 - mid)
        else:
            value += p.cost
    return acct.cash + value
