// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BN254} from "../crypto/BN254.sol";
import {DomainMerkle} from "../crypto/DomainMerkle.sol";
import {DisputeTypes} from "./DisputeTypes.sol";

/// @title DisputeVerifier
/// @notice Cryptographic and arithmetic verification logic for disputes D1 and D2.
library DisputeVerifier {
    error GeneratorHashMismatch();
    error AggProofFailed();
    error ModelProofFailed();
    error ClientProofFailed();

    /// @notice Validates that provided generators match the committed generatorsHash.
    function verifyGenerators(
        BN254.G1Point calldata hGen,
        BN254.G1Point[] calldata gGens,
        bytes32 expectedHash
    ) internal pure {
        bytes memory raw = abi.encodePacked(hGen.x, hGen.y);
        uint256 len = gGens.length;
        for (uint256 i = 0; i < len;) {
            raw = abi.encodePacked(raw, gGens[i].x, gGens[i].y);
            unchecked {
                ++i;
            }
        }
        if (keccak256(raw) != expectedHash) revert GeneratorHashMismatch();
    }

    /// @notice Verifies D1 aggregation equation: sum n_k C_{k,b} == Com(U_b; R_b).
    /// @return upheld True if the server's aggregate was fraudulent (mismatch detected).
    function verifyD1Aggregation(
        DisputeTypes.D1DisputeData calldata data,
        bytes32 aggRoot,
        bytes32 clientLeavesRoot,
        uint32[] memory participantWeights
    ) internal view returns (bool upheld) {
        // 1. Verify aggregate leaf inclusion in aggRoot
        bytes memory aggLeafData = abi.encodePacked(
            data.blockIndex,
            data.rBlock
        );
        for (uint256 i = 0; i < data.uBlock.length;) {
            aggLeafData = abi.encodePacked(aggLeafData, data.uBlock[i]);
            unchecked {
                ++i;
            }
        }
        if (!DomainMerkle.verifyProof(aggRoot, aggLeafData, data.aggProof)) {
            revert AggProofFailed();
        }

        // 2. Verify client commitments and compute LHS = sum_k n_k * C_{k,b}
        BN254.G1Point memory lhs = BN254.G1Point(0, 0);
        uint256 numParticipants = data.clientProofs.length;

        for (uint256 k = 0; k < numParticipants;) {
            DisputeTypes.ClientCommitmentData calldata cp = data.clientProofs[k];

            // Verify client leaf inclusion in clientLeavesRoot:
            bytes memory clientLeaf = abi.encodePacked(
                cp.clientIndex,
                cp.clientAddress,
                cp.clientBlockRoot,
                cp.signature
            );
            if (!DomainMerkle.verifyProof(clientLeavesRoot, clientLeaf, cp.clientLeafProof)) {
                revert ClientProofFailed();
            }

            // Verify commitment leaf inclusion in clientBlockRoot:
            bytes memory commLeaf = abi.encodePacked(
                data.blockIndex,
                cp.commitment.x,
                cp.commitment.y
            );
            if (!DomainMerkle.verifyProof(cp.clientBlockRoot, commLeaf, cp.blockProof)) {
                revert ClientProofFailed();
            }

            if (!BN254.isOnCurve(cp.commitment)) {
                // Invalid curve point submitted in aggregate -> upheld
                return true;
            }

            BN254.G1Point memory term = BN254.ecMul(cp.commitment, participantWeights[k]);
            lhs = BN254.ecAdd(lhs, term);

            unchecked {
                ++k;
            }
        }

        // 3. Compute RHS = R_b * H + sum_i (U_{b,i} * G_i)
        BN254.G1Point memory rhs = BN254.ecMul(data.hGen, data.rBlock);

        uint256 blockSize = data.uBlock.length;
        for (uint256 i = 0; i < blockSize;) {
            uint256 s = BN254.toScalar(data.uBlock[i]);
            BN254.G1Point memory gTerm = BN254.ecMul(data.gGens[i], s);
            rhs = BN254.ecAdd(rhs, gTerm);
            unchecked {
                ++i;
            }
        }

        // Upheld if server's claimed aggregate does not match participant commitments
        return !BN254.equals(lhs, rhs);
    }

    /// @notice Verifies D2 update rule: W_{t+1,b} == W_{t,b} + div(U_b, claimedWeight).
    /// @return upheld True if server's updated model violated integer truncation division.
    function verifyD2UpdateRule(
        DisputeTypes.D2DisputeData calldata data,
        bytes32 prevModelRoot,
        bytes32 aggRoot,
        bytes32 nextModelRoot,
        uint32 claimedWeight
    ) internal pure returns (bool upheld) {
        // 1. Verify W_{t,b} inclusion in prevModelRoot
        bytes memory prevLeaf = abi.encodePacked(data.blockIndex);
        for (uint256 i = 0; i < data.wCurrBlock.length;) {
            prevLeaf = abi.encodePacked(prevLeaf, data.wCurrBlock[i]);
            unchecked {
                ++i;
            }
        }
        if (!DomainMerkle.verifyProof(prevModelRoot, prevLeaf, data.wCurrProof)) {
            revert ModelProofFailed();
        }

        // 2. Verify U_b inclusion in aggRoot
        bytes memory aggLeaf = abi.encodePacked(data.blockIndex, data.rBlock);
        for (uint256 i = 0; i < data.uBlock.length;) {
            aggLeaf = abi.encodePacked(aggLeaf, data.uBlock[i]);
            unchecked {
                ++i;
            }
        }
        if (!DomainMerkle.verifyProof(aggRoot, aggLeaf, data.aggProof)) {
            revert AggProofFailed();
        }

        // 3. Verify W_{t+1,b} inclusion in nextModelRoot
        bytes memory nextLeaf = abi.encodePacked(data.blockIndex);
        for (uint256 i = 0; i < data.wNextBlock.length;) {
            nextLeaf = abi.encodePacked(nextLeaf, data.wNextBlock[i]);
            unchecked {
                ++i;
            }
        }
        if (!DomainMerkle.verifyProof(nextModelRoot, nextLeaf, data.wNextProof)) {
            revert ModelProofFailed();
        }

        // 4. Element-wise update check with native Solidity truncation toward zero
        int256 totalWeight = int256(uint256(claimedWeight));
        uint256 len = data.wCurrBlock.length;

        for (uint256 i = 0; i < len;) {
            int256 delta = data.uBlock[i] / totalWeight;
            int256 expected = data.wCurrBlock[i] + delta;
            if (data.wNextBlock[i] != expected) {
                // Fraudulent update step detected!
                return true;
            }
            unchecked {
                ++i;
            }
        }

        // Updates were faithfully computed
        return false;
    }
}
