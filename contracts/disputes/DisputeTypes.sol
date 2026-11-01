// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BN254} from "../crypto/BN254.sol";

/// @title DisputeTypes
/// @notice Data structures for D1 (aggregation) and D2 (update rule) dispute proofs.
library DisputeTypes {
    struct ClientCommitmentData {
        uint8 clientIndex;
        address clientAddress;
        bytes32 clientBlockRoot;
        bytes signature;
        bytes32[] clientLeafProof;
        BN254.G1Point commitment;
        bytes32[] blockProof;
    }

    struct D1DisputeData {
        uint256 round;
        uint32 blockIndex;
        bytes32 salt;
        BN254.G1Point hGen;
        BN254.G1Point[] gGens;
        int256[] uBlock;
        uint256 rBlock;
        bytes32[] aggProof;
        ClientCommitmentData[] clientProofs;
    }

    struct D2DisputeData {
        uint256 round;
        uint32 blockIndex;
        bytes32 salt;
        int256[] wCurrBlock;
        bytes32[] wCurrProof;
        int256[] uBlock;
        uint256 rBlock;
        bytes32[] aggProof;
        int256[] wNextBlock;
        bytes32[] wNextProof;
    }

    struct D4DisputeData {
        uint256 round;
        bytes32 salt;
        uint8 clientIndex;
        address clientAddress;
        bytes32 clientBlockRoot;
        bytes signature;
        bytes32[] clientLeafProof;
    }
}
