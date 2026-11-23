"""Positions, cash and equity, derived from the fills and settlements in the ledger."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger.db import Ledger


UNPAID = ("determined", "disputed", "amended")     # outcome announced, cash not yet moved


@dataclass
class Position:
    ticker: str
    event_ticker: str
    side: str            # 'yes' / 'no'
    contracts: float     # net of offsetting fills on the other side
    cost: float          # dollars paid for the net position, fees included
    result: str | None   # the market's outcome, once it is known
    status: str | None = None   # the market's status on the exchange

    @property
    def decided(self) -> bool:
        return self.result in ("yes", "no")

    @property
    def settled(self) -> bool:
        """Paid out. Kalshi announces a result ('determined') some hours before it moves the cash
        ('finalized'), and a result can still be disputed or amended in between. Counting the payout at
        the announcement made the ledger's cash run ahead of the exchange's: the gap showed up as
        negative "credited" cash, and on a large win equity would have dropped by the whole payout
        until it arrived, enough to set off a drawdown halt."""
        return self.decided and self.status not in UNPAID

    @property
    def payout(self) -> float:
        return self.contracts if self.settled and self.result == self.side else 0.0

    @property
    def decided_value(self) -> float:
        """What the position is worth once the outcome is known, paid or not."""
        return self.contracts if self.result == self.side else 0.0


def positions(ledger: Ledger, mode: str) -> list[Position]:
    """Net position per market. A YES and a NO contract in one market pair off into $1."""
    rows = ledger.query(
        """SELECT f.ticker, m.event_ticker, m.result, m.status,
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
        out.append(Position(r["ticker"], r["event_ticker"] or "", side, abs(net), r["paid"] - paired, r["result"], r["status"]))
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


MAX_MARK_SPREAD = 0.10   # dollars. A wider book says little about value: its midpoint moves with whoever quotes last.


def mark_price(ledger: Ledger, ticker: str) -> float | None:
    """What a YES contract is worth: the midpoint of the latest snapshot with a two-sided book no wider
    than MAX_MARK_SPREAD. None if there has never been one.

    A thin overnight book of 10c bid / 73c ask once marked an 8c position at 41c, which inflated equity
    by $49 and would have set a false daily-loss halt when the book tightened again.
    """
    snap = ledger.one(
        "SELECT yes_bid, yes_ask FROM snapshots WHERE ticker=? AND yes_ask > yes_bid AND yes_ask - yes_bid <= ? "
        "ORDER BY ts DESC LIMIT 1", [ticker, MAX_MARK_SPREAD + 1e-9])
    return (snap["yes_bid"] + snap["yes_ask"]) / 2 if snap else None


def position_value(ledger: Ledger, p: Position) -> tuple[float, bool]:
    """(dollars, whether that is a real price). A position whose outcome is known but not yet paid is
    worth exactly its payout; otherwise the latest tight book, or cost where there has never been one."""
    if p.decided:
        return p.decided_value, True
    mid = mark_price(ledger, p.ticker)
    if mid is None:
        return p.cost, False
    return p.contracts * (mid if p.side == "yes" else 1 - mid), True


def mark_to_market(ledger: Ledger, acct: Account) -> float:
    """Equity with open positions valued by position_value."""
    return acct.cash + sum(position_value(ledger, p)[0] for p in acct.open_positions)
