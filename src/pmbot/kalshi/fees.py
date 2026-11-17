"""Kalshi fee model.

fee = multiplier * rate * contracts * P * (1 - P)

Taker rate is 0.07. Makers pay nothing on `quadratic` series, a quarter of the
taker rate on `quadratic_with_maker_fees`, and half on
`quadratic_with_combo_maker_fees`. Direct members' balances are kept to
$0.0001, so an order's total fee is rounded up to that precision.
"""

from __future__ import annotations

import math

TAKER_RATE = 0.07
MAKER_SHARE = {
    "quadratic": 0.0,
    "quadratic_with_maker_fees": 0.25,
    "quadratic_with_combo_maker_fees": 0.5,
}
BALANCE_PRECISION = 1e-4


def fee_rate(maker: bool, fee_type: str = "quadratic", fee_multiplier: float = 1.0) -> float:
    if fee_type == "flat":
        raise ValueError("flat-fee series are not modelled; exclude them from the universe")
    share = MAKER_SHARE[fee_type] if maker else 1.0
    return TAKER_RATE * share * fee_multiplier


def fee_per_contract(price: float, maker: bool, fee_type: str = "quadratic", fee_multiplier: float = 1.0) -> float:
    """Unrounded fee for one contract; use for edge maths."""
    return fee_rate(maker, fee_type, fee_multiplier) * price * (1.0 - price)


def order_fee(price: float, contracts: float, maker: bool, fee_type: str = "quadratic", fee_multiplier: float = 1.0) -> float:
    """Total fee for an order as a direct member would be charged."""
    raw = fee_per_contract(price, maker, fee_type, fee_multiplier) * contracts
    return math.ceil(round(raw / BALANCE_PRECISION, 9)) * BALANCE_PRECISION
