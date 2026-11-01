"""Scripted cheating server implementation for evaluating dispute and detection mechanisms."""

from __future__ import annotations

import random
from enum import Enum, auto
from typing import Sequence
import numpy as np

from ledger.fixed import div_truncate, DEFAULT_SCALE_BITS, BN254_SCALAR_ORDER
from ledger.merkle import MerkleTree
from sim.client import ClientUpdatePackage
from sim.server import HonestServer, RoundPostPackage


class CheatType(Enum):
    HONEST = auto()
    OLD_MODEL = auto()
    SKIPPED_ROUND = auto()
    CORRUPTED_BLOCKS = auto()
    FABRICATED_CLIENT = auto()
    HISTORY_TAMPER = auto()


class CheatingServer(HonestServer):
    """Server capable of executing scripted cheats across federated rounds."""

    def __init__(
        self,
        initial_weights: np.ndarray,
        block_size: int = 16,
        scale_bits: int = DEFAULT_SCALE_BITS,
        cheat_type: CheatType = CheatType.HONEST,
        corrupt_fraction: float = 0.2,
        seed: int = 42,
    ) -> None:
        super().__init__(initial_weights, block_size, scale_bits)
        self.cheat_type = cheat_type
        self.corrupt_fraction = corrupt_fraction
        self.seed = seed
        self.rng = random.Random(seed)

    def aggregate_round_with_cheat(
        self,
        round_num: int,
        client_packages: Sequence[ClientUpdatePackage],
        participant_mask: int,
    ) -> RoundPostPackage:
        """Aggregate round updates while applying designated cheat mode."""
        old_w_int = list(self.w_t_int)
        pkg = self.aggregate_round(round_num, client_packages, participant_mask)
        num_blocks = len(pkg.u_blocks)

        if self.cheat_type == CheatType.HONEST:
            return pkg

        elif self.cheat_type == CheatType.OLD_MODEL:
            # Server returns previous model W_t instead of updated model W_{t+1}
            corrupt_leaves = []
            old_model_blocks = []
            for b_idx in range(num_blocks):
                w_curr_chunk = old_w_int[b_idx * self.block_size : (b_idx + 1) * self.block_size]
                if len(w_curr_chunk) < self.block_size:
                    w_curr_chunk = w_curr_chunk + [0] * (self.block_size - len(w_curr_chunk))
                leaf_data = b_idx.to_bytes(4, "big") + b"".join(
                    val.to_bytes(32, "big", signed=True) for val in w_curr_chunk
                )
                corrupt_leaves.append(leaf_data)
                old_model_blocks.append(w_curr_chunk)
            tree = MerkleTree(corrupt_leaves)
            pkg.model_root_next = tree.root
            pkg.model_merkle_tree = tree
            pkg.w_next_blocks = old_model_blocks
            return pkg

        elif self.cheat_type == CheatType.CORRUPTED_BLOCKS:
            return self.corrupt_corrupted_blocks(pkg, self.corrupt_fraction, self.seed)

        elif self.cheat_type == CheatType.FABRICATED_CLIENT:
            # Modify first client leaf with forged signature (flip byte in r coordinate)
            import copy
            pkg.active_packages = [copy.copy(p) for p in pkg.active_packages]
            corrupt_client_leaves = []
            for i, p in enumerate(pkg.active_packages):
                sig = p.signature
                if i == 0:
                    sig = bytes(bytearray(sig[:10]) + bytes([sig[10] ^ 0xff]) + bytearray(sig[11:]))
                    p.signature = sig
                leaf_bytes = (
                    p.client_id.to_bytes(1, "big")
                    + bytes.fromhex(p.address[2:])
                    + p.client_block_root
                    + sig
                )
                corrupt_client_leaves.append(leaf_bytes)
            tree = MerkleTree(corrupt_client_leaves)
            pkg.client_leaves_root = tree.root
            pkg.client_merkle_tree = tree
            return pkg

        return pkg

    @staticmethod
    def corrupt_corrupted_blocks(
        pkg: RoundPostPackage,
        corrupt_fraction: float,
        seed: int,
    ) -> RoundPostPackage:
        """Perturb fraction phi of aggregate blocks U_b without recomputing base commitments."""
        import copy
        new_pkg = copy.copy(pkg)
        num_blocks = len(pkg.u_blocks)
        rng = random.Random(seed)
        k_corrupt = max(1, int(round(num_blocks * corrupt_fraction)))
        corrupt_indices = set(rng.sample(range(num_blocks), min(k_corrupt, num_blocks)))

        corrupt_agg_leaves = []
        corrupt_u_blocks = []
        for b_idx in range(num_blocks):
            u_b = list(pkg.u_blocks[b_idx])
            r_b = pkg.r_blocks[b_idx]
            if b_idx in corrupt_indices:
                u_b[0] += 1
            leaf_data = (
                b_idx.to_bytes(4, "big")
                + r_b.to_bytes(32, "big")
                + b"".join(val.to_bytes(32, "big", signed=True) for val in u_b)
            )
            corrupt_agg_leaves.append(leaf_data)
            corrupt_u_blocks.append(u_b)
        tree = MerkleTree(corrupt_agg_leaves)
        new_pkg.agg_root = tree.root
        new_pkg.agg_merkle_tree = tree
        new_pkg.u_blocks = corrupt_u_blocks
        return new_pkg
