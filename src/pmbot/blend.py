"""Probability, edge and sizing maths. Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, floor, log

from .kalshi.fees import fee_per_contract

EPS = 1e-4


def clip(p: float, lo: float = EPS, hi: float = 1 - EPS) -> float:
    return min(hi, max(lo, p))


def logit(p: float) -> float:
    p = clip(p)
    return log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + exp(-x))


def calibrate(p: float, a: float = 1.0, b: float = 0.0) -> float:
    """Platt scaling in log-odds. a > 1 pushes away from 50%; identity until fitted on resolved forecasts."""
    return sigmoid(a * logit(p) + b)


def debias(price: float, a: float = 0.0, b: float = 1.0) -> float:
    """Market price -> historical win rate at that price, as a logistic curve in log-odds.

    Fitted on resolved Kalshi markets (research/analyze_trades.py): b > 1 means favourites
    win more often than their price says and longshots less; a < 0 means YES is overpriced.
    """
    return sigmoid(a + b * logit(price))


def blend(p_model: float, p_market: float, w_market: float) -> float:
    """Weighted average in log-odds. w_market = 1 returns the market price."""
    return sigmoid(w_market * logit(p_market) + (1 - w_market) * logit(p_model))


def kelly_fraction(p_win: float, cost: float) -> float:
    """Full-Kelly bankroll fraction for a contract costing `cost` that pays $1 with probability p_win."""
    if not 0 < cost < 1:
        return 0.0
    return max(0.0, (p_win - cost) / (1 - cost))


@dataclass(frozen=True)
class Sizing:
    side: str | None        # 'yes', 'no', or None for no trade
    price: float            # price paid per contract for that side
    fee: float              # fee per contract
    edge: float             # expected profit per contract after fee
    kelly: float            # full-Kelly fraction
    contracts: int
    reason: str = ""


def size_order(
    p_yes: float,
    yes_price: float,
    no_price: float,
    bankroll: float,
    maker: bool = True,
    fee_type: str = "quadratic",
    fee_multiplier: float = 1.0,
    kelly_mult: float = 0.2,
    max_fraction: float = 0.03,
    min_edge: float = 0.03,
    max_contracts: int | None = None,
) -> Sizing:
    """Pick the better side at the given limit prices and size it.

    `yes_price` is what we would pay for YES, `no_price` what we would pay for NO
    (each a resting limit price when maker=True).
    """
    best = Sizing(None, 0.0, 0.0, 0.0, 0.0, 0, "no_edge")
    for side, p_win, price in (("yes", p_yes, yes_price), ("no", 1 - p_yes, no_price)):
        if not 0 < price < 1:
            continue
        fee = fee_per_contract(price, maker, fee_type, fee_multiplier)
        edge = p_win - price - fee
        if edge > best.edge:
            best = Sizing(side, price, fee, edge, kelly_fraction(p_win, price + fee), 0)
    if best.side is None or best.edge < min_edge:
        return Sizing(None, best.price, best.fee, best.edge, best.kelly, 0, "edge_below_min")
    stake = min(kelly_mult * best.kelly, max_fraction) * bankroll
    n = floor(stake / (best.price + best.fee))
    if max_contracts is not None:
        n = min(n, max_contracts)
    if n < 1:
        return Sizing(None, best.price, best.fee, best.edge, best.kelly, 0, "size_below_one_contract")
    return Sizing(best.side, best.price, best.fee, best.edge, best.kelly, n)
