// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title DomainMerkle
/// @notice Domain-separated Merkle proof verifier.
/// @dev Uses 0x00 prefix for leaves and 0x01 prefix for internal node pairs with sorted ordering.
library DomainMerkle {
    bytes1 internal constant LEAF_PREFIX = 0x00;
    bytes1 internal constant NODE_PREFIX = 0x01;

    /// @notice Computes domain-separated leaf hash.
    /// @param data Raw leaf byte contents.
    /// @return 32-byte leaf hash.
    function hashLeaf(bytes memory data) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(LEAF_PREFIX, data));
    }

    /// @notice Computes domain-separated internal node hash with sorted pair ordering.
    /// @param a First node hash.
    /// @param b Second node hash.
    /// @return 32-byte parent hash.
    function hashInternal(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        if (a <= b) {
            return keccak256(abi.encodePacked(NODE_PREFIX, a, b));
        }
        return keccak256(abi.encodePacked(NODE_PREFIX, b, a));
    }

    /// @notice Verifies inclusion of leaf data in the Merkle root.
    /// @param root Claimed Merkle root hash.
    /// @param leafData Raw bytes of the leaf.
    /// @param proof Array of sibling hashes along the Merkle branch.
    /// @return True if computed root matches claimed root.
    function verifyProof(
        bytes32 root,
        bytes memory leafData,
        bytes32[] memory proof
    ) internal pure returns (bool) {
        bytes32 current = hashLeaf(leafData);
        uint256 len = proof.length;

        for (uint256 i = 0; i < len;) {
            current = hashInternal(current, proof[i]);
            unchecked {
                ++i;
            }
        }

        return current == root;
    }
}
