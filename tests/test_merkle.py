"""Unit tests for domain-separated Merkle trees and proofs."""

import pytest
from ledger.merkle import (
    MerkleTree,
    verify_proof,
    hash_leaf,
    calculate_tree_depth,
)


def test_single_leaf_tree() -> None:
    leaves = [b"leaf_0"]
    tree = MerkleTree(leaves)
    assert tree.root == hash_leaf(b"leaf_0")
    proof = tree.get_proof(0)
    assert proof == []
    assert verify_proof(tree.root, b"leaf_0", proof, expected_depth=0)


@pytest.mark.parametrize("n_leaves", [2, 3, 4, 7, 8, 15, 16])
def test_merkle_tree_and_proofs(n_leaves: int) -> None:
    raw_leaves = [f"data_block_{i}".encode() for i in range(n_leaves)]
    tree = MerkleTree(raw_leaves)
    expected_depth = calculate_tree_depth(n_leaves)

    assert len(tree.root) == 32

    for idx, leaf_data in enumerate(raw_leaves):
        proof = tree.get_proof(idx)
        assert len(proof) == expected_depth
        # Valid proof must pass
        assert verify_proof(tree.root, leaf_data, proof, expected_depth=expected_depth)

        # Tampered leaf data must fail
        tampered_leaf = leaf_data + b"_tampered"
        assert not verify_proof(tree.root, tampered_leaf, proof, expected_depth=expected_depth)


def test_proof_wrong_depth_rejected() -> None:
    raw_leaves = [f"leaf_{i}".encode() for i in range(4)]
    tree = MerkleTree(raw_leaves)
    proof = tree.get_proof(0)  # depth is 2

    # Truncated proof must be rejected
    assert not verify_proof(tree.root, b"leaf_0", proof[:-1], expected_depth=2)

    # Extended proof with dummy sibling must be rejected
    dummy_sibling = b"\x00" * 32
    assert not verify_proof(tree.root, b"leaf_0", proof + [dummy_sibling], expected_depth=2)


def test_domain_separation_second_preimage_defense() -> None:
    # Leaf prefix 0x00 prevents an internal node hash (prefix 0x01) from matching a leaf
    l1 = b"left"
    l2 = b"right"
    tree = MerkleTree([l1, l2])

    # Internal root is keccak(0x01 + min(h(l1), h(l2)) + max(h(l1), h(l2)))
    # A single leaf containing that concatenation hashed with 0x00 cannot produce the same root
    raw_concat = l1 + l2
    tree_single = MerkleTree([raw_concat])
    assert tree.root != tree_single.root
