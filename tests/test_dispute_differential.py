"""Differential testing: cross-check Python reference primitives against Solidity contract rules."""

import pytest
import random
from ledger.fixed import div_truncate, quantise, BN254_SCALAR_ORDER
from ledger.merkle import MerkleTree, hash_leaf, hash_internal, verify_proof
from ledger.commit import commit_block, homomorphic_sum, get_default_generators


def test_differential_signed_division_truncation() -> None:
    """Verify that Python div_truncate exactly mirrors Solidity signed integer division."""
    rng = random.Random(42)
    weights = [1, 2, 7, 10, 30, 64, 1000]

    # Test edge cases and random signed integers
    test_values = [
        0, 1, -1, 29, -29, 30, -30, 31, -31,
        1000, -1000, 2**31 - 1, -(2**31 - 1)
    ]
    for _ in range(500):
        test_values.append(rng.randint(-1_000_000, 1_000_000))

    for val in test_values:
        for w in weights:
            py_trunc = div_truncate(val, w)
            # Simulated Solidity signed division: int256 / int256
            if val >= 0:
                sol_trunc = val // w
            else:
                sol_trunc = -((-val) // w)

            assert py_trunc == sol_trunc, f"Mismatch on val={val}, w={w}: py={py_trunc}, sol={sol_trunc}"
            # Truncation property: magnitude never increases
            assert abs(py_trunc * w) <= abs(val)


def test_differential_domain_merkle() -> None:
    """Verify domain-separated leaf and node hashes match between Python and Solidity."""
    leaf_data = b"client_leaf_test_data"
    py_leaf_hash = hash_leaf(leaf_data)

    # Reconstruct Solidity abi.encodePacked(bytes1(0x00), leaf_data)
    from eth_utils import keccak
    sol_leaf_hash = keccak(b"\x00" + leaf_data)
    assert py_leaf_hash == sol_leaf_hash

    node_a = keccak(b"node_a")
    node_b = keccak(b"node_b")
    py_node_hash = hash_internal(node_a, node_b)

    if node_a <= node_b:
        sol_node_hash = keccak(b"\x01" + node_a + node_b)
    else:
        sol_node_hash = keccak(b"\x01" + node_b + node_a)
    assert py_node_hash == sol_node_hash


def test_differential_d1_homomorphism() -> None:
    """Verify D1 aggregation equation sum n_k C_{k,b} == Com(U_b; R_b)."""
    rng = random.Random(1337)
    weights = [10, 20]
    total_weight = sum(weights)

    # 2 clients, block size 4
    q0 = [100, -50, 25, -10]
    r0 = 12345
    c0 = commit_block(q0, r0)

    q1 = [200, 150, -80, 40]
    r1 = 67890
    c1 = commit_block(q1, r1)

    # LHS in Python: homomorphic_sum([c0, c1], weights)
    lhs = homomorphic_sum([c0, c1], weights)

    # Expected aggregate
    u_b = [
        weights[0] * q0[i] + weights[1] * q1[i]
        for i in range(4)
    ]
    r_b = (weights[0] * r0 + weights[1] * r1) % BN254_SCALAR_ORDER

    # RHS in Python: commit_block(u_b, r_b)
    rhs = commit_block(u_b, r_b)

    assert lhs == rhs, "Homomorphism equality failed in reference calculation"


def test_differential_d2_update_rule() -> None:
    """Verify D2 element-wise update calculation."""
    w_curr = [10000, -20000, 30000, -40000]
    u_b = [5000, 2500, -1350, 700]
    claimed_weight = 30

    w_next = [
        w_curr[i] + div_truncate(u_b[i], claimed_weight)
        for i in range(4)
    ]

    expected = [10166, -19917, 29955, -39977]
    assert w_next == expected, f"Update rule result {w_next} did not match expected {expected}"
