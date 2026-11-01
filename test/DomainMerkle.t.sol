// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {DomainMerkle} from "../contracts/crypto/DomainMerkle.sol";

contract DomainMerkleTest is Test {
    function test_domainPrefixSeparation() public pure {
        bytes memory leafData = "hello";
        bytes32 leafHash = DomainMerkle.hashLeaf(leafData);

        // Explicit check of 0x00 prefix
        bytes32 manualLeafHash = keccak256(abi.encodePacked(bytes1(0x00), leafData));
        assertEq(leafHash, manualLeafHash);

        bytes32 a = keccak256("left");
        bytes32 b = keccak256("right");
        bytes32 nodeHash = DomainMerkle.hashInternal(a, b);

        // Sorted pair ordering check
        bytes32 manualNodeHash;
        if (a <= b) {
            manualNodeHash = keccak256(abi.encodePacked(bytes1(0x01), a, b));
        } else {
            manualNodeHash = keccak256(abi.encodePacked(bytes1(0x01), b, a));
        }
        assertEq(nodeHash, manualNodeHash);

        // Domain separation ensures leaf hash != node hash for identical concatenated content
        assertTrue(leafHash != nodeHash);
    }

    function test_sortedPairCommutativity() public pure {
        bytes32 a = keccak256("item1");
        bytes32 b = keccak256("item2");
        assertEq(DomainMerkle.hashInternal(a, b), DomainMerkle.hashInternal(b, a));
    }

    function test_twoLeafTreeProof() public pure {
        bytes memory leaf0 = "leaf_zero";
        bytes memory leaf1 = "leaf_one";

        bytes32 h0 = DomainMerkle.hashLeaf(leaf0);
        bytes32 h1 = DomainMerkle.hashLeaf(leaf1);
        bytes32 root = DomainMerkle.hashInternal(h0, h1);

        bytes32[] memory proof0 = new bytes32[](1);
        proof0[0] = h1;

        bytes32[] memory proof1 = new bytes32[](1);
        proof1[0] = h0;

        assertTrue(DomainMerkle.verifyProof(root, leaf0, proof0));
        assertTrue(DomainMerkle.verifyProof(root, leaf1, proof1));

        // Wrong leaf data must fail
        assertFalse(DomainMerkle.verifyProof(root, "tampered_leaf", proof0));

        // Tampered proof must fail
        bytes32[] memory badProof = new bytes32[](1);
        badProof[0] = keccak256("bogus");
        assertFalse(DomainMerkle.verifyProof(root, leaf0, badProof));
    }
}
