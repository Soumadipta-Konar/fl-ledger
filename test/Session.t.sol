// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { Session } from "../contracts/Session.sol";
import { IAccessControl } from "@openzeppelin/contracts/access/IAccessControl.sol";

contract SessionTest is Test {
    Session internal session;

    address internal admin = makeAddr("admin");
    address internal server = makeAddr("server");
    address internal treasury = makeAddr("treasury");
    address internal client1 = makeAddr("client1");
    address internal client2 = makeAddr("client2");
    address internal client3 = makeAddr("client3");

    uint48 internal constant ADMIN_DELAY = 1 days;
    uint8 internal constant MAX_CLIENTS = 16;
    uint8 internal constant BLOCK_SIZE = 16;
    uint8 internal constant SCALE_BITS = 16;
    uint32 internal constant CHALLENGE_WINDOW = 20;
    uint32 internal constant WITHDRAWAL_DELAY = 40;
    uint256 internal constant BOND_AMOUNT = 10 ether;
    uint256 internal constant CHALLENGER_DEPOSIT = 1 ether;
    uint16 internal constant REWARD_SHARE_BPS = 5000; // 50%
    bytes32 internal constant GENERATORS_HASH =
        0xe652044a86d69ffa665a025c9d84022f1ed2c28b2ad38f6f44d33fb7513781b9;

    bytes32 internal initialModelRoot = keccak256("modelRoot_0");

    function setUp() public {
        Session.InitParams memory params = Session.InitParams({
            initialAdmin: admin,
            adminDelay: ADMIN_DELAY,
            server: server,
            treasury: treasury,
            maxClients: MAX_CLIENTS,
            blockSize: BLOCK_SIZE,
            scaleBits: SCALE_BITS,
            challengeWindowBlocks: CHALLENGE_WINDOW,
            withdrawalDelayBlocks: WITHDRAWAL_DELAY,
            bondAmountWei: BOND_AMOUNT,
            challengerDepositWei: CHALLENGER_DEPOSIT,
            rewardShareBps: REWARD_SHARE_BPS,
            generatorsHash: GENERATORS_HASH
        });

        session = new Session(params);
        vm.deal(server, 100 ether);
    }

    // --- Constructor Tests ---

    function test_constructor_success() public view {
        assertEq(session.server(), server);
        assertEq(session.treasury(), treasury);
        assertEq(session.maxClients(), MAX_CLIENTS);
        assertEq(session.blockSize(), BLOCK_SIZE);
        assertEq(session.scaleBits(), SCALE_BITS);
        assertEq(session.challengeWindowBlocks(), CHALLENGE_WINDOW);
        assertEq(session.withdrawalDelayBlocks(), WITHDRAWAL_DELAY);
        assertEq(session.bondAmountWei(), BOND_AMOUNT);
        assertEq(session.challengerDepositWei(), CHALLENGER_DEPOSIT);
        assertEq(session.rewardShareBps(), REWARD_SHARE_BPS);
        assertEq(session.generatorsHash(), GENERATORS_HASH);
        assertEq(uint8(session.phase()), uint8(Session.Phase.Registration));
    }

    function test_constructor_revertZeroServer() public {
        Session.InitParams memory params = _defaultParams();
        params.server = address(0);
        vm.expectRevert(Session.InvalidParameter.selector);
        new Session(params);
    }

    function test_constructor_revertZeroTreasury() public {
        Session.InitParams memory params = _defaultParams();
        params.treasury = address(0);
        vm.expectRevert(Session.InvalidParameter.selector);
        new Session(params);
    }

    function test_constructor_revertMaxClientsLimit() public {
        Session.InitParams memory params = _defaultParams();
        params.maxClients = 65; // exceeds 64
        vm.expectRevert(Session.InvalidParameter.selector);
        new Session(params);
    }

    // --- Registration Tests ---

    function test_register_success() public {
        vm.prank(admin);
        session.register(client1, 100);

        assertEq(session.getClientCount(), 1);
        (address addr, uint32 weight) = session.getClient(0);
        assertEq(addr, client1);
        assertEq(weight, 100);
    }

    function test_register_revertUnauthorized() public {
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector,
                client1,
                session.DEFAULT_ADMIN_ROLE()
            )
        );
        vm.prank(client1);
        session.register(client1, 100);
    }

    function test_register_revertZeroAddress() public {
        vm.prank(admin);
        vm.expectRevert(Session.ZeroAddressNotAllowed.selector);
        session.register(address(0), 100);
    }

    function test_register_revertZeroWeight() public {
        vm.prank(admin);
        vm.expectRevert(Session.ZeroWeightNotAllowed.selector);
        session.register(client1, 0);
    }

    function test_register_revertDuplicateClient() public {
        vm.startPrank(admin);
        session.register(client1, 100);
        vm.expectRevert(Session.ClientAlreadyRegistered.selector);
        session.register(client1, 50);
        vm.stopPrank();
    }

    function test_register_revertMaxClientsExceeded() public {
        Session.InitParams memory params = _defaultParams();
        params.maxClients = 2;
        Session s = new Session(params);

        vm.startPrank(admin);
        s.register(client1, 10);
        s.register(client2, 20);
        vm.expectRevert(Session.MaxClientsExceeded.selector);
        s.register(client3, 30);
        vm.stopPrank();
    }

    // --- Bond Deposit Tests ---

    function test_depositBond_success() public {
        vm.prank(server);
        session.depositBond{ value: BOND_AMOUNT }();

        assertTrue(session.bondDeposited());
        assertEq(address(session).balance, BOND_AMOUNT);
    }

    function test_depositBond_revertIncorrectAmount() public {
        vm.prank(server);
        vm.expectRevert(Session.IncorrectBondAmount.selector);
        session.depositBond{ value: 5 ether }();
    }

    function test_depositBond_revertOnlyServer() public {
        vm.deal(client1, BOND_AMOUNT);
        vm.expectRevert(Session.OnlyServerAllowed.selector);
        vm.prank(client1);
        session.depositBond{ value: BOND_AMOUNT }();
    }

    function test_depositBond_revertAlreadyDeposited() public {
        vm.startPrank(server);
        session.depositBond{ value: BOND_AMOUNT }();
        vm.expectRevert(Session.BondAlreadyDeposited.selector);
        session.depositBond{ value: BOND_AMOUNT }();
        vm.stopPrank();
    }

    // --- Start Session Tests ---

    function test_start_success() public {
        _registerClientsAndDepositBond();

        vm.prank(admin);
        session.start(initialModelRoot);

        assertEq(uint8(session.phase()), uint8(Session.Phase.Active));
        assertEq(session.currentModelRoot(), initialModelRoot);
        assertEq(session.currentRound(), 0);
    }

    function test_start_revertBondNotDeposited() public {
        vm.prank(admin);
        session.register(client1, 100);

        vm.prank(admin);
        vm.expectRevert(Session.BondNotDeposited.selector);
        session.start(initialModelRoot);
    }

    function test_start_revertNoClientsRegistered() public {
        vm.prank(server);
        session.depositBond{ value: BOND_AMOUNT }();

        vm.prank(admin);
        vm.expectRevert(Session.NoClientsRegistered.selector);
        session.start(initialModelRoot);
    }

    function test_start_freezesRegistry() public {
        _registerClientsAndDepositBond();

        vm.prank(admin);
        session.start(initialModelRoot);

        // Subsequent registration attempts must revert
        vm.prank(admin);
        vm.expectRevert(Session.InvalidPhase.selector);
        session.register(client3, 50);
    }

    // --- Post Round Tests ---

    function test_postRound_success() public {
        _startSessionWithTwoClients();

        bytes32 modelRoot1 = keccak256("modelRoot_1");
        bytes32 aggRoot1 = keccak256("aggRoot_1");
        bytes32 clientRoot1 = keccak256("clientLeavesRoot_1");

        // Mask = 3 (binary 11: both client 0 and client 1 active). Weight = 100 + 200 = 300
        vm.prank(server);
        session.postRound(1, modelRoot1, aggRoot1, clientRoot1, 3, 300);

        Session.RoundData memory r = session.getRound(1);
        assertEq(r.modelRootNext, modelRoot1);
        assertEq(r.aggRoot, aggRoot1);
        assertEq(r.clientLeavesRoot, clientRoot1);
        assertEq(r.participantMask, 3);
        assertEq(r.claimedWeight, 300);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Posted));
        assertEq(r.postedBlock, block.number);
    }

    function test_postRound_revertInvalidRoundSequence() public {
        _startSessionWithTwoClients();

        vm.prank(server);
        vm.expectRevert(Session.InvalidRoundSequence.selector);
        session.postRound(2, bytes32(0), bytes32(0), bytes32(0), 1, 100);
    }

    function test_postRound_revertEmptyMask() public {
        _startSessionWithTwoClients();

        vm.prank(server);
        vm.expectRevert(Session.EmptyParticipantMask.selector);
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 0, 0);
    }

    function test_postRound_revertInvalidParticipantBit() public {
        _startSessionWithTwoClients(); // 2 clients registered (indices 0 and 1)

        // Mask = 4 (binary 100: bit 2 is set, but only indices 0 and 1 exist)
        vm.prank(server);
        vm.expectRevert(abi.encodeWithSelector(Session.InvalidParticipantBit.selector, 2));
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 4, 100);
    }

    function test_postRound_revertClaimedWeightMismatch() public {
        _startSessionWithTwoClients(); // weights: client1=100, client2=200

        // Mask = 1 (client1 only), claimed weight = 999 (mismatch)
        vm.prank(server);
        vm.expectRevert(abi.encodeWithSelector(Session.ClaimedWeightMismatch.selector, 100, 999));
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 1, 999);
    }

    // --- Finalize Round Tests ---

    function test_finalizeRound_success() public {
        _startSessionWithTwoClients();

        bytes32 modelRoot1 = keccak256("modelRoot_1");
        vm.prank(server);
        session.postRound(1, modelRoot1, bytes32(0), bytes32(0), 1, 100);

        // Advance blocks past challenge window
        vm.roll(block.number + CHALLENGE_WINDOW);

        session.finalizeRound(1);

        Session.RoundData memory r = session.getRound(1);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Finalized));
        assertEq(session.currentRound(), 1);
        assertEq(session.currentModelRoot(), modelRoot1);
    }

    function test_finalizeRound_revertChallengeWindowActive() public {
        _startSessionWithTwoClients();

        vm.prank(server);
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 1, 100);

        // Attempt finalize within window
        vm.roll(block.number + CHALLENGE_WINDOW - 1);
        vm.expectRevert(Session.ChallengeWindowActive.selector);
        session.finalizeRound(1);
    }

    // --- Withdraw Bond Tests ---

    function test_withdrawBond_success() public {
        _startSessionWithTwoClients();

        vm.prank(server);
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 1, 100);

        vm.roll(block.number + CHALLENGE_WINDOW);
        session.finalizeRound(1);

        // Advance blocks past withdrawal delay
        vm.roll(block.number + WITHDRAWAL_DELAY);

        uint256 balanceBefore = server.balance;
        vm.prank(server);
        session.withdrawBond();

        assertEq(server.balance - balanceBefore, BOND_AMOUNT);
        assertEq(uint8(session.phase()), uint8(Session.Phase.Closed));
    }

    function test_withdrawBond_revertWithdrawalDelayActive() public {
        _startSessionWithTwoClients();

        vm.prank(server);
        session.postRound(1, bytes32(0), bytes32(0), bytes32(0), 1, 100);

        vm.roll(block.number + CHALLENGE_WINDOW);
        session.finalizeRound(1);

        // Try before withdrawal delay elapsed
        vm.roll(block.number + WITHDRAWAL_DELAY - 1);
        vm.prank(server);
        vm.expectRevert(Session.WithdrawalDelayActive.selector);
        session.withdrawBond();
    }

    // --- Fuzz Tests ---

    function testFuzz_registerWeightsAndMasks(uint32 w1, uint32 w2, bool p1, bool p2) public {
        vm.assume(w1 > 0 && w1 <= 1_000_000);
        vm.assume(w2 > 0 && w2 <= 1_000_000);
        vm.assume(p1 || p2); // at least one participant

        Session.InitParams memory params = _defaultParams();
        Session s = new Session(params);

        vm.startPrank(admin);
        s.register(client1, w1);
        s.register(client2, w2);
        vm.stopPrank();

        vm.prank(server);
        s.depositBond{ value: BOND_AMOUNT }();

        vm.prank(admin);
        s.start(initialModelRoot);

        uint64 mask = 0;
        uint32 expectedW = 0;
        if (p1) {
            mask |= 1;
            expectedW += w1;
        }
        if (p2) {
            mask |= 2;
            expectedW += w2;
        }

        vm.prank(server);
        s.postRound(1, bytes32(0), bytes32(0), bytes32(0), mask, expectedW);

        Session.RoundData memory r = s.getRound(1);
        assertEq(r.participantMask, mask);
        assertEq(r.claimedWeight, expectedW);
    }

    // --- Internal Helpers ---

    function _defaultParams() internal view returns (Session.InitParams memory) {
        return Session.InitParams({
            initialAdmin: admin,
            adminDelay: ADMIN_DELAY,
            server: server,
            treasury: treasury,
            maxClients: MAX_CLIENTS,
            blockSize: BLOCK_SIZE,
            scaleBits: SCALE_BITS,
            challengeWindowBlocks: CHALLENGE_WINDOW,
            withdrawalDelayBlocks: WITHDRAWAL_DELAY,
            bondAmountWei: BOND_AMOUNT,
            challengerDepositWei: CHALLENGER_DEPOSIT,
            rewardShareBps: REWARD_SHARE_BPS,
            generatorsHash: GENERATORS_HASH
        });
    }

    function _registerClientsAndDepositBond() internal {
        vm.startPrank(admin);
        session.register(client1, 100);
        session.register(client2, 200);
        vm.stopPrank();

        vm.prank(server);
        session.depositBond{ value: BOND_AMOUNT }();
    }

    function _startSessionWithTwoClients() internal {
        _registerClientsAndDepositBond();
        vm.prank(admin);
        session.start(initialModelRoot);
    }
}
