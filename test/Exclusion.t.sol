// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { Session } from "../contracts/Session.sol";
import { DisputeTypes } from "../contracts/disputes/DisputeTypes.sol";
import { BN254 } from "../contracts/crypto/BN254.sol";
import { DomainMerkle } from "../contracts/crypto/DomainMerkle.sol";

contract ExclusionTest is Test {
    Session internal session;

    address internal admin = address(0xAD);
    address internal server = address(0x5E);
    address internal treasury = address(0x78);
    address internal challenger = address(0x99);

    uint256 internal client0Key = 0xA11CE;
    uint256 internal client1Key = 0xB0B;
    uint256 internal client2Key = 0xCA501;

    address internal client0;
    address internal client1;
    address internal client2;
    address internal nonClient = address(0x999);

    uint256 internal constant BOND_AMOUNT = 10 ether;
    uint256 internal constant CHALLENGER_DEPOSIT = 1 ether;
    uint32 internal constant CHALLENGE_WINDOW = 20;
    uint32 internal constant WITHDRAWAL_DELAY = 40;
    uint8 internal constant BLOCK_SIZE = 16;
    uint8 internal constant SCALE_BITS = 16;

    BN254.G1Point internal hGen;
    BN254.G1Point[] internal gGens;
    bytes32 internal generatorsHash;
    bytes32 internal MODEL_ROOT_0;

    // Cryptographic data for D1 testing
    BN254.G1Point internal c0Point;
    BN254.G1Point internal c1Point;
    BN254.G1Point internal c2Point;
    bytes32 internal client0BlockRoot;
    bytes32 internal client1BlockRoot;
    bytes32 internal client2BlockRoot;
    bytes32[] internal client0BlockProof;
    bytes32[] internal client1BlockProof;
    bytes32[] internal client2BlockProof;
    bytes internal sig0;
    bytes internal sig1;
    bytes internal sig2;

    event ExclusionRequested(
        address indexed client,
        uint8 indexed clientIndex,
        uint256 indexed epoch,
        uint256 startRound,
        uint64 newRetainedMask
    );
    event ChallengeUpheld(
        uint256 indexed round, uint32 indexed blockIndex, address indexed challenger
    );
    event ServerSlashed(
        uint256 indexed round,
        address indexed challenger,
        uint256 challengerReward,
        uint256 treasuryReward
    );

    function setUp() public {
        client0 = vm.addr(client0Key);
        client1 = vm.addr(client1Key);
        client2 = vm.addr(client2Key);

        vm.deal(admin, 100 ether);
        vm.deal(server, 100 ether);
        vm.deal(challenger, 100 ether);
        vm.deal(client0, 10 ether);
        vm.deal(client1, 10 ether);
        vm.deal(client2, 10 ether);
        vm.deal(nonClient, 10 ether);

        // 1. Setup generators
        hGen = BN254.G1Point(1, 2);
        bytes memory rawGens = abi.encodePacked(hGen.x, hGen.y);
        for (uint256 i = 0; i < 32; i++) {
            BN254.G1Point memory pt = BN254.ecMul(hGen, i + 3);
            gGens.push(pt);
            rawGens = abi.encodePacked(rawGens, pt.x, pt.y);
        }
        generatorsHash = keccak256(rawGens);

        // 2. Deploy Session
        Session.InitParams memory params = Session.InitParams({
            initialAdmin: admin,
            adminDelay: 0,
            server: server,
            treasury: treasury,
            maxClients: 3,
            blockSize: BLOCK_SIZE,
            scaleBits: SCALE_BITS,
            challengeWindowBlocks: CHALLENGE_WINDOW,
            withdrawalDelayBlocks: WITHDRAWAL_DELAY,
            bondAmountWei: BOND_AMOUNT,
            challengerDepositWei: CHALLENGER_DEPOSIT,
            rewardShareBps: 5000,
            generatorsHash: generatorsHash
        });

        session = new Session(params);

        vm.startPrank(admin);
        session.register(client0, 10);
        session.register(client1, 20);
        session.register(client2, 30);
        vm.stopPrank();

        vm.prank(server);
        session.depositBond{ value: BOND_AMOUNT }();

        // 3. Initial model root
        int256[] memory w0 = new int256[](BLOCK_SIZE);
        w0[0] = 10000;
        w0[1] = -20000;
        bytes memory w0Leaf = abi.encodePacked(uint32(0));
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            w0Leaf = abi.encodePacked(w0Leaf, w0[i]);
        }
        bytes32 hW0 = DomainMerkle.hashLeaf(w0Leaf);
        bytes32 hWDummy = DomainMerkle.hashLeaf("dummy_w_leaf");
        MODEL_ROOT_0 = DomainMerkle.hashInternal(hW0, hWDummy);

        vm.prank(admin);
        session.start(MODEL_ROOT_0);

        // 4. Client vectors and commitments
        // Client 0: q0 = [100, -50, ...], r0 = 12345
        int256[] memory q0 = new int256[](BLOCK_SIZE);
        q0[0] = 100;
        q0[1] = -50;
        uint256 r0 = 12345;
        c0Point = BN254.ecMul(hGen, r0);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            c0Point = BN254.ecAdd(c0Point, BN254.ecMul(gGens[i], BN254.toScalar(q0[i])));
        }
        bytes memory c0Leaf = abi.encodePacked(uint32(0), c0Point.x, c0Point.y);
        bytes32 hC0 = DomainMerkle.hashLeaf(c0Leaf);
        bytes32 hC0Dummy = DomainMerkle.hashLeaf("dummy_c0");
        client0BlockRoot = DomainMerkle.hashInternal(hC0, hC0Dummy);
        client0BlockProof = new bytes32[](1);
        client0BlockProof[0] = hC0Dummy;

        // Client 1: q1 = [200, 150, ...], r1 = 67890
        int256[] memory q1 = new int256[](BLOCK_SIZE);
        q1[0] = 200;
        q1[1] = 150;
        uint256 r1 = 67890;
        c1Point = BN254.ecMul(hGen, r1);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            c1Point = BN254.ecAdd(c1Point, BN254.ecMul(gGens[i], BN254.toScalar(q1[i])));
        }
        bytes memory c1Leaf = abi.encodePacked(uint32(0), c1Point.x, c1Point.y);
        bytes32 hC1 = DomainMerkle.hashLeaf(c1Leaf);
        bytes32 hC1Dummy = DomainMerkle.hashLeaf("dummy_c1");
        client1BlockRoot = DomainMerkle.hashInternal(hC1, hC1Dummy);
        client1BlockProof = new bytes32[](1);
        client1BlockProof[0] = hC1Dummy;

        // Client 2: q2 = [500, -300, ...], r2 = 11111
        int256[] memory q2 = new int256[](BLOCK_SIZE);
        q2[0] = 500;
        q2[1] = -300;
        uint256 r2 = 11111;
        c2Point = BN254.ecMul(hGen, r2);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            c2Point = BN254.ecAdd(c2Point, BN254.ecMul(gGens[i], BN254.toScalar(q2[i])));
        }
        bytes memory c2Leaf = abi.encodePacked(uint32(0), c2Point.x, c2Point.y);
        bytes32 hC2 = DomainMerkle.hashLeaf(c2Leaf);
        bytes32 hC2Dummy = DomainMerkle.hashLeaf("dummy_c2");
        client2BlockRoot = DomainMerkle.hashInternal(hC2, hC2Dummy);
        client2BlockProof = new bytes32[](1);
        client2BlockProof[0] = hC2Dummy;

        // 5. Client EIP-712 Signatures for round 1
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("FL-Ledger"),
                keccak256("1"),
                block.chainid,
                address(session)
            )
        );
        bytes32 sessionId = bytes32(uint256(uint160(address(session))));

        bytes32 structHash0 = keccak256(
            abi.encode(
                session.CLIENT_ROOT_TYPEHASH(),
                sessionId,
                uint256(1),
                client0,
                client0BlockRoot,
                uint256(0)
            )
        );
        (uint8 v0, bytes32 r0_s, bytes32 s0_s) = vm.sign(
            client0Key, keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash0))
        );
        sig0 = abi.encodePacked(r0_s, s0_s, v0);

        bytes32 structHash1 = keccak256(
            abi.encode(
                session.CLIENT_ROOT_TYPEHASH(),
                sessionId,
                uint256(1),
                client1,
                client1BlockRoot,
                uint256(0)
            )
        );
        (uint8 v1, bytes32 r1_s, bytes32 s1_s) = vm.sign(
            client1Key, keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash1))
        );
        sig1 = abi.encodePacked(r1_s, s1_s, v1);

        bytes32 structHash2 = keccak256(
            abi.encode(
                session.CLIENT_ROOT_TYPEHASH(),
                sessionId,
                uint256(1),
                client2,
                client2BlockRoot,
                uint256(0)
            )
        );
        (uint8 v2, bytes32 r2_s, bytes32 s2_s) = vm.sign(
            client2Key, keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash2))
        );
        sig2 = abi.encodePacked(r2_s, s2_s, v2);
    }

    function test_initialRetainedMask() public view {
        assertEq(session.getRetainedMask(), 7);
        assertEq(session.getEpoch(), 0);
        assertFalse(session.isExcluded(client0));
        assertFalse(session.isExcluded(client1));
        assertFalse(session.isExcluded(client2));
    }

    function test_requestExclusion_revertNonClient() public {
        vm.prank(nonClient);
        vm.expectRevert(Session.ClientNotRegistered.selector);
        session.requestExclusion();
    }

    function test_requestExclusion_revertUnauthorizedIndex() public {
        vm.prank(client0);
        vm.expectRevert(Session.UnauthorizedClient.selector);
        session.requestExclusion(1);
    }

    function test_requestExclusion_beforeParticipation() public {
        vm.prank(client2);
        vm.expectEmit(true, true, true, true);
        emit ExclusionRequested(client2, 2, 0, 0, 3);
        session.requestExclusion();

        assertTrue(session.isExcluded(client2));
        assertEq(session.getRetainedMask(), 3);
        assertEq(session.getEpoch(), 0);

        bytes32 m1 = keccak256("model_1");
        bytes32 a1 = keccak256("agg_1");
        bytes32 c1 = keccak256("clients_1");

        vm.prank(server);
        vm.expectRevert(abi.encodeWithSelector(Session.ExcludedParticipantBit.selector, 2));
        session.postRound(1, m1, a1, c1, 7, 60);

        vm.prank(server);
        session.postRound(1, m1, a1, c1, 3, 30);

        Session.RoundData memory r = session.getRound(1);
        assertEq(r.participantMask, 3);
        assertEq(r.claimedWeight, 30);
    }

    function test_requestExclusion_revertAlreadyExcluded() public {
        vm.prank(client2);
        session.requestExclusion();

        vm.prank(client2);
        vm.expectRevert(Session.ClientAlreadyExcluded.selector);
        session.requestExclusion();
    }

    function test_requestExclusion_revertWhileChallengeWindowActive() public {
        bytes32 m1 = keccak256("model_1");
        bytes32 a1 = keccak256("agg_1");
        bytes32 c1 = keccak256("clients_1");

        vm.prank(server);
        session.postRound(1, m1, a1, c1, 7, 60);

        vm.prank(client2);
        vm.expectRevert(Session.ChallengeWindowActive.selector);
        session.requestExclusion();
    }

    function test_exclusionEpoch_fullLifecycle() public {
        // 1. Execute Round 1 with all 3 clients (mask 7, weight 60)
        bytes32 m1 = keccak256("m1");
        bytes32 a1 = keccak256("a1");
        bytes32 c1 = keccak256("c1");

        vm.prank(server);
        session.postRound(1, m1, a1, c1, 7, 60);

        vm.roll(block.number + CHALLENGE_WINDOW + 1);
        session.finalizeRound(1);
        assertEq(session.currentRound(), 1);
        assertEq(session.currentModelRoot(), m1);

        // 2. Execute Round 2 with all 3 clients
        bytes32 m2 = keccak256("m2");
        bytes32 a2 = keccak256("a2");
        bytes32 c2 = keccak256("c2");

        vm.prank(server);
        session.postRound(2, m2, a2, c2, 7, 60);

        vm.roll(block.number + CHALLENGE_WINDOW + 1);
        session.finalizeRound(2);
        assertEq(session.currentRound(), 2);
        assertEq(session.currentModelRoot(), m2);

        // 3. Client 2 requests exclusion
        uint256 gasBefore = gasleft();
        vm.prank(client2);
        vm.expectEmit(true, true, true, true);
        emit ExclusionRequested(client2, 2, 1, 1, 3);
        session.requestExclusion();
        uint256 gasUsed = gasBefore - gasleft();
        emit log_named_uint("Gas used for requestExclusion (epoch trigger)", gasUsed);

        // Verify Epoch 1 state
        assertEq(session.getEpoch(), 1);
        assertEq(session.getRetainedMask(), 3);
        assertTrue(session.isExcluded(client2));
        assertEq(session.currentRound(), 0);
        assertEq(session.currentModelRoot(), MODEL_ROOT_0);

        // Active rounds 1 and 2 cleared
        assertEq(uint8(session.getRound(1).status), uint8(Session.RoundStatus.None));
        assertEq(uint8(session.getRound(2).status), uint8(Session.RoundStatus.None));

        // Epoch 0 immutable history preserved
        Session.RoundData memory epoch0_r1 = session.getEpochRound(0, 1);
        assertEq(epoch0_r1.modelRootNext, m1);
        assertEq(epoch0_r1.participantMask, 7);

        // 4. Server attempts cheating: include excluded client 2 in Epoch 1 Round 1
        bytes32 m1_rerun_bad = keccak256("m1_rerun_bad");
        vm.prank(server);
        vm.expectRevert(abi.encodeWithSelector(Session.ExcludedParticipantBit.selector, 2));
        session.postRound(1, m1_rerun_bad, a1, c1, 7, 60);

        // Server attempts cheating: include non-registered client bit
        vm.prank(server);
        vm.expectRevert(abi.encodeWithSelector(Session.InvalidParticipantBit.selector, 3));
        session.postRound(1, m1_rerun_bad, a1, c1, 8, 30);

        // 5. Faithful re-run of Round 1 with retained set (clients 0 and 1: mask 3, weight 30)
        bytes32 m1_rerun = keccak256("m1_retained");
        bytes32 a1_rerun = keccak256("a1_retained");
        bytes32 c1_rerun = keccak256("c1_retained");

        vm.prank(server);
        session.postRound(1, m1_rerun, a1_rerun, c1_rerun, 3, 30);

        assertEq(session.getRound(1).participantMask, 3);
        assertEq(session.getRound(1).claimedWeight, 30);

        vm.roll(block.number + CHALLENGE_WINDOW + 1);
        session.finalizeRound(1);
        assertEq(session.currentRound(), 1);
        assertEq(session.currentModelRoot(), m1_rerun);

        // 6. Faithful re-run of Round 2 with retained set
        bytes32 m2_rerun = keccak256("m2_retained");
        bytes32 a2_rerun = keccak256("a2_retained");
        bytes32 c2_rerun = keccak256("c2_retained");

        vm.prank(server);
        session.postRound(2, m2_rerun, a2_rerun, c2_rerun, 3, 30);

        vm.roll(block.number + CHALLENGE_WINDOW + 1);
        session.finalizeRound(2);
        assertEq(session.currentRound(), 2);
        assertEq(session.currentModelRoot(), m2_rerun);

        // 7. Server withdraws bond after withdrawal delay
        vm.roll(block.number + WITHDRAWAL_DELAY + 1);
        uint256 serverBalBefore = server.balance;
        vm.prank(server);
        session.withdrawBond();
        assertEq(server.balance - serverBalBefore, BOND_AMOUNT);
        assertEq(uint8(session.phase()), uint8(Session.Phase.Closed));
    }

    function test_exclusionEpoch_d1DisputeUpheld_secretClientInclusion() public {
        // Round 1 runs with all 3 clients
        bytes32 m1 = keccak256("m1");
        bytes32 a1 = keccak256("a1");
        bytes32 c1 = keccak256("c1");

        vm.prank(server);
        session.postRound(1, m1, a1, c1, 7, 60);

        vm.roll(block.number + CHALLENGE_WINDOW + 1);
        session.finalizeRound(1);

        // Client 2 requests exclusion -> enters Epoch 1, retained mask = 3
        vm.prank(client2);
        session.requestExclusion();
        assertEq(session.getEpoch(), 1);
        assertEq(session.getRetainedMask(), 3);

        // In Epoch 1 Round 1:
        // Server creates a cheating aggregate U_b that secretly includes client 2's data!
        // True retained aggregate (clients 0 and 1 only):
        // U[0] = 10 * 100 + 20 * 200 = 5000
        // But server secretly adds client 2 (weight 30 * 500 = 15000):
        // Cheating U[0] = 5000 + 15000 = 20000!
        int256[] memory uBlockCheat = new int256[](BLOCK_SIZE);
        uBlockCheat[0] = 20000;
        uBlockCheat[1] = 10 * (-50) + 20 * 150 + 30 * (-300); // secretly tainted
        uint256 rBlockCheat = (10 * 12345 + 20 * 67890 + 30 * 11111) % BN254.SCALAR_ORDER;

        bytes memory aggLeafCheat = abi.encodePacked(uint32(0), rBlockCheat);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            aggLeafCheat = abi.encodePacked(aggLeafCheat, uBlockCheat[i]);
        }
        bytes32 hAggC = DomainMerkle.hashLeaf(aggLeafCheat);
        bytes32 hAggDummy = DomainMerkle.hashLeaf("dummy_agg");
        bytes32 aggRootCheat = DomainMerkle.hashInternal(hAggC, hAggDummy);
        bytes32[] memory aggProof = new bytes32[](1);
        aggProof[0] = hAggDummy;

        // Build client leaves root for the retained participants (client 0 and client 1)
        bytes memory cl0Data = abi.encodePacked(uint8(0), client0, client0BlockRoot, sig0);
        bytes memory cl1Data = abi.encodePacked(uint8(1), client1, client1BlockRoot, sig1);
        bytes32 hCl0 = DomainMerkle.hashLeaf(cl0Data);
        bytes32 hCl1 = DomainMerkle.hashLeaf(cl1Data);
        bytes32 clientLeavesRootRetained = DomainMerkle.hashInternal(hCl0, hCl1);

        bytes32[] memory cl0Proof = new bytes32[](1);
        cl0Proof[0] = hCl1;
        bytes32[] memory cl1Proof = new bytes32[](1);
        cl1Proof[0] = hCl0;

        // Server posts round with participantMask = 3 (claiming only clients 0 and 1)
        bytes32 m1_cheat = keccak256("m1_cheat");
        vm.prank(server);
        session.postRound(1, m1_cheat, aggRootCheat, clientLeavesRootRetained, 3, 30);

        // Challenger detects that U_b does not equal 10*C0 + 20*C1!
        // Challenger commits challenge
        bytes32 salt = bytes32(uint256(0x5A17));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(1), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{ value: CHALLENGER_DEPOSIT }(commitment);

        vm.roll(block.number + 1);

        // Challenger reveals D1 dispute
        DisputeTypes.ClientCommitmentData[] memory cp = new DisputeTypes.ClientCommitmentData[](2);
        cp[0] = DisputeTypes.ClientCommitmentData({
            clientIndex: 0,
            clientAddress: client0,
            clientBlockRoot: client0BlockRoot,
            signature: sig0,
            clientLeafProof: cl0Proof,
            commitment: c0Point,
            blockProof: client0BlockProof
        });
        cp[1] = DisputeTypes.ClientCommitmentData({
            clientIndex: 1,
            clientAddress: client1,
            clientBlockRoot: client1BlockRoot,
            signature: sig1,
            clientLeafProof: cl1Proof,
            commitment: c1Point,
            blockProof: client1BlockProof
        });

        DisputeTypes.D1DisputeData memory d1Data = DisputeTypes.D1DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            hGen: hGen,
            gGens: gGens,
            uBlock: uBlockCheat,
            rBlock: rBlockCheat,
            aggProof: aggProof,
            clientProofs: cp
        });

        vm.expectEmit(true, true, true, true);
        emit ChallengeUpheld(1, 0, challenger);
        vm.expectEmit(true, true, true, true);
        emit ServerSlashed(1, challenger, 5 ether, 5 ether);

        vm.prank(challenger);
        session.challengeAggregation(d1Data);

        // Assert server was slashed and challenger rewarded
        assertFalse(session.bondDeposited());
        assertEq(uint8(session.getRound(1).status), uint8(Session.RoundStatus.Invalid));
        assertEq(session.withdrawableBalances(challenger), 5 ether + CHALLENGER_DEPOSIT);
        assertEq(session.withdrawableBalances(treasury), 5 ether);
    }
}
