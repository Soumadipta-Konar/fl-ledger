"""Fixed-point arithmetic and field scalar conversions for fl-ledger.

Units:
- Quantised values: integers scaled by 2^s.
- Scalar field elements: non-negative integers in [0, BN254_SCALAR_ORDER - 1].
Invariants:
- Entry bounds: |q| <= B (default B = 2^31 - 1).
- Truncation toward zero matches Solidity native signed division: div(-5, 2) == -2.
"""

from __future__ import annotations

import math
from typing import Sequence

# Alt_bn128 (BN254) elliptic curve orders
BN254_FIELD_PRIME: int = (
    21888242871839275222246405745257275088696311157297823662689037894645226208583
)
BN254_SCALAR_ORDER: int = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)

DEFAULT_SCALE_BITS: int = 16
DEFAULT_BOUND_B: int = (1 << 31) - 1
MAX_CLIENTS_K: int = 64
MAX_BLOCK_SIZE_M: int = 32


def quantise(val: float, scale_bits: int = DEFAULT_SCALE_BITS, bound: int = DEFAULT_BOUND_B) -> int:
    """Scale float by 2^scale_bits, round to nearest integer, and enforce [-bound, bound]."""
    scale = 1 << scale_bits
    scaled = round(val * scale)
    if scaled > bound or scaled < -bound:
        raise ValueError(f"Value {scaled} exceeds bound [{ -bound}, {bound}]")
    return scaled


def dequantise(q: int, scale_bits: int = DEFAULT_SCALE_BITS) -> float:
    """Convert fixed-point integer back to float."""
    return float(q) / (1 << scale_bits)


def div_truncate(numerator: int, denominator: int) -> int:
    """Integer division truncating toward zero, matching Solidity native integer division.

    EVM division satisfies: -5 / 2 == -2, 5 / 2 == 2, -5 / -2 == 2.
    """
    if denominator == 0:
        raise ZeroDivisionError("division by zero")
    return math.trunc(numerator / denominator)


def to_scalar(x: int) -> int:
    """Encode a signed integer into a BN254 G1 scalar field element in [0, BN254_SCALAR_ORDER - 1]."""
    return x % BN254_SCALAR_ORDER


def aggregate_blocks(
    client_blocks: Sequence[Sequence[int]],
    weights: Sequence[int],
) -> list[int]:
    """Compute weighted sum: U_b = sum_k (n_k * q_{k,b})."""
    if not client_blocks:
        raise ValueError("client_blocks must not be empty")
    if len(client_blocks) != len(weights):
        raise ValueError("mismatched number of clients and weights")

    block_len = len(client_blocks[0])
    agg = [0] * block_len
    for k, block in enumerate(client_blocks):
        if len(block) != block_len:
            raise ValueError("all client blocks must have identical length")
        w = weights[k]
        for i in range(block_len):
            agg[i] += w * block[i]
    return agg


def update_block(
    w_t: Sequence[int],
    u_b: Sequence[int],
    total_weight: int,
) -> list[int]:
    """Compute federated update: W_{t+1,b} = W_{t,b} + div_truncate(U_b, total_weight)."""
    if len(w_t) != len(u_b):
        raise ValueError("weight block and update block lengths must match")
    if total_weight <= 0:
        raise ValueError("total_weight must be positive")

    return [w_t[i] + div_truncate(u_b[i], total_weight) for i in range(len(w_t))]
