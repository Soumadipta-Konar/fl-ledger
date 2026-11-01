// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {AccessControlDefaultAdminRules} from
    "@openzeppelin/contracts/access/extensions/AccessControlDefaultAdminRules.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {BN254} from "./crypto/BN254.sol";
import {DomainMerkle} from "./crypto/DomainMerkle.sol";
import {DisputeTypes} from "./disputes/DisputeTypes.sol";
import {DisputeVerifier} from "./disputes/DisputeVerifier.sol";

/// @title Session
/// @notice Manages FL session lifecycle, participant registry, optimistic round anchoring, and disputes.
/// @dev Implements optimistic verification where rounds finalize after challengeWindowBlocks without dispute.
contract Session is AccessControlDefaultAdminRules, ReentrancyGuard, EIP712 {
    using SafeCast for uint256;

    // --- Limits and Constants ---
    uint8 public constant MAX_CLIENTS_LIMIT = 64;
    uint8 public constant MAX_BLOCK_SIZE_LIMIT = 32;

    bytes32 public constant CLIENT_ROOT_TYPEHASH = keccak256(
        "ClientRoot(bytes32 session,uint256 round,address client,bytes32 root,uint256 nonce)"
    );

    // --- State Machine ---
    enum Phase {
        Registration,
        Active,
        Closed
    }

    enum RoundStatus {
        None,
        Posted,
        Finalized,
        Invalid
    }

    struct RoundData {
        bytes32 modelRootNext;
        bytes32 aggRoot;
        bytes32 clientLeavesRoot;
        uint64 participantMask;
        uint32 claimedWeight;
        uint32 postedBlock;
        RoundStatus status;
    }

    struct InitParams {
        address initialAdmin;
        uint48 adminDelay;
        address server;
        address treasury;
        uint8 maxClients;
        uint8 blockSize;
        uint8 scaleBits;
        uint32 challengeWindowBlocks;
        uint32 withdrawalDelayBlocks;
        uint256 bondAmountWei;
        uint256 challengerDepositWei;
        uint16 rewardShareBps;
        bytes32 generatorsHash;
    }

    struct ClientInfo {
        uint32 weight;
        uint8 index;
        bool registered;
    }

    struct ChallengeCommitment {
        address challenger;
        uint32 committedBlock;
        bool active;
    }

    // --- Immutables ---
    address public immutable server;
    address public immutable treasury;
    uint8 public immutable maxClients;
    uint8 public immutable blockSize;
    uint8 public immutable scaleBits;
    uint32 public immutable challengeWindowBlocks;
    uint32 public immutable withdrawalDelayBlocks;
    uint256 public immutable bondAmountWei;
    uint256 public immutable challengerDepositWei;
    uint16 public immutable rewardShareBps;
    bytes32 public immutable generatorsHash;

    // --- State Variables ---
    Phase public phase;
    bool public bondDeposited;
    bytes32 public currentModelRoot;
    uint256 public currentRound;
    uint256 public lastFinalizedBlock;

    address[] private _clientAddresses;
    mapping(address => ClientInfo) public clientRegistry;
    mapping(uint256 => RoundData) public rounds;
    mapping(bytes32 => ChallengeCommitment) public challengeCommitments;
    mapping(address => uint256) public withdrawableBalances;

    // --- Events ---
    event ClientRegistered(address indexed client, uint32 weight, uint8 index);
    event BondDeposited(address indexed server, uint256 amount);
    event SessionStarted(bytes32 indexed initialModelRoot, uint8 clientCount);
    event RoundPosted(
        uint256 indexed round,
        bytes32 modelRootNext,
        bytes32 aggRoot,
        bytes32 clientLeavesRoot,
        uint64 participantMask,
        uint32 claimedWeight,
        uint32 postedBlock
    );
    event RoundFinalized(uint256 indexed round, bytes32 indexed newModelRoot);
    event BondWithdrawn(address indexed server, uint256 amount);
    event ChallengeCommitted(address indexed challenger, bytes32 indexed commitment, uint32 committedBlock);
    event ChallengeUpheld(uint256 indexed round, uint32 indexed blockIndex, address indexed challenger);
    event ChallengeRejected(uint256 indexed round, uint32 indexed blockIndex, address indexed challenger);
    event ServerSlashed(
        uint256 indexed round,
        address indexed challenger,
        uint256 challengerReward,
        uint256 treasuryReward
    );
    event Withdrawn(address indexed recipient, uint256 amount);

    // --- Custom Errors ---
    error InvalidParameter();
    error OnlyServerAllowed();
    error InvalidPhase();
    error ClientAlreadyRegistered();
    error MaxClientsExceeded();
    error ZeroAddressNotAllowed();
    error ZeroWeightNotAllowed();
    error IncorrectBondAmount();
    error BondAlreadyDeposited();
    error BondNotDeposited();
    error NoClientsRegistered();
    error InvalidRoundSequence();
    error RoundAlreadyPosted();
    error EmptyParticipantMask();
    error InvalidParticipantBit(uint8 bitIndex);
    error ClaimedWeightMismatch(uint32 expected, uint32 actual);
    error ChallengeWindowActive();
    error RoundNotPosted();
    error WithdrawalDelayActive();
    error TransferFailed();
    error IncorrectDepositAmount();
    error CommitmentAlreadyExists();
    error CommitmentNotFound();
    error UnauthorizedChallenger();
    error RevealSameBlockNotAllowed();
    error ChallengeWindowExpired();
    error InvalidBlockLength();
    error InvalidGeneratorsLength();
    error InvalidParticipantCount();
    error InvalidParticipantIndex();
    error InvalidParticipantAddress();
    error NothingToWithdraw();
    error ServerAlreadySlashed();
    error ParticipantNotActive();
    error ClientProofFailed();

    // --- Modifiers ---
    modifier onlyServer() {
        if (msg.sender != server) revert OnlyServerAllowed();
        _;
    }

    modifier inPhase(Phase expected) {
        if (phase != expected) revert InvalidPhase();
        _;
    }

    /// @notice Constructs a new Session contract with verified immutable parameters.
    /// @param params Struct holding all initialization parameters.
    constructor(InitParams memory params)
        AccessControlDefaultAdminRules(params.adminDelay, params.initialAdmin)
        EIP712("FL-Ledger", "1")
    {
        if (
            params.server == address(0) || params.treasury == address(0) || params.maxClients == 0
                || params.maxClients > MAX_CLIENTS_LIMIT || params.blockSize == 0
                || params.blockSize > MAX_BLOCK_SIZE_LIMIT || params.scaleBits == 0
                || params.challengeWindowBlocks == 0 || params.withdrawalDelayBlocks == 0
                || params.rewardShareBps > 10000 || params.generatorsHash == bytes32(0)
        ) {
            revert InvalidParameter();
        }

        server = params.server;
        treasury = params.treasury;
        maxClients = params.maxClients;
        blockSize = params.blockSize;
        scaleBits = params.scaleBits;
        challengeWindowBlocks = params.challengeWindowBlocks;
        withdrawalDelayBlocks = params.withdrawalDelayBlocks;
        bondAmountWei = params.bondAmountWei;
        challengerDepositWei = params.challengerDepositWei;
        rewardShareBps = params.rewardShareBps;
        generatorsHash = params.generatorsHash;

        phase = Phase.Registration;
    }

    /// @notice Registers a client with address and integer weight.
    /// @dev Can only be called by the admin during Registration phase.
    /// @param client Participant wallet address.
    /// @param weight Positive integer weight.
    function register(address client, uint32 weight)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
        inPhase(Phase.Registration)
    {
        if (client == address(0)) revert ZeroAddressNotAllowed();
        if (weight == 0) revert ZeroWeightNotAllowed();
        if (clientRegistry[client].registered) revert ClientAlreadyRegistered();
        if (_clientAddresses.length >= maxClients) revert MaxClientsExceeded();

        uint8 index = _clientAddresses.length.toUint8();
        clientRegistry[client] = ClientInfo({weight: weight, index: index, registered: true});
        _clientAddresses.push(client);

        emit ClientRegistered(client, weight, index);
    }

    /// @notice Deposits the server security bond.
    /// @dev Requires exact bondAmountWei sent with transaction during Registration phase.
    function depositBond() external payable nonReentrant onlyServer inPhase(Phase.Registration) {
        if (bondDeposited) revert BondAlreadyDeposited();
        if (msg.value != bondAmountWei) revert IncorrectBondAmount();

        bondDeposited = true;
        emit BondDeposited(msg.sender, msg.value);
    }

    /// @notice Freezes client registry and transitions session from Registration to Active.
    /// @param initialModelRoot Merkle root of round 0 initial model vector.
    function start(bytes32 initialModelRoot)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
        inPhase(Phase.Registration)
    {
        if (!bondDeposited) revert BondNotDeposited();
        if (_clientAddresses.length == 0) revert NoClientsRegistered();

        currentModelRoot = initialModelRoot;
        rounds[0].modelRootNext = initialModelRoot;
        rounds[0].status = RoundStatus.Finalized;

        phase = Phase.Active;

        emit SessionStarted(initialModelRoot, _clientAddresses.length.toUint8());
    }

    /// @notice Posts aggregate roots and client commitment roots for round t.
    /// @param round Sequential round index (must equal currentRound + 1).
    /// @param modelRootNext Root of updated model vector W_{t+1}.
    /// @param aggRoot Root of aggregate vector blocks U_b and blindings R_b.
    /// @param clientLeavesRoot Root of participant EIP-712 commitment leaves.
    /// @param participantMask Bitmask of active participants in round.
    /// @param claimedWeight Sum of weights of active participants.
    function postRound(
        uint256 round,
        bytes32 modelRootNext,
        bytes32 aggRoot,
        bytes32 clientLeavesRoot,
        uint64 participantMask,
        uint32 claimedWeight
    ) external onlyServer inPhase(Phase.Active) {
        if (round != currentRound + 1) revert InvalidRoundSequence();
        if (rounds[round].status != RoundStatus.None) revert RoundAlreadyPosted();
        if (participantMask == 0) revert EmptyParticipantMask();

        uint256 numClients = _clientAddresses.length;
        uint32 expectedWeight = 0;

        for (uint8 i = 0; i < numClients;) {
            if ((participantMask & (uint64(1) << uint64(i))) != 0) {
                expectedWeight += clientRegistry[_clientAddresses[i]].weight;
            }
            unchecked {
                ++i;
            }
        }

        // Verify no bits set beyond registered client count
        if (numClients < 64 && participantMask >= (uint64(1) << uint64(numClients))) {
            revert InvalidParticipantBit(numClients.toUint8());
        }

        if (claimedWeight != expectedWeight) {
            revert ClaimedWeightMismatch(expectedWeight, claimedWeight);
        }

        uint32 currentBlock = block.number.toUint32();
        rounds[round] = RoundData({
            modelRootNext: modelRootNext,
            aggRoot: aggRoot,
            clientLeavesRoot: clientLeavesRoot,
            participantMask: participantMask,
            claimedWeight: claimedWeight,
            postedBlock: currentBlock,
            status: RoundStatus.Posted
        });

        emit RoundPosted(
            round,
            modelRootNext,
            aggRoot,
            clientLeavesRoot,
            participantMask,
            claimedWeight,
            currentBlock
        );
    }

    /// @notice Commits a hash of challenge data to prevent front-running.
    /// @param commitment Hash of (round, blockIndex, disputeType, msg.sender, salt).
    function commitChallenge(bytes32 commitment)
        external
        payable
        nonReentrant
        inPhase(Phase.Active)
    {
        if (msg.value != challengerDepositWei) revert IncorrectDepositAmount();
        if (challengeCommitments[commitment].active) revert CommitmentAlreadyExists();

        challengeCommitments[commitment] = ChallengeCommitment({
            challenger: msg.sender,
            committedBlock: block.number.toUint32(),
            active: true
        });

        emit ChallengeCommitted(msg.sender, commitment, block.number.toUint32());
    }

    /// @notice Reveals challenge data for D1 (aggregation dispute).
    /// @param data Dispute calldata including generators, aggregate block, and client proofs.
    function challengeAggregation(DisputeTypes.D1DisputeData calldata data)
        external
        nonReentrant
        inPhase(Phase.Active)
    {
        RoundData storage r = rounds[data.round];
        if (r.status != RoundStatus.Posted) revert RoundNotPosted();
        if (block.number > r.postedBlock + challengeWindowBlocks) revert ChallengeWindowExpired();

        bytes32 commitment = keccak256(
            abi.encode(data.round, data.blockIndex, uint8(1), msg.sender, data.salt)
        );
        ChallengeCommitment storage c = challengeCommitments[commitment];
        if (!c.active) revert CommitmentNotFound();
        if (c.challenger != msg.sender) revert UnauthorizedChallenger();
        if (block.number <= c.committedBlock) revert RevealSameBlockNotAllowed();
        c.active = false;

        if (data.uBlock.length != blockSize) revert InvalidBlockLength();
        if (data.gGens.length < blockSize) revert InvalidGeneratorsLength();

        DisputeVerifier.verifyGenerators(data.hGen, data.gGens, generatorsHash);

        uint64 mask = r.participantMask;
        uint256 numClients = _clientAddresses.length;
        uint256 expectedActive = 0;
        for (uint8 i = 0; i < numClients;) {
            if ((mask & (uint64(1) << uint64(i))) != 0) {
                expectedActive++;
            }
            unchecked {
                ++i;
            }
        }

        if (data.clientProofs.length != expectedActive) revert InvalidParticipantCount();

        uint32[] memory weights = new uint32[](expectedActive);
        uint256 actIdx = 0;
        for (uint8 i = 0; i < numClients;) {
            if ((mask & (uint64(1) << uint64(i))) != 0) {
                DisputeTypes.ClientCommitmentData calldata cp = data.clientProofs[actIdx];
                if (cp.clientIndex != i) revert InvalidParticipantIndex();
                if (cp.clientAddress != _clientAddresses[i]) revert InvalidParticipantAddress();
                weights[actIdx] = clientRegistry[_clientAddresses[i]].weight;
                actIdx++;
            }
            unchecked {
                ++i;
            }
        }

        bool upheld = DisputeVerifier.verifyD1Aggregation(
            data,
            r.aggRoot,
            r.clientLeavesRoot,
            weights
        );

        _resolveDispute(data.round, data.blockIndex, upheld);
    }

    /// @notice Reveals challenge data for D2 (update rule dispute).
    /// @param data Dispute calldata including current model, aggregate, and next model blocks.
    function challengeUpdateRule(DisputeTypes.D2DisputeData calldata data)
        external
        nonReentrant
        inPhase(Phase.Active)
    {
        RoundData storage r = rounds[data.round];
        if (r.status != RoundStatus.Posted) revert RoundNotPosted();
        if (block.number > r.postedBlock + challengeWindowBlocks) revert ChallengeWindowExpired();

        bytes32 commitment = keccak256(
            abi.encode(data.round, data.blockIndex, uint8(2), msg.sender, data.salt)
        );
        ChallengeCommitment storage c = challengeCommitments[commitment];
        if (!c.active) revert CommitmentNotFound();
        if (c.challenger != msg.sender) revert UnauthorizedChallenger();
        if (block.number <= c.committedBlock) revert RevealSameBlockNotAllowed();
        c.active = false;

        if (
            data.wCurrBlock.length != blockSize || data.wNextBlock.length != blockSize
                || data.uBlock.length != blockSize
        ) {
            revert InvalidBlockLength();
        }

        bytes32 prevModelRoot = rounds[data.round - 1].modelRootNext;

        bool upheld = DisputeVerifier.verifyD2UpdateRule(
            data,
            prevModelRoot,
            r.aggRoot,
            r.modelRootNext,
            r.claimedWeight
        );

        _resolveDispute(data.round, data.blockIndex, upheld);
    }

    /// @notice Reveals challenge data for D4b (client signature verification).
    /// @param data Dispute calldata including client index, address, block root, signature, and proof.
    function challengeClientLeaf(DisputeTypes.D4DisputeData calldata data)
        external
        nonReentrant
        inPhase(Phase.Active)
    {
        RoundData storage r = rounds[data.round];
        if (r.status != RoundStatus.Posted) revert RoundNotPosted();
        if (block.number > r.postedBlock + challengeWindowBlocks) revert ChallengeWindowExpired();

        bytes32 commitment = keccak256(
            abi.encode(data.round, uint32(data.clientIndex), uint8(4), msg.sender, data.salt)
        );
        ChallengeCommitment storage c = challengeCommitments[commitment];
        if (!c.active) revert CommitmentNotFound();
        if (c.challenger != msg.sender) revert UnauthorizedChallenger();
        if (block.number <= c.committedBlock) revert RevealSameBlockNotAllowed();
        c.active = false;

        // 1. Verify client leaf inclusion in clientLeavesRoot
        bytes memory clientLeaf = abi.encodePacked(
            data.clientIndex,
            data.clientAddress,
            data.clientBlockRoot,
            data.signature
        );
        if (!DomainMerkle.verifyProof(r.clientLeavesRoot, clientLeaf, data.clientLeafProof)) {
            revert ClientProofFailed();
        }

        // 2. Verify client is marked active in participantMask
        if ((r.participantMask & (uint64(1) << uint64(data.clientIndex))) == 0) {
            revert ParticipantNotActive();
        }

        // 3. Verify client registration and address match
        bool upheld = false;
        if (
            data.clientIndex >= _clientAddresses.length
                || _clientAddresses[data.clientIndex] != data.clientAddress
        ) {
            upheld = true;
        } else if (!clientRegistry[data.clientAddress].registered) {
            upheld = true;
        } else {
            // 4. Verify EIP-712 signature
            uint256 nonce = data.round - 1;
            bytes32 sessionId = bytes32(uint256(uint160(address(this))));
            bytes32 structHash = keccak256(
                abi.encode(
                    CLIENT_ROOT_TYPEHASH,
                    sessionId,
                    data.round,
                    data.clientAddress,
                    data.clientBlockRoot,
                    nonce
                )
            );
            bytes32 digest = _hashTypedDataV4(structHash);
            (address recovered, ECDSA.RecoverError err, bytes32 errorData) = ECDSA.tryRecover(digest, data.signature);
            if (err != ECDSA.RecoverError.NoError || recovered != data.clientAddress || errorData != bytes32(0)) {
                upheld = true;
            }
        }

        _resolveDispute(data.round, uint32(data.clientIndex), upheld);
    }

    /// @dev Internal dispute resolution executing slashing or deposit forfeiture.
    function _resolveDispute(uint256 round, uint32 blockIndex, bool upheld) private {
        RoundData storage r = rounds[round];
        if (upheld) {
            if (!bondDeposited) revert ServerAlreadySlashed();
            bondDeposited = false;
            r.status = RoundStatus.Invalid;

            uint256 challengerReward = (bondAmountWei * rewardShareBps) / 10000;
            uint256 treasuryReward = bondAmountWei - challengerReward;

            withdrawableBalances[msg.sender] += (challengerReward + challengerDepositWei);
            withdrawableBalances[treasury] += treasuryReward;

            emit ChallengeUpheld(round, blockIndex, msg.sender);
            emit ServerSlashed(round, msg.sender, challengerReward, treasuryReward);
        } else {
            withdrawableBalances[server] += challengerDepositWei;
            emit ChallengeRejected(round, blockIndex, msg.sender);
        }
    }

    /// @notice Finalizes a posted round after challengeWindowBlocks has elapsed without dispute.
    /// @param round Sequential round index to finalize.
    function finalizeRound(uint256 round) external inPhase(Phase.Active) {
        RoundData storage r = rounds[round];
        if (r.status != RoundStatus.Posted) revert RoundNotPosted();
        if (block.number < r.postedBlock + challengeWindowBlocks) revert ChallengeWindowActive();

        r.status = RoundStatus.Finalized;
        currentRound = round;
        currentModelRoot = r.modelRootNext;
        lastFinalizedBlock = block.number;

        emit RoundFinalized(round, r.modelRootNext);
    }

    /// @notice Pull-payment withdrawal for rewards, refunds, or forfeited deposits.
    function withdraw() external nonReentrant {
        uint256 amount = withdrawableBalances[msg.sender];
        if (amount == 0) revert NothingToWithdraw();

        withdrawableBalances[msg.sender] = 0;
        emit Withdrawn(msg.sender, amount);

        (bool success,) = msg.sender.call{value: amount}("");
        if (!success) revert TransferFailed();
    }

    /// @notice Withdraws the server bond after session completion and withdrawal delay.
    /// @dev Can only be called by the server when all posted rounds are finalized.
    function withdrawBond() external nonReentrant onlyServer inPhase(Phase.Active) {
        if (!bondDeposited) revert BondNotDeposited();
        if (currentRound == 0 || rounds[currentRound].status != RoundStatus.Finalized) {
            revert RoundNotPosted();
        }
        if (block.number < lastFinalizedBlock + withdrawalDelayBlocks) {
            revert WithdrawalDelayActive();
        }

        phase = Phase.Closed;
        bondDeposited = false;
        uint256 amount = bondAmountWei;

        emit BondWithdrawn(server, amount);

        (bool success,) = server.call{value: amount}("");
        if (!success) revert TransferFailed();
    }

    // --- Views ---

    /// @notice Returns total number of registered clients.
    function getClientCount() external view returns (uint256) {
        return _clientAddresses.length;
    }

    /// @notice Returns address and weight of a registered client by index.
    function getClient(uint8 index) external view returns (address, uint32) {
        if (index >= _clientAddresses.length) revert InvalidParameter();
        address client = _clientAddresses[index];
        return (client, clientRegistry[client].weight);
    }

    /// @notice Returns round data for a given round index.
    function getRound(uint256 round) external view returns (RoundData memory) {
        return rounds[round];
    }
}
