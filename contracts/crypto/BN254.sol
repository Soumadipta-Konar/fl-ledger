// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title BN254
/// @notice Elliptic curve operations for alt_bn128 (BN254) G1 group using EVM precompiles 0x06 and 0x07.
/// @dev Precompiles ecAdd (0x06) and ecMul (0x07) operate on uncompressed affine coordinates.
library BN254 {
    uint256 internal constant FIELD_PRIME =
        21888242871839275222246405745257275088696311157297823662689037894645226208583;
    uint256 internal constant SCALAR_ORDER =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;

    struct G1Point {
        uint256 x;
        uint256 y;
    }

    error PrecompileCallFailed();
    error InvalidCurvePoint();

    /// @notice Converts signed integer to a scalar field element in [0, SCALAR_ORDER - 1].
    /// @param val Signed integer value.
    /// @return Reduced scalar field representation.
    function toScalar(int256 val) internal pure returns (uint256) {
        if (val >= 0) {
            return uint256(val) % SCALAR_ORDER;
        }
        uint256 absVal;
        unchecked {
            absVal = uint256(-val);
        }
        uint256 rem = absVal % SCALAR_ORDER;
        return rem == 0 ? 0 : SCALAR_ORDER - rem;
    }

    /// @notice Validates that a point satisfies y^2 = x^3 + 3 (mod q).
    /// @param p Affine G1 point.
    /// @return True if valid point on BN254 G1 or point at infinity (0, 0).
    function isOnCurve(G1Point memory p) internal pure returns (bool) {
        if (p.x == 0 && p.y == 0) return true;
        if (p.x >= FIELD_PRIME || p.y >= FIELD_PRIME) return false;

        uint256 lhs = mulmod(p.y, p.y, FIELD_PRIME);
        uint256 x2 = mulmod(p.x, p.x, FIELD_PRIME);
        uint256 x3 = mulmod(x2, p.x, FIELD_PRIME);
        uint256 rhs = addmod(x3, 3, FIELD_PRIME);

        return lhs == rhs;
    }

    /// @notice Adds two G1 curve points using EVM precompile 0x06.
    /// @param p1 First point.
    /// @param p2 Second point.
    /// @return result Point sum on G1.
    function ecAdd(G1Point memory p1, G1Point memory p2) internal view returns (G1Point memory result) {
        if (p1.x == 0 && p1.y == 0) return p2;
        if (p2.x == 0 && p2.y == 0) return p1;

        uint256[4] memory input = [p1.x, p1.y, p2.x, p2.y];
        bool success;
        assembly ("memory-safe") {
            success := staticcall(gas(), 0x06, input, 128, result, 64)
        }
        if (!success) revert PrecompileCallFailed();
    }

    /// @notice Multiplies a G1 curve point by an integer scalar using EVM precompile 0x07.
    /// @param p G1 point.
    /// @param scalar Multiplier integer.
    /// @return result Point product on G1.
    function ecMul(G1Point memory p, uint256 scalar) internal view returns (G1Point memory result) {
        uint256 s = scalar % SCALAR_ORDER;
        if (s == 0 || (p.x == 0 && p.y == 0)) {
            return G1Point(0, 0);
        }

        uint256[3] memory input = [p.x, p.y, s];
        bool success;
        assembly ("memory-safe") {
            success := staticcall(gas(), 0x07, input, 96, result, 64)
        }
        if (!success) revert PrecompileCallFailed();
    }

    /// @notice Checks equality between two G1 points.
    function equals(G1Point memory a, G1Point memory b) internal pure returns (bool) {
        return a.x == b.x && a.y == b.y;
    }
}
