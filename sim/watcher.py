"""Off-chain watcher auditing server roots, homomorphic commitments, and update rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from ledger.commit import commit_block, homomorphic_sum
from ledger.fixed import div_truncate
from ledger.merkle import verify_proof
from ledger.sign import verify_client_signature
from sim.server import RoundPostPackage


@dataclass
class AuditVerdict:
    passed: bool
    deviation_type: str | None = None  # "INVALID_SIGNATURE", "WEIGHT_MISMATCH", "D1_HOMOMORPHISM", "D2_UPDATE_RULE"
    failed_block_idx: int | None = None
    failed_client_idx: int | None = None


class Watcher:
    """Auditor sampling blocks to verify honest server aggregation."""

    def __init__(self, chain_id: int, contract_address: str, session_id: bytes) -> None:
        self.chain_id = chain_id
        self.contract_address = contract_address
        self.session_id = session_id

    def audit_round(
        self,
        post_pkg: RoundPostPackage,
        w_curr_blocks: Sequence[Sequence[int]],
        sampled_block_indices: Sequence[int] | None = None,
    ) -> AuditVerdict:
        """Comprehensive audit returning detailed verdict and failure location."""
        # 1. Verify client signatures (D4b)
        for idx, pkg in enumerate(post_pkg.active_packages):
            valid_sig = verify_client_signature(
                signature=pkg.signature,
                session=self.session_id,
                round_num=post_pkg.round_num,
                expected_client=pkg.address,
                root=pkg.client_block_root,
                nonce=pkg.nonce,
                chain_id=self.chain_id,
                verifying_contract=self.contract_address,
            )
            if not valid_sig:
                return AuditVerdict(
                    passed=False,
                    deviation_type="INVALID_SIGNATURE",
                    failed_client_idx=idx,
                )

        # 2. Check participant weights
        expected_weight = sum(pkg.weight for pkg in post_pkg.active_packages)
        if expected_weight != post_pkg.claimed_weight:
            return AuditVerdict(
                passed=False,
                deviation_type="WEIGHT_MISMATCH",
            )

        # 3. Sample and audit blocks
        num_blocks = len(post_pkg.u_blocks)
        if sampled_block_indices is None:
            indices = list(range(min(5, num_blocks)))
        else:
            indices = list(sampled_block_indices)

        for b in indices:
            b_idx = int(b)
            if b_idx < 0 or b_idx >= num_blocks:
                continue

            # a. Check client commitment inclusion in client block tree
            for pkg in post_pkg.active_packages:
                comm = pkg.commitments[b_idx]
                leaf_payload = (
                    b_idx.to_bytes(4, "big")
                    + comm[0].to_bytes(32, "big")
                    + comm[1].to_bytes(32, "big")
                )
                proof = pkg.block_merkle_tree.get_proof(b_idx)
                if not verify_proof(pkg.client_block_root, leaf_payload, proof):
                    return AuditVerdict(
                        passed=False,
                        deviation_type="CLIENT_COMMITMENT_PROOF_FAILED",
                        failed_block_idx=b_idx,
                    )

            # b. Check Homomorphism (D1): sum_k n_k C_{k,b} == Com(U_b; R_b)
            client_comms = [pkg.commitments[b_idx] for pkg in post_pkg.active_packages]
            client_weights = [pkg.weight for pkg in post_pkg.active_packages]
            lhs = homomorphic_sum(client_comms, client_weights)

            u_b = post_pkg.u_blocks[b_idx]
            r_b = post_pkg.r_blocks[b_idx]
            rhs = commit_block(u_b, r_b)

            if lhs != rhs:
                return AuditVerdict(
                    passed=False,
                    deviation_type="D1_HOMOMORPHISM",
                    failed_block_idx=b_idx,
                )

            # c. Check Update Rule (D2): W_{t+1,b} == W_{t,b} + div_truncate(U_b, claimed_weight)
            w_curr = w_curr_blocks[b_idx]
            w_next = post_pkg.w_next_blocks[b_idx]
            for i in range(len(u_b)):
                expected_w = w_curr[i] + div_truncate(u_b[i], post_pkg.claimed_weight)
                if w_next[i] != expected_w:
                    return AuditVerdict(
                        passed=False,
                        deviation_type="D2_UPDATE_RULE",
                        failed_block_idx=b_idx,
                    )

        return AuditVerdict(passed=True)

    def verify_round(
        self,
        post_pkg: RoundPostPackage,
        w_curr_blocks: Sequence[Sequence[int]],
        sampled_block_indices: Sequence[int] | None = None,
    ) -> bool:
        """Audit round: verify client signatures, homomorphic commitments, and update rules."""
        verdict = self.audit_round(post_pkg, w_curr_blocks, sampled_block_indices)
        return verdict.passed
