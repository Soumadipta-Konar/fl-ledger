"""Unit tests for BN254 G1 Pedersen commitments and additive homomorphism."""

import pytest
from py_ecc.bn128 import is_on_curve, b, FQ, curve_order

from ledger.commit import (
    commit_block,
    homomorphic_sum,
    get_default_generators,
    load_generators,
)
from ledger.fixed import to_scalar


def test_generators_valid_on_curve() -> None:
    h_gen, g_gens, comm_hash = load_generators()
    assert comm_hash.startswith("0x")
    assert len(comm_hash) == 66
    assert len(g_gens) == 32

    # Check H is on curve
    assert is_on_curve((FQ(h_gen[0]), FQ(h_gen[1])), b)

    # Check all G_i are on curve
    for gx, gy in g_gens:
        assert is_on_curve((FQ(gx), FQ(gy)), b)


def test_commit_block_is_on_curve() -> None:
    q_block = [10, -25, 0, 100]
    r_scalar = 99999
    comm = commit_block(q_block, r_scalar)
    assert is_on_curve((FQ(comm[0]), FQ(comm[1])), b)


def test_additive_homomorphism() -> None:
    """Verify sum_k n_k Com(q_k; r_k) == Com(sum_k n_k q_k; sum_k n_k r_k)."""
    # 3 clients, block size m = 4
    client_updates = [
        [100, -200, 300, -400],
        [-50, 75, -125, 250],
        [10, 20, 30, 40],
    ]
    blindings = [12345, 67890, 11223]
    weights = [3, 5, 2]

    # Compute individual client commitments
    commitments = [
        commit_block(q, r)
        for q, r in zip(client_updates, blindings)
    ]

    # LHS: sum_k n_k C_k
    lhs = homomorphic_sum(commitments, weights)

    # RHS: Com(sum_k n_k q_k; sum_k n_k r_k)
    m = len(client_updates[0])
    agg_q = [0] * m
    for q, w in zip(client_updates, weights):
        for i in range(m):
            agg_q[i] += w * q[i]

    agg_r = sum(w * r for w, r in zip(weights, blindings)) % curve_order
    rhs = commit_block(agg_q, agg_r)

    assert lhs == rhs


def test_commitment_negative_values() -> None:
    # Test block with all negative entries
    q_neg = [-1000, -2000, -3000]
    r_val = 55555
    comm = commit_block(q_neg, r_val)
    assert is_on_curve((FQ(comm[0]), FQ(comm[1])), b)


def test_block_size_exceeding_generators_rejected() -> None:
    h, g = get_default_generators()
    too_large_block = [1] * (len(g) + 1)
    with pytest.raises(ValueError):
        commit_block(too_large_block, r_scalar=1, h_gen=h, g_gens=g)
