// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Trivial test for verifying Solidity 0.8.28 compilation and test runner
contract TrivialTest {
    function test_trivialArithmetic() public pure {
        assert(1 + 1 == 2);
    }
}
