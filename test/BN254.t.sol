// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { BN254 } from "../contracts/crypto/BN254.sol";

contract BN254Test is Test {
    // Known BN254 G1 generator: (1, 2)
    BN254.G1Point internal G1_GEN = BN254.G1Point(1, 2);

    function test_isOnCurve_validPoints() public view {
        assertTrue(BN254.isOnCurve(G1_GEN));
        assertTrue(BN254.isOnCurve(BN254.G1Point(0, 0))); // Point at infinity
    }

    function test_isOnCurve_invalidPoints() public pure {
        assertFalse(BN254.isOnCurve(BN254.G1Point(1, 3))); // 3^2 != 1^3 + 3
        assertFalse(BN254.isOnCurve(BN254.G1Point(BN254.FIELD_PRIME, 2))); // >= field prime
    }

    function test_ecAdd_identity() public view {
        BN254.G1Point memory zero = BN254.G1Point(0, 0);
        BN254.G1Point memory res1 = BN254.ecAdd(G1_GEN, zero);
        assertTrue(BN254.equals(res1, G1_GEN));

        BN254.G1Point memory res2 = BN254.ecAdd(zero, G1_GEN);
        assertTrue(BN254.equals(res2, G1_GEN));
    }

    function test_ecMul_basic() public view {
        BN254.G1Point memory zero = BN254.ecMul(G1_GEN, 0);
        assertTrue(BN254.equals(zero, BN254.G1Point(0, 0)));

        BN254.G1Point memory one = BN254.ecMul(G1_GEN, 1);
        assertTrue(BN254.equals(one, G1_GEN));

        BN254.G1Point memory twoMul = BN254.ecMul(G1_GEN, 2);
        BN254.G1Point memory twoAdd = BN254.ecAdd(G1_GEN, G1_GEN);
        assertTrue(BN254.equals(twoMul, twoAdd));
    }

    function test_toScalar_edgeCases() public pure {
        assertEq(BN254.toScalar(0), 0);
        assertEq(BN254.toScalar(1), 1);
        assertEq(BN254.toScalar(42), 42);

        // Negative values: should map to SCALAR_ORDER - |val|
        assertEq(BN254.toScalar(-1), BN254.SCALAR_ORDER - 1);
        assertEq(BN254.toScalar(-42), BN254.SCALAR_ORDER - 42);

        // Minimum integer bound edge case
        uint256 minScalar = BN254.toScalar(type(int256).min);
        assertTrue(minScalar < BN254.SCALAR_ORDER);
    }

    function testFuzz_toScalar(int256 val) public pure {
        uint256 s = BN254.toScalar(val);
        assertTrue(s < BN254.SCALAR_ORDER);

        if (val == 0) {
            assertEq(s, 0);
        } else if (val > 0) {
            assertEq(s, uint256(val) % BN254.SCALAR_ORDER);
        } else {
            uint256 absVal;
            unchecked {
                absVal = uint256(-val);
            }
            uint256 rem = absVal % BN254.SCALAR_ORDER;
            uint256 expected = rem == 0 ? 0 : BN254.SCALAR_ORDER - rem;
            assertEq(s, expected);
        }
    }
}
