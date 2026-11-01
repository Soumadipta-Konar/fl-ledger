"""Federated learning client with quantisation, Pedersen commitments, and EIP-712 signing."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from ledger.fixed import quantise, DEFAULT_SCALE_BITS, DEFAULT_BOUND_B, BN254_SCALAR_ORDER
from ledger.commit import commit_block, Point
from ledger.merkle import MerkleTree
from ledger.sign import sign_client_root
from sim.model import SmallMLP


@dataclass
class ClientUpdatePackage:
    client_id: int
    address: str
    weight: int
    q_blocks: list[list[int]]
    r_blocks: list[int]
    commitments: list[Point]
    block_merkle_tree: MerkleTree
    client_block_root: bytes
    signature: bytes
    nonce: int


class Client:
    """Federated learning client participant."""

    def __init__(
        self,
        client_id: int,
        address: str,
        private_key: str,
        weight: int,
        data: tuple[np.ndarray, np.ndarray],
    ) -> None:
        self.client_id = client_id
        self.address = address
        self.private_key = private_key
        self.weight = weight
        self.x_train, self.y_train = data

    def compute_update(
        self,
        global_flat_weights: np.ndarray,
        block_size: int,
        session_id: bytes,
        round_num: int,
        chain_id: int,
        contract_address: str,
        nonce: int,
        scale_bits: int = DEFAULT_SCALE_BITS,
        bound: int = DEFAULT_BOUND_B,
        seed: int = 42,
    ) -> ClientUpdatePackage:
        """Train locally, quantise updates, compute Pedersen commitments, and sign root."""
        # 1. Local training step
        local_model = SmallMLP(seed=seed + self.client_id)
        local_model.set_flat_weights(global_flat_weights.copy())
        local_model.train_step(self.x_train, self.y_train, lr=0.05)

        # 2. Compute delta
        local_flat = local_model.get_flat_weights()
        delta = local_flat - global_flat_weights

        # 3. Quantise
        q_vec = [quantise(float(v), scale_bits=scale_bits, bound=bound) for v in delta]

        # 4. Partition into blocks of size m
        q_blocks: list[list[int]] = []
        r_blocks: list[int] = []
        commitments: list[Point] = []
        raw_leaves: list[bytes] = []

        rng = random.Random(seed + round_num * 1000 + self.client_id)

        for b_idx in range(0, len(q_vec), block_size):
            chunk = q_vec[b_idx : b_idx + block_size]
            if len(chunk) < block_size:
                chunk = chunk + [0] * (block_size - len(chunk))

            r_val = rng.randint(1, BN254_SCALAR_ORDER - 1)
            comm = commit_block(chunk, r_val)

            q_blocks.append(chunk)
            r_blocks.append(r_val)
            commitments.append(comm)

            # Canonical leaf encoding for client block commitment
            leaf_payload = (
                (b_idx // block_size).to_bytes(4, "big")
                + comm[0].to_bytes(32, "big")
                + comm[1].to_bytes(32, "big")
            )
            raw_leaves.append(leaf_payload)

        # 5. Build Merkle tree over block commitments
        block_tree = MerkleTree(raw_leaves)
        client_block_root = block_tree.root

        # 6. EIP-712 structured signing
        sig = sign_client_root(
            private_key=self.private_key,
            session=session_id,
            round_num=round_num,
            client=self.address,
            root=client_block_root,
            nonce=nonce,
            chain_id=chain_id,
            verifying_contract=contract_address,
        )

        return ClientUpdatePackage(
            client_id=self.client_id,
            address=self.address,
            weight=self.weight,
            q_blocks=q_blocks,
            r_blocks=r_blocks,
            commitments=commitments,
            block_merkle_tree=block_tree,
            client_block_root=client_block_root,
            signature=sig,
            nonce=nonce,
        )
