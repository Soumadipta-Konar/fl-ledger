"""Unit tests for fixed-point math and scalar field arithmetic."""

import pytest
from ledger.fixed import (
    quantise,
    dequantise,
    div_truncate,
    to_scalar,
    aggregate_blocks,
    update_block,
    BN254_SCALAR_ORDER,
    DEFAULT_BOUND_B,
)


def test_quantise_and_dequantise() -> None:
    val = 0.12345
    q = quantise(val, scale_bits=16)
    assert isinstance(q, int)
    recovered = dequantise(q, scale_bits=16)
    assert abs(val - recovered) < 1.0 / 65536


def test_quantise_bounds_enforced() -> None:
    # Exactly on bound should pass
    q_max = quantise(DEFAULT_BOUND_B / 65536.0, scale_bits=16, bound=DEFAULT_BOUND_B)
    assert q_max == DEFAULT_BOUND_B

    # Exceeding bound must raise ValueError
    with pytest.raises(ValueError):
        quantise(DEFAULT_BOUND_B / 65536.0 + 1.0, scale_bits=16, bound=DEFAULT_BOUND_B)

    with pytest.raises(ValueError):
        quantise(-(DEFAULT_BOUND_B / 65536.0) - 1.0, scale_bits=16, bound=DEFAULT_BOUND_B)


def test_div_truncate_matches_solidity() -> None:
    # Positive quotients
    assert div_truncate(10, 3) == 3
    assert div_truncate(9, 3) == 3

    # Negative quotients must truncate toward zero (EVM semantics)
    assert div_truncate(-5, 2) == -2
    assert div_truncate(5, -2) == -2
    assert div_truncate(-9, 4) == -2
    assert div_truncate(-5, -2) == 2

    # Zero numerator
    assert div_truncate(0, 7) == 0

    # Zero denominator
    with pytest.raises(ZeroDivisionError):
        div_truncate(5, 0)


def test_to_scalar_negative_and_bounds() -> None:
    assert to_scalar(0) == 0
    assert to_scalar(1) == 1
    assert to_scalar(-1) == BN254_SCALAR_ORDER - 1
    assert to_scalar(-100) == BN254_SCALAR_ORDER - 100
    assert to_scalar(BN254_SCALAR_ORDER) == 0
    assert to_scalar(BN254_SCALAR_ORDER + 5) == 5


def test_aggregate_and_update_block() -> None:
    c1 = [100, -50, 20]
    c2 = [-30, 40, -10]
    weights = [2, 3]

    # U_b = 2*[100, -50, 20] + 3*[-30, 40, -10] = [110, 20, 10]
    agg = aggregate_blocks([c1, c2], weights)
    assert agg == [110, 20, 10]

    # W_{t+1} = W_t + div(U, sum_weights)
    # total_weight = 5 -> div([110, 20, 10], 5) = [22, 4, 2]
    w_t = [1000, 2000, 3000]
    w_next = update_block(w_t, agg, total_weight=5)
    assert w_next == [1022, 2004, 3002]


def test_update_block_negative_truncation() -> None:
    # Test negative update with truncation
    w_t = [100]
    u_b = [-5]
    total_weight = 2  # -5 / 2 truncates to -2
    w_next = update_block(w_t, u_b, total_weight)
    assert w_next == [98]  # 100 + (-2) == 98
