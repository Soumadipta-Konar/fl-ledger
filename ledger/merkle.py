"""Domain-separated Merkle tree implementation for fl-ledger.

Invariants:
- Domain separation: leaf prefix 0x00, internal node prefix 0x01.
- Sorted pair convention: min(left, right) followed by max(left, right).
- Fixed/committed depth: proofs of unexpected depth are rejected.
"""

from __future__ import annotations

import math
from typing import Sequence
from eth_utils import keccak

LEAF_PREFIX: bytes = b"\x00"
NODE_PREFIX: bytes = b"\x01"


def hash_leaf(data: bytes) -> bytes:
    """Hash raw leaf bytes using domain prefix 0x00."""
    return keccak(LEAF_PREFIX + data)


def hash_internal(a: bytes, b: bytes) -> bytes:
    """Hash two node hashes using sorted order and domain prefix 0x01."""
    if a <= b:
        return keccak(NODE_PREFIX + a + b)
    return keccak(NODE_PREFIX + b + a)


def calculate_tree_depth(num_leaves: int) -> int:
    """Return required Merkle proof depth: ceil(log2(num_leaves))."""
    if num_leaves <= 1:
        return 0
    return math.ceil(math.log2(num_leaves))


class MerkleTree:
    """Domain-separated binary Merkle tree with sorted pairs."""

    def __init__(self, raw_leaves: Sequence[bytes]) -> None:
        if not raw_leaves:
            raise ValueError("tree must contain at least one leaf")

        self.raw_leaves: list[bytes] = list(raw_leaves)
        self.num_leaves: int = len(self.raw_leaves)
        self.expected_depth: int = calculate_tree_depth(self.num_leaves)
        self.layers: list[list[bytes]] = []
        self._build()

    def _build(self) -> None:
        current_layer: list[bytes] = [hash_leaf(data) for data in self.raw_leaves]
        self.layers.append(current_layer)

        while len(current_layer) > 1:
            next_layer: list[bytes] = []
            if len(current_layer) % 2 != 0:
                current_layer.append(current_layer[-1])

            for i in range(0, len(current_layer), 2):
                next_layer.append(hash_internal(current_layer[i], current_layer[i + 1]))

            self.layers.append(next_layer)
            current_layer = next_layer

    @property
    def root(self) -> bytes:
        """Return the 32-byte Merkle root hash."""
        return self.layers[-1][0]

    def get_proof(self, index: int) -> list[bytes]:
        """Generate Merkle proof siblings for the given leaf index."""
        if index < 0 or index >= self.num_leaves:
            raise IndexError("leaf index out of range")

        proof: list[bytes] = []
        curr_idx = index

        for layer in self.layers[:-1]:
            working_layer = list(layer)
            if len(working_layer) % 2 != 0:
                working_layer.append(working_layer[-1])

            sibling_idx = curr_idx + 1 if curr_idx % 2 == 0 else curr_idx - 1
            proof.append(working_layer[sibling_idx])
            curr_idx //= 2

        return proof


def verify_proof(
    root: bytes,
    leaf_data: bytes,
    proof: Sequence[bytes],
    expected_depth: int | None = None,
) -> bool:
    """Verify inclusion of leaf_data in the Merkle root.

    Rejects proof if expected_depth is specified and len(proof) != expected_depth.
    """
    if expected_depth is not None and len(proof) != expected_depth:
        return False

    current = hash_leaf(leaf_data)
    for sibling in proof:
        current = hash_internal(current, sibling)

    return current == root
