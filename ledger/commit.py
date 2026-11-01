"""Pedersen commitments on BN254 G1 for fl-ledger.

Commitment scheme:
  C = r * H + sum_{i=0}^{m-1} q_i * G_i
Invariants:
- q_i are signed integers encoded via to_scalar(q_i) in [0, BN254_SCALAR_ORDER - 1].
- r is blinding scalar in [0, BN254_SCALAR_ORDER - 1].
- Additive homomorphism: sum_k n_k Com(q_k; r_k) == Com(sum_k n_k q_k; sum_k n_k r_k).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence
from py_ecc.bn128 import add, multiply, FQ

from ledger.fixed import to_scalar

Point = tuple[int, int]


def _to_fq(pt: Point | None) -> tuple[FQ, FQ] | None:
    if pt is None:
        return None
    return FQ(pt[0]), FQ(pt[1])


def _from_fq(pt: tuple[FQ, FQ] | None) -> Point | None:
    if pt is None:
        return None
    return int(pt[0]), int(pt[1])


def load_generators(path: str | Path | None = None) -> tuple[Point, list[Point], str]:
    """Load H and G generators along with committed hash from generators.json."""
    if path is None:
        path = Path(__file__).parent.parent / "params" / "generators.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    h_point: Point = (int(data["H"]["x"], 16), int(data["H"]["y"], 16))
    g_points: list[Point] = [
        (int(item["x"], 16), int(item["y"], 16)) for item in data["G"]
    ]
    return h_point, g_points, data["generators_hash"]


# Cached default generators
_DEFAULT_H: Point | None = None
_DEFAULT_G: list[Point] | None = None


def get_default_generators() -> tuple[Point, list[Point]]:
    """Return cached default H and G generators."""
    global _DEFAULT_H, _DEFAULT_G
    if _DEFAULT_H is None or _DEFAULT_G is None:
        _DEFAULT_H, _DEFAULT_G, _ = load_generators()
    return _DEFAULT_H, _DEFAULT_G


def add_points(p1: Point | None, p2: Point | None) -> Point | None:
    """Add two BN254 G1 points."""
    fq1 = _to_fq(p1)
    fq2 = _to_fq(p2)
    res = add(fq1, fq2)
    return _from_fq(res)


def scalar_mul(p: Point | None, scalar: int) -> Point | None:
    """Multiply BN254 G1 point by integer scalar modulo BN254_SCALAR_ORDER."""
    if p is None:
        return None
    s = to_scalar(scalar)
    fq = _to_fq(p)
    res = multiply(fq, s)
    return _from_fq(res)


def commit_block(
    q_block: Sequence[int],
    r_scalar: int,
    h_gen: Point | None = None,
    g_gens: Sequence[Point] | None = None,
) -> Point:
    """Compute Pedersen commitment C = r*H + sum_i (q_i * G_i)."""
    if h_gen is None or g_gens is None:
        h_gen, g_gens = get_default_generators()

    if len(q_block) > len(g_gens):
        raise ValueError(f"Block size {len(q_block)} exceeds generators {len(g_gens)}")

    # r * H
    acc = scalar_mul(h_gen, r_scalar)

    # sum_i q_i * G_i
    for q_val, g_pt in zip(q_block, g_gens):
        if q_val != 0:
            term = scalar_mul(g_pt, q_val)
            acc = add_points(acc, term)

    if acc is None:
        raise ValueError("Commitment evaluated to point at infinity")
    return acc


def homomorphic_sum(commitments: Sequence[Point], weights: Sequence[int]) -> Point:
    """Compute weighted sum of commitments: sum_k (n_k * C_k)."""
    if len(commitments) != len(weights):
        raise ValueError("mismatched commitments and weights")
    if not commitments:
        raise ValueError("empty commitments list")

    acc: Point | None = None
    for comm, weight in zip(commitments, weights):
        scaled = scalar_mul(comm, weight)
        acc = add_points(acc, scaled)

    if acc is None:
        raise ValueError("Homomorphic sum evaluated to point at infinity")
    return acc
