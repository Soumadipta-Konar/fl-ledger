// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {Session} from "../contracts/Session.sol";
import {BN254} from "../contracts/crypto/BN254.sol";
import {DomainMerkle} from "../contracts/crypto/DomainMerkle.sol";
import {DisputeTypes} from "../contracts/disputes/DisputeTypes.sol";

contract DisputesTest is Test {
    Session internal session;

    address internal admin = address(0xAD);
    address internal server = address(0x5E);
    address internal treasury = address(0x78);
    address internal challenger = address(0xCC);
    address internal adversary = address(0x66);

    address internal client0 = address(0xC0);
    address internal client1 = address(0xC1);

    uint8 internal constant MAX_CLIENTS = 4;
    uint8 internal constant BLOCK_SIZE = 4;
    uint8 internal constant SCALE_BITS = 16;
    uint32 internal constant CHALLENGE_WINDOW = 20;
    uint32 internal constant WITHDRAWAL_DELAY = 40;
    uint256 internal constant BOND_AMOUNT = 10 ether;
    uint256 internal constant CHALLENGER_DEPOSIT = 1 ether;
    uint16 internal constant REWARD_SHARE_BPS = 5000; // 50%

    BN254.G1Point internal hGen;
    BN254.G1Point[] internal gGens;
    bytes32 internal generatorsHash;

    bytes32 internal initialModelRoot;

    // Fixture storage for round 1
    bytes32 internal aggRootHonest;
    bytes32 internal clientLeavesRoot;
    bytes32 internal modelRootNextHonest;
    bytes32 internal aggRootCorrupt;
    bytes32 internal modelRootNextCorrupt;

    bytes32 internal client0BlockRoot;
    bytes32 internal client1BlockRoot;

    BN254.G1Point internal c0Point;
    BN254.G1Point internal c1Point;

    int256[] internal uBlockHonest;
    uint256 internal rBlockHonest;
    int256[] internal uBlockCorrupt;

    int256[] internal wCurrBlock;
    int256[] internal wNextHonest;
    int256[] internal wNextCorrupt;

    bytes32[] internal client0LeafProof;
    bytes32[] internal client1LeafProof;
    bytes32[] internal client0BlockProof;
    bytes32[] internal client1BlockProof;

    bytes32[] internal aggProofHonest;
    bytes32[] internal aggProofCorrupt;
    bytes32[] internal wCurrProof;
    bytes32[] internal wNextHonestProof;
    bytes32[] internal wNextCorruptProof;

    function setUp() public {
        vm.deal(server, 100 ether);
        vm.deal(challenger, 100 ether);
        vm.deal(adversary, 100 ether);

        // 1. Setup BN254 generators
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
            maxClients: MAX_CLIENTS,
            blockSize: BLOCK_SIZE,
            scaleBits: SCALE_BITS,
            challengeWindowBlocks: CHALLENGE_WINDOW,
            withdrawalDelayBlocks: WITHDRAWAL_DELAY,
            bondAmountWei: BOND_AMOUNT,
            challengerDepositWei: CHALLENGER_DEPOSIT,
            rewardShareBps: REWARD_SHARE_BPS,
            generatorsHash: generatorsHash
        });

        vm.prank(admin);
        session = new Session(params);

        // Register clients: client0 (weight 10), client1 (weight 20)
        vm.prank(admin);
        session.register(client0, 10);
        vm.prank(admin);
        session.register(client1, 20);

        // Deposit bond
        vm.prank(server);
        session.depositBond{value: BOND_AMOUNT}();

        // 3. Build Round 0 Initial Model Root
        wCurrBlock = new int256[](BLOCK_SIZE);
        wCurrBlock[0] = 10000;
        wCurrBlock[1] = -20000;
        wCurrBlock[2] = 30000;
        wCurrBlock[3] = -40000;

        bytes memory wCurrLeaf = abi.encodePacked(uint32(0));
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            wCurrLeaf = abi.encodePacked(wCurrLeaf, wCurrBlock[i]);
        }
        bytes32 hCurr0 = DomainMerkle.hashLeaf(wCurrLeaf);
        bytes32 hCurrDummy = DomainMerkle.hashLeaf("dummy_w_leaf");
        initialModelRoot = DomainMerkle.hashInternal(hCurr0, hCurrDummy);

        wCurrProof = new bytes32[](1);
        wCurrProof[0] = hCurrDummy;

        // Start session
        vm.prank(admin);
        session.start(initialModelRoot);

        // 4. Build Client commitments and clientLeavesTree
        // Client 0: q0 = [100, -50, 25, -10], r0 = 12345
        int256[] memory q0 = new int256[](BLOCK_SIZE);
        q0[0] = 100;
        q0[1] = -50;
        q0[2] = 25;
        q0[3] = -10;
        uint256 r0 = 12345;

        c0Point = BN254.ecMul(hGen, r0);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            c0Point = BN254.ecAdd(c0Point, BN254.ecMul(gGens[i], BN254.toScalar(q0[i])));
        }

        bytes memory comm0Leaf = abi.encodePacked(uint32(0), c0Point.x, c0Point.y);
        bytes32 hC0 = DomainMerkle.hashLeaf(comm0Leaf);
        bytes32 hC0Dummy = DomainMerkle.hashLeaf("dummy_comm_0");
        client0BlockRoot = DomainMerkle.hashInternal(hC0, hC0Dummy);
        client0BlockProof = new bytes32[](1);
        client0BlockProof[0] = hC0Dummy;

        // Client 1: q1 = [200, 150, -80, 40], r1 = 67890
        int256[] memory q1 = new int256[](BLOCK_SIZE);
        q1[0] = 200;
        q1[1] = 150;
        q1[2] = -80;
        q1[3] = 40;
        uint256 r1 = 67890;

        c1Point = BN254.ecMul(hGen, r1);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            c1Point = BN254.ecAdd(c1Point, BN254.ecMul(gGens[i], BN254.toScalar(q1[i])));
        }

        bytes memory comm1Leaf = abi.encodePacked(uint32(0), c1Point.x, c1Point.y);
        bytes32 hC1 = DomainMerkle.hashLeaf(comm1Leaf);
        bytes32 hC1Dummy = DomainMerkle.hashLeaf("dummy_comm_1");
        client1BlockRoot = DomainMerkle.hashInternal(hC1, hC1Dummy);
        client1BlockProof = new bytes32[](1);
        client1BlockProof[0] = hC1Dummy;

        // Build client leaves tree
        bytes memory cl0Data = abi.encodePacked(uint8(0), client0, client0BlockRoot, hex"beef");
        bytes memory cl1Data = abi.encodePacked(uint8(1), client1, client1BlockRoot, hex"cafe");
        bytes32 hCl0 = DomainMerkle.hashLeaf(cl0Data);
        bytes32 hCl1 = DomainMerkle.hashLeaf(cl1Data);
        clientLeavesRoot = DomainMerkle.hashInternal(hCl0, hCl1);

        client0LeafProof = new bytes32[](1);
        client0LeafProof[0] = hCl1;
        client1LeafProof = new bytes32[](1);
        client1LeafProof[0] = hCl0;

        // 5. Honest Aggregation: n0 = 10, n1 = 20
        uBlockHonest = new int256[](BLOCK_SIZE);
        uBlockHonest[0] = 10 * 100 + 20 * 200; // 5000
        uBlockHonest[1] = 10 * (-50) + 20 * 150; // 2500
        uBlockHonest[2] = 10 * 25 + 20 * (-80); // -1350
        uBlockHonest[3] = 10 * (-10) + 20 * 40; // 700
        rBlockHonest = (10 * r0 + 20 * r1) % BN254.SCALAR_ORDER;

        bytes memory aggLeafHonest = abi.encodePacked(uint32(0), rBlockHonest);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            aggLeafHonest = abi.encodePacked(aggLeafHonest, uBlockHonest[i]);
        }
        bytes32 hAggH = DomainMerkle.hashLeaf(aggLeafHonest);
        bytes32 hAggDummy = DomainMerkle.hashLeaf("dummy_agg");
        aggRootHonest = DomainMerkle.hashInternal(hAggH, hAggDummy);
        aggProofHonest = new bytes32[](1);
        aggProofHonest[0] = hAggDummy;

        // 6. Corrupt Aggregation (server manipulated entry 0: 5001 instead of 5000)
        uBlockCorrupt = new int256[](BLOCK_SIZE);
        uBlockCorrupt[0] = 5001;
        uBlockCorrupt[1] = 2500;
        uBlockCorrupt[2] = -1350;
        uBlockCorrupt[3] = 700;

        bytes memory aggLeafCorrupt = abi.encodePacked(uint32(0), rBlockHonest);
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            aggLeafCorrupt = abi.encodePacked(aggLeafCorrupt, uBlockCorrupt[i]);
        }
        bytes32 hAggC = DomainMerkle.hashLeaf(aggLeafCorrupt);
        aggRootCorrupt = DomainMerkle.hashInternal(hAggC, hAggDummy);
        aggProofCorrupt = new bytes32[](1);
        aggProofCorrupt[0] = hAggDummy;

        // 7. Honest Next Model: delta = u / 30
        wNextHonest = new int256[](BLOCK_SIZE);
        wNextHonest[0] = wCurrBlock[0] + (uBlockHonest[0] / 30); // 10000 + 166 = 10166
        wNextHonest[1] = wCurrBlock[1] + (uBlockHonest[1] / 30); // -20000 + 83 = -19917
        wNextHonest[2] = wCurrBlock[2] + (uBlockHonest[2] / 30); // 30000 - 45 = 29955
        wNextHonest[3] = wCurrBlock[3] + (uBlockHonest[3] / 30); // -40000 + 23 = -39977

        bytes memory wNextHLeaf = abi.encodePacked(uint32(0));
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            wNextHLeaf = abi.encodePacked(wNextHLeaf, wNextHonest[i]);
        }
        bytes32 hNextH = DomainMerkle.hashLeaf(wNextHLeaf);
        bytes32 hNextDummy = DomainMerkle.hashLeaf("dummy_next_w");
        modelRootNextHonest = DomainMerkle.hashInternal(hNextH, hNextDummy);
        wNextHonestProof = new bytes32[](1);
        wNextHonestProof[0] = hNextDummy;

        // 8. Corrupt Next Model (server corrupted entry 0: +1 cheat)
        wNextCorrupt = new int256[](BLOCK_SIZE);
        wNextCorrupt[0] = wNextHonest[0] + 1; // 10167
        wNextCorrupt[1] = wNextHonest[1];
        wNextCorrupt[2] = wNextHonest[2];
        wNextCorrupt[3] = wNextHonest[3];

        bytes memory wNextCLeaf = abi.encodePacked(uint32(0));
        for (uint256 i = 0; i < BLOCK_SIZE; i++) {
            wNextCLeaf = abi.encodePacked(wNextCLeaf, wNextCorrupt[i]);
        }
        bytes32 hNextC = DomainMerkle.hashLeaf(wNextCLeaf);
        modelRootNextCorrupt = DomainMerkle.hashInternal(hNextC, hNextDummy);
        wNextCorruptProof = new bytes32[](1);
        wNextCorruptProof[0] = hNextDummy;
    }

    // --- Commit-Reveal Window Tests ---

    function test_commitChallenge_revertIncorrectDeposit() public {
        bytes32 commitment = keccak256("test_commit");
        vm.prank(challenger);
        vm.expectRevert(Session.IncorrectDepositAmount.selector);
        session.commitChallenge{value: 0.5 ether}(commitment);
    }

    function test_commitChallenge_revertCommitmentAlreadyExists() public {
        bytes32 commitment = keccak256("test_commit");
        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.prank(challenger);
        vm.expectRevert(Session.CommitmentAlreadyExists.selector);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);
    }

    function test_reveal_revertCommitmentNotFound() public {
        // Post round 1
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: bytes32(uint256(999)),
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextHonest,
            wNextProof: wNextHonestProof
        });

        vm.prank(challenger);
        vm.expectRevert(Session.CommitmentNotFound.selector);
        session.challengeUpdateRule(d2Data);
    }

    function test_reveal_revertRevealSameBlockNotAllowed() public {
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(123));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextHonest,
            wNextProof: wNextHonestProof
        });

        // Calling in the same block reverts!
        vm.prank(challenger);
        vm.expectRevert(Session.RevealSameBlockNotAllowed.selector);
        session.challengeUpdateRule(d2Data);
    }

    function test_reveal_revertUnauthorizedChallenger() public {
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(123));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.roll(block.number + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextHonest,
            wNextProof: wNextHonestProof
        });

        // Calling from adversary address reverts with CommitmentNotFound because commitment is bound to challenger!
        vm.prank(adversary);
        vm.expectRevert(Session.CommitmentNotFound.selector);
        session.challengeUpdateRule(d2Data);
    }

    function test_reveal_revertChallengeWindowExpired() public {
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(123));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        // Advance beyond challenge window
        vm.roll(block.number + CHALLENGE_WINDOW + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextHonest,
            wNextProof: wNextHonestProof
        });

        vm.prank(challenger);
        vm.expectRevert(Session.ChallengeWindowExpired.selector);
        session.challengeUpdateRule(d2Data);
    }

    // --- D1 Aggregation Dispute Tests ---

    function _buildD1Data(
        bytes32 salt,
        int256[] memory uBlock,
        bytes32[] memory aggProof
    ) internal view returns (DisputeTypes.D1DisputeData memory) {
        DisputeTypes.ClientCommitmentData[] memory cp = new DisputeTypes.ClientCommitmentData[](2);
        cp[0] = DisputeTypes.ClientCommitmentData({
            clientIndex: 0,
            clientAddress: client0,
            clientBlockRoot: client0BlockRoot,
            signature: hex"beef",
            clientLeafProof: client0LeafProof,
            commitment: c0Point,
            blockProof: client0BlockProof
        });
        cp[1] = DisputeTypes.ClientCommitmentData({
            clientIndex: 1,
            clientAddress: client1,
            clientBlockRoot: client1BlockRoot,
            signature: hex"cafe",
            clientLeafProof: client1LeafProof,
            commitment: c1Point,
            blockProof: client1BlockProof
        });

        return DisputeTypes.D1DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            hGen: hGen,
            gGens: gGens,
            uBlock: uBlock,
            rBlock: rBlockHonest,
            aggProof: aggProof,
            clientProofs: cp
        });
    }

    function test_d1_honestAggregate_rejected() public {
        // Honest server posts truthful aggregate
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(777));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(1), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.roll(block.number + 1);

        DisputeTypes.D1DisputeData memory d1Data = _buildD1Data(salt, uBlockHonest, aggProofHonest);

        vm.prank(challenger);
        session.challengeAggregation(d1Data);

        // Dispute rejected: honest server is NOT slashed
        assertTrue(session.bondDeposited());
        Session.RoundData memory r = session.getRound(1);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Posted));

        // Challenger deposit forfeited to server
        assertEq(session.withdrawableBalances(server), CHALLENGER_DEPOSIT);
        assertEq(session.withdrawableBalances(challenger), 0);
    }

    function test_d1_corruptedAggregate_upheld_serverSlashed() public {
        // Cheating server posted corrupted aggregate root
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootCorrupt, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(888));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(1), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.roll(block.number + 1);

        DisputeTypes.D1DisputeData memory d1Data = _buildD1Data(salt, uBlockCorrupt, aggProofCorrupt);

        vm.prank(challenger);
        session.challengeAggregation(d1Data);

        // Dispute upheld: server slashed!
        assertFalse(session.bondDeposited());
        Session.RoundData memory r = session.getRound(1);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Invalid));

        // 50% reward to challenger + deposit refund; 50% to treasury
        uint256 expectedReward = (BOND_AMOUNT * REWARD_SHARE_BPS) / 10000; // 5 ether
        assertEq(session.withdrawableBalances(challenger), expectedReward + CHALLENGER_DEPOSIT);
        assertEq(session.withdrawableBalances(treasury), BOND_AMOUNT - expectedReward);
    }

    // --- D2 Update Rule Dispute Tests ---

    function test_d2_honestUpdate_rejected() public {
        vm.prank(server);
        session.postRound(1, modelRootNextHonest, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(555));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.roll(block.number + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextHonest,
            wNextProof: wNextHonestProof
        });

        vm.prank(challenger);
        session.challengeUpdateRule(d2Data);

        // Honest update rule: dispute rejected
        assertTrue(session.bondDeposited());
        Session.RoundData memory r = session.getRound(1);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Posted));
        assertEq(session.withdrawableBalances(server), CHALLENGER_DEPOSIT);
    }

    function test_d2_corruptedUpdate_upheld_serverSlashed() public {
        // Server posted corrupted next model root (+1 off-by-one cheat)
        vm.prank(server);
        session.postRound(1, modelRootNextCorrupt, aggRootHonest, clientLeavesRoot, 3, 30);

        bytes32 salt = bytes32(uint256(666));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));

        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        vm.roll(block.number + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextCorrupt,
            wNextProof: wNextCorruptProof
        });

        vm.prank(challenger);
        session.challengeUpdateRule(d2Data);

        // Fraudulent update: dispute upheld! Server slashed!
        assertFalse(session.bondDeposited());
        Session.RoundData memory r = session.getRound(1);
        assertEq(uint8(r.status), uint8(Session.RoundStatus.Invalid));

        uint256 expectedReward = (BOND_AMOUNT * REWARD_SHARE_BPS) / 10000;
        assertEq(session.withdrawableBalances(challenger), expectedReward + CHALLENGER_DEPOSIT);
        assertEq(session.withdrawableBalances(treasury), BOND_AMOUNT - expectedReward);
    }

    // --- Pull-Payment and Invariant Tests ---

    function test_withdraw_pullPayment() public {
        // Trigger a slash
        test_d2_corruptedUpdate_upheld_serverSlashed();

        uint256 challengerBalBefore = challenger.balance;
        uint256 withdrawable = session.withdrawableBalances(challenger);
        assertTrue(withdrawable > 0);

        vm.prank(challenger);
        session.withdraw();

        assertEq(session.withdrawableBalances(challenger), 0);
        assertEq(challenger.balance, challengerBalBefore + withdrawable);

        // Subsequent withdraw fails
        vm.prank(challenger);
        vm.expectRevert(Session.NothingToWithdraw.selector);
        session.withdraw();
    }

    function test_withdrawBond_revertServerSlashed() public {
        // Trigger a slash
        test_d1_corruptedAggregate_upheld_serverSlashed();

        // Server attempts to withdraw bond
        vm.roll(block.number + WITHDRAWAL_DELAY + 10);
        vm.prank(server);
        vm.expectRevert(Session.BondNotDeposited.selector);
        session.withdrawBond();
    }

    function test_balanceConservationInvariant() public {
        uint256 contractBalStart = address(session).balance;
        assertEq(contractBalStart, BOND_AMOUNT);

        // Challenger commits deposit
        bytes32 salt = bytes32(uint256(111));
        bytes32 commitment = keccak256(abi.encode(1, 0, uint8(2), challenger, salt));
        vm.prank(challenger);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment);

        assertEq(address(session).balance, BOND_AMOUNT + CHALLENGER_DEPOSIT);

        // Post and slash
        vm.prank(server);
        session.postRound(1, modelRootNextCorrupt, aggRootHonest, clientLeavesRoot, 3, 30);

        vm.roll(block.number + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextCorrupt,
            wNextProof: wNextCorruptProof
        });

        vm.prank(challenger);
        session.challengeUpdateRule(d2Data);

        // Balance conserved after slashing into withdrawables
        uint256 totalWithdrawable = session.withdrawableBalances(challenger) +
            session.withdrawableBalances(treasury) +
            session.withdrawableBalances(server);
        assertEq(address(session).balance, totalWithdrawable);
        assertEq(address(session).balance, BOND_AMOUNT + CHALLENGER_DEPOSIT);

        // All parties pull their balances
        vm.prank(challenger);
        session.withdraw();
        vm.prank(treasury);
        session.withdraw();

        assertEq(address(session).balance, 0);
    }

    function test_noDoubleSlashInvariant() public {
        // First slash
        test_d1_corruptedAggregate_upheld_serverSlashed();

        // Adversary attempts second dispute on already slashed round
        bytes32 salt2 = bytes32(uint256(999));
        bytes32 commitment2 = keccak256(abi.encode(1, 0, uint8(2), adversary, salt2));
        vm.prank(adversary);
        session.commitChallenge{value: CHALLENGER_DEPOSIT}(commitment2);

        vm.roll(block.number + 1);

        DisputeTypes.D2DisputeData memory d2Data = DisputeTypes.D2DisputeData({
            round: 1,
            blockIndex: 0,
            salt: salt2,
            wCurrBlock: wCurrBlock,
            wCurrProof: wCurrProof,
            uBlock: uBlockHonest,
            rBlock: rBlockHonest,
            aggProof: aggProofHonest,
            wNextBlock: wNextCorrupt,
            wNextProof: wNextCorruptProof
        });

        // Round is Invalid, so calling dispute reverts with RoundNotPosted!
        vm.prank(adversary);
        vm.expectRevert(Session.RoundNotPosted.selector);
        session.challengeUpdateRule(d2Data);
    }

    // --- Fuzz Testing Update Rule Rounding ---

    function testFuzz_updateRuleSignedTruncation(int256 uVal, uint32 weight) public pure {
        vm.assume(weight > 0);
        vm.assume(uVal > type(int256).min + 1000 && uVal < type(int256).max - 1000);

        int256 delta = uVal / int256(uint256(weight));

        // Truncation toward zero: abs(delta * weight) <= abs(uVal)
        if (uVal >= 0) {
            assertTrue(delta >= 0);
            assertTrue(delta * int256(uint256(weight)) <= uVal);
        } else {
            assertTrue(delta <= 0);
            assertTrue(delta * int256(uint256(weight)) >= uVal);
        }
    }
}
