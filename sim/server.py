"""Honest server implementation for aggregating client updates and building Merkle roots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from ledger.fixed import (
    quantise,
    dequantise,
    div_truncate,
    DEFAULT_SCALE_BITS,
    BN254_SCALAR_ORDER,
)
from ledger.merkle import MerkleTree
from sim.client import ClientUpdatePackage


@dataclass
class RoundPostPackage:
    round_num: int
    model_root_next: bytes
    agg_root: bytes
    client_leaves_root: bytes
    participant_mask: int
    claimed_weight: int
    w_next_blocks: list[list[int]]
    u_blocks: list[list[int]]
    r_blocks: list[int]
    model_merkle_tree: MerkleTree
    agg_merkle_tree: MerkleTree
    client_merkle_tree: MerkleTree
    active_packages: list[ClientUpdatePackage]


class HonestServer:
    """Aggregator server executing faithful federated averaging."""

    def __init__(
        self,
        initial_weights: np.ndarray,
        block_size: int = 16,
        scale_bits: int = DEFAULT_SCALE_BITS,
    ) -> None:
        self.block_size = block_size
        self.scale_bits = scale_bits
        self.current_weights = initial_weights.copy()
        # Quantised integer representation of model parameters
        self.w_t_int: list[int] = [
            quantise(float(v), scale_bits=self.scale_bits)
            for v in self.current_weights
        ]

    def aggregate_round(
        self,
        round_num: int,
        client_packages: Sequence[ClientUpdatePackage],
        participant_mask: int,
    ) -> RoundPostPackage:
        """Combine participant updates, compute update rule, and anchor roots."""
        active_pkgs = [
            pkg for i, pkg in enumerate(client_packages)
            if (participant_mask & (1 << i)) != 0
        ]
        if not active_pkgs:
            raise ValueError("No active participants in mask")

        claimed_weight = sum(pkg.weight for pkg in active_pkgs)
        num_blocks = len(active_pkgs[0].q_blocks)

        u_blocks: list[list[int]] = []
        r_blocks: list[int] = []
        w_next_blocks: list[list[int]] = []

        agg_leaves: list[bytes] = []
        model_leaves: list[bytes] = []

        # 1. Block-wise integer aggregation and update rule
        for b_idx in range(num_blocks):
            # Compute U_b = sum_k n_k * q_{k,b}
            u_b = [0] * self.block_size
            for pkg in active_pkgs:
                chunk = pkg.q_blocks[b_idx]
                w = pkg.weight
                for i in range(self.block_size):
                    u_b[i] += w * chunk[i]

            # Compute R_b = sum_k n_k * r_{k,b} mod r
            r_b = sum(pkg.weight * pkg.r_blocks[b_idx] for pkg in active_pkgs) % BN254_SCALAR_ORDER

            # Compute W_{t+1,b} = W_{t,b} + div_truncate(U_b, claimed_weight)
            w_curr_chunk = self.w_t_int[b_idx * self.block_size : (b_idx + 1) * self.block_size]
            if len(w_curr_chunk) < self.block_size:
                w_curr_chunk = w_curr_chunk + [0] * (self.block_size - len(w_curr_chunk))

            w_next_chunk = [
                w_curr_chunk[i] + div_truncate(u_b[i], claimed_weight)
                for i in range(self.block_size)
            ]

            u_blocks.append(u_b)
            r_blocks.append(r_b)
            w_next_blocks.append(w_next_chunk)

            # Merkle leaf encodings
            # Model leaf: b_idx (4 bytes) + W_{t+1,b} (32 bytes each, signed int256)
            model_leaf_data = b_idx.to_bytes(4, "big") + b"".join(
                val.to_bytes(32, "big", signed=True) for val in w_next_chunk
            )
            model_leaves.append(model_leaf_data)

            # Aggregate leaf: b_idx (4 bytes) + R_b (32 bytes) + U_b (32 bytes each, signed)
            agg_leaf_data = (
                b_idx.to_bytes(4, "big")
                + r_b.to_bytes(32, "big")
                + b"".join(val.to_bytes(32, "big", signed=True) for val in u_b)
            )
            agg_leaves.append(agg_leaf_data)

        # 2. Client leaves tree: client_idx (1 byte) + address (20 bytes) + root (32) + sig (65)
        client_leaves: list[bytes] = []
        for pkg in active_pkgs:
            leaf_bytes = (
                pkg.client_id.to_bytes(1, "big")
                + bytes.fromhex(pkg.address[2:])
                + pkg.client_block_root
                + pkg.signature
            )
            client_leaves.append(leaf_bytes)

        # 3. Build Merkle trees
        model_tree = MerkleTree(model_leaves)
        agg_tree = MerkleTree(agg_leaves)
        client_tree = MerkleTree(client_leaves)

        # 4. Update internal state
        flat_w_next: list[int] = []
        for chunk in w_next_blocks:
            flat_w_next.extend(chunk)
        # Truncate back to exact parameter vector length
        self.w_t_int = flat_w_next[: len(self.current_weights)]
        self.current_weights = np.array([
            dequantise(v, self.scale_bits) for v in self.w_t_int
        ])

        return RoundPostPackage(
            round_num=round_num,
            model_root_next=model_tree.root,
            agg_root=agg_tree.root,
            client_leaves_root=client_tree.root,
            participant_mask=participant_mask,
            claimed_weight=claimed_weight,
            w_next_blocks=w_next_blocks,
            u_blocks=u_blocks,
            r_blocks=r_blocks,
            model_merkle_tree=model_tree,
            agg_merkle_tree=agg_tree,
            client_merkle_tree=client_tree,
            active_packages=active_pkgs,
        )
