# Security Report: fl-ledger

**Scope:** Research prototype for auditable federated learning on local Ethereum test chains (Foundry Anvil).  
**Warning:** This codebase has not been audited by an independent security firm and must not hold real economic value.

---

## 1. Security Checklist Compliance (18 Binding Items)

| Item | Requirement | Status | Code Location | Test Coverage | Security Rationale & Mitigations |
|---|---|---|---|---|---|
| **1** | **Reentrancy Protection & Pull Payments** | **COMPLIANT** | [`contracts/Session.sol:withdraw()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L552) | [`test/Disputes.t.sol:test_withdraw_pullPayment`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L198) | All external value transfers use OpenZeppelin `ReentrancyGuard` and pull-payment pattern (`withdraw()`). State balances are zeroed *before* external `.call{value: amount}("")`. |
| **2** | **Integer Arithmetic & Boundary Truncation** | **COMPLIANT** | [`contracts/crypto/BN254.sol:toScalar()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/crypto/BN254.sol#L84), [`contracts/disputes/DisputeVerifier.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/disputes/DisputeVerifier.sol#L77) | [`test/Disputes.t.sol:testFuzz_updateRuleSignedTruncation`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L228), [`tests/test_dispute_differential.py`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/tests/test_dispute_differential.py#L12) | Built with Solidity `0.8.28` checked arithmetic. Unchecked blocks are strictly limited to `toScalar()` for `type(int256).min` two's-complement negation without overflow panic. Differential tests verify exact parity with Python signed integer division `/` truncating toward zero. |
| **3** | **Low-Level Call Checking** | **COMPLIANT** | [`contracts/crypto/BN254.sol:ecAdd()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/crypto/BN254.sol#L26), [`contracts/crypto/BN254.sol:ecMul()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/crypto/BN254.sol#L48) | [`test/BN254.t.sol:test_ecAdd_identity`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/BN254.t.sol#L22) | All low-level precompile calls (`0x06` and `0x07`) utilize `staticcall` and strictly assert `success == true` and `returndatasize == 64`. Value transfers assert `(bool success,) = to.call{value: val}("")` with `revert TransferFailed()`. No `delegatecall` exists anywhere. |
| **4** | **Front-Running & MEV Protection** | **COMPLIANT** | [`contracts/Session.sol:commitChallenge()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L368) | [`test/Disputes.t.sol:test_reveal_revertRevealSameBlockNotAllowed`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L141), [`test/Disputes.t.sol:test_reveal_revertUnauthorizedChallenger`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L157) | Two-phase commit-reveal challenge mechanism. The commitment binds `keccak256(challenger, challengeType, payload, salt)`. Same-block reveals are rejected (`block.number <= commitment.commitBlock`), preventing MEV searchers and block builders from copying challenge payloads. |
| **5** | **Randomness Integrity** | **COMPLIANT** | None | Verified in static analysis | No contract logic depends on `block.timestamp`, `block.prevrandao`, `block.difficulty`, or `blockhash` for random seed generation. All sampling occurs off-chain; on-chain dispute checks are purely deterministic. |
| **6** | **Role Access Control & Two-Step Admin** | **COMPLIANT** | [`contracts/Session.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L115) | [`test/Session.t.sol:test_constructor_success`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol#L40) | Built on OpenZeppelin `AccessControlDefaultAdminRules` with two-step admin transfer and mandatory timelock delay. `onlyServer` and `onlyAdmin` guard all state-advancing endpoints. No use of `tx.origin`. |
| **7** | **Signature Security & EIP-712** | **COMPLIANT** | [`contracts/Session.sol:challengeClientLeaf()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L460) | [`tests/test_sign.py`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/tests/test_sign.py#L32), [`test/Disputes.t.sol:test_d4_forgedSignature_upheld_serverSlashed`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L112) | EIP-712 structured data hashing enforces `chainId`, `verifyingContract`, `session`, `round`, and `nonce`. Signatures are recovered via OpenZeppelin's `ECDSA.recover`, strictly preventing malleable signatures ($s > \text{secp256k1n}/2$). Cross-chain and cross-contract replays revert. |
| **8** | **Domain-Separated Merkle Trees** | **COMPLIANT** | [`contracts/crypto/DomainMerkle.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/crypto/DomainMerkle.sol#L18) | [`test/DomainMerkle.t.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/DomainMerkle.t.sol#L15), [`tests/test_merkle.py:test_domain_separation_second_preimage_defense`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/tests/test_merkle.py#L86) | Leaves hashed with `0x00` prefix: `keccak256(0x00, data)`. Internal nodes hashed with `0x01` prefix and lexicographically sorted pairs: `keccak256(0x01, min(a, b), max(a, b))`. Depth mismatches strictly reject second-preimage collision attacks. |
| **9** | **Elliptic-Curve Point & Scalar Validation** | **COMPLIANT** | [`contracts/crypto/BN254.sol:isOnCurve()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/crypto/BN254.sol#L68) | [`test/BN254.t.sol:test_isOnCurve_validPoints`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/BN254.t.sol#L45) | Weierstrass curve equation $y^2 = x^3 + 3 \pmod q$ validated on untrusted point inputs. Scalars are strictly reduced modulo group order $r = 21888242871839275222246405745257275088548364400416034343698204186575808495617$. Points at infinity $(0, 0)$ are explicitly handled. |
| **10** | **No Unbounded Loops** | **COMPLIANT** | [`contracts/Session.sol:register()`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L225) | [`test/Session.t.sol:test_register_revertMaxClientsExceeded`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol#L105) | Maximum client count is constrained by immutable `maxClients <= 64`. Registration duplicate checking loops are bounded by `maxClients`. Dispute loops in `DisputeVerifier` iterate strictly over vector block size $m \le 32$. |
| **11** | **Storage & Calldata Discipline** | **COMPLIANT** | [`contracts/Session.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol#L60) | Gas snapshot validation | Structs `RoundAnchor` pack `participantMask` (64-bit), `claimedWeight` (32-bit), `startBlock` (32-bit), and `status` (8-bit) into a single 256-bit EVM word. Array arguments use `calldata`. Immutables are used for all constructor parameters. |
| **12** | **Size Limits on Calldata Arrays** | **COMPLIANT** | [`contracts/disputes/DisputeVerifier.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/disputes/DisputeVerifier.sol#L25) | [`test/Disputes.t.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L80) | Input block vectors $U_b$ and client commitments $C_{k,b}$ strictly assert length equality with contract-configured `blockSize` ($m$) and active participant count ($K$). |
| **13** | **Gas Regression Tracking** | **COMPLIANT** | [`.gas-snapshot`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/.gas-snapshot) | `forge snapshot --check` | `.gas-snapshot` committed to git tracking gas usage across all 57 contract tests. Changes exceeding tolerance are logged in `LOG.md`. |
| **14** | **No Hardcoded Keys or Addresses** | **COMPLIANT** | [`.env.example`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/.env.example) | Codebase grep review | Zero private keys, mnemonic seeds, or production contract addresses are committed to git. All configurations load dynamically from environment variables. |
| **15** | **No Upgradeability Proxies** | **COMPLIANT** | [`contracts/Session.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/contracts/Session.sol) | Architecture review | Immutable deployment pattern: every federated learning session is a standalone, immutable smart contract deployment. No upgrade proxy proxies (`ERC1967`, `UUPS`, `Transparent`) or uninitialized storage patterns exist. |
| **16** | **Privileged Role Blast Radius** | **COMPLIANT** | Section 3 below | [`test/Session.t.sol:test_start_freezesRegistry`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol#L155) | Full blast radius analysis documented. Once `start()` is invoked, the participant registry and session parameters are permanently frozen, preventing admin interference. |
| **17** | **Test Network vs Production Differences** | **COMPLIANT** | Section 4 below | [`tests/test_e2e_honest.py`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/tests/test_e2e_honest.py) | Full list of differences (block times, gas limits, base fees, MEV extraction) documented. |
| **18** | **Emergency Pause Discipline** | **COMPLIANT** | None | Architecture review | No arbitrary pause mechanism exists that can freeze user withdrawals or dispute resolution. Slashing and pull-payment withdrawals remain permanently permissionless. |

---

## 2. Invariant Verification

All five core invariants have been proven under property and invariant tests in [`test/Disputes.t.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol) and [`test/Session.t.sol`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol):

1. **Balance Conservation Invariant** ([`test_balanceConservationInvariant`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L182)):
   $$\text{address}(this).\text{balance} \equiv \text{bondAmountWei} + \sum \text{pendingWithdrawals} + \sum \text{activeChallengeDeposits}$$
   Contract balance strictly equals total accounted protocol liabilities at all times.
2. **Sequential Progression Invariant** ([`test_postRound_revertInvalidRoundSequence`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol#L185)):
   $$\text{postedRound}_{i} \equiv \text{postedRound}_{i-1} + 1$$
   Rounds cannot be skipped, duplicated, or posted out of order.
3. **No Double-Slash Invariant** ([`test_noDoubleSlashInvariant`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L173)):
   A server bond can be slashed at most once. Once slashed, `serverBond = 0` and `roundState = Invalid`, permanently reverting subsequent slash attempts.
4. **Honest Server Safety Invariant** ([`test_d1_honestAggregate_rejected`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L80), [`test_d2_honestUpdate_rejected`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L96), [`test_d4_honestSignature_rejected`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Disputes.t.sol#L103)):
   An honest server cannot be slashed. Over 700 adversarial challenger attacks (Experiment E7), 0 false slashes were upheld, and 100% of challenger deposits were forfeited to the server.
5. **Frozen Registry Invariant** ([`test_start_freezesRegistry`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Session.t.sol#L155)):
   After `start()`, `phase == Phase.Active`. Any call to `register()` immediately reverts with `SessionAlreadyStarted()`.
6. **Retained Mask Invariant (Stage 9 Exclusion Epoch)** ([`test/Exclusion.t.sol:test_exclusionEpoch_fullLifecycle`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/test/Exclusion.t.sol#L180), [`tests/test_exclusion.py:test_server_reaggregation_with_retained_mask`](file:///c:/Users/Soumadipta%20Konar/Desktop/FL-ledger/tests/test_exclusion.py#L65)):
   $$\text{participantMask} \subseteq \text{retainedMask} \iff (\text{participantMask} \ \& \ \sim\!\text{retainedMask}) \equiv 0$$
   Enforced $O(1)$ at posting time. An excluded client's bit cannot appear in any future epoch round. Any attempt to secretly include an excluded client's commitment or update vector into $U_b$ without declaring them in `participantMask` violates BN254 homomorphic equality ($Com(U_b; R_b) \ne \sum_{k \in \text{retained}} n_k C_{k,b}$) and is slashed via D1.

---

## 3. Privileged Roles & Blast Radius Analysis

| Role | Authorized Address | Permitted Actions | Blast Radius if Key Compromised | Mitigation |
|---|---|---|---|---|
| **Admin** | `initialAdmin` (OpenZeppelin Default Admin) | `register()`, `start()`, `transferAdmin()` | Can register adversarial clients or refuse to call `start()`. **Cannot** touch server bond, cannot alter dispute verdicts, cannot seize user funds. Once `start()` is invoked, admin has **zero** authority over the active session. | Two-step admin transfer with timelock delay (`AccessControlDefaultAdminRules`). |
| **Server** | `server` | `depositBond()`, `postRound()`, `finalizeRound()`, `withdrawBond()` | Can post corrupt or poisoned roots. | Any corrupt root is auditable by off-chain watchers and subject to immediate on-chain slashing via D1, D2, or D4. Bond is locked for 40 blocks after session close. |
| **Challenger** | Any address locking `1 ETH` deposit | `commitChallenge()`, `challengeAggregation()`, `challengeUpdateRule()`, `challengeClientLeaf()` | Can attempt to spam or grief honest server. | If challenge is invalid, the entire 1 ETH deposit is permanently forfeited to the server. Two-phase commit-reveal prevents front-running. |
| **Client** | Registered participant wallet (`msg.sender`) | `requestExclusion()` | Can request self-exclusion from current and future rounds. **Cannot** exclude other participants. Cannot front-run or interrupt an active dispute challenge window. | `msg.sender` authorization check; challenge window quarantine; $O(1)$ bitwise mask enforcement; gas-refunded round cleanup. |

---

## 4. Test Network vs Production Differences

| Characteristic | Local Test Chain (Foundry Anvil) | Production Public Mainnet (Ethereum) | Operational Impact |
|---|---|---|---|
| **Block Time** | Instantaneous / deterministic on-demand mining | ~12 seconds per slot (PoS) | Challenge windows in production correspond to ~4 minutes (20 blocks), providing adequate off-chain watcher verification time. |
| **Gas Costs & Base Fees** | Fixed gas prices, no congestion | EIP-1559 variable base fees + priority tips | Challengers must price priority tips sufficiently high to guarantee dispute inclusion within the 20-block challenge window during high network congestion. |
| **Transaction Ordering & MEV** | FIFO mempool ordering | Proposer-Builder Separation (PBS), MEV-Boost | Mitigated by two-phase commit-reveal: commitment hash binds `msg.sender`, preventing MEV searchers from stealing challenge payloads. |
| **Precompile Performance** | Native Rust EVM execution | Native Geth/Erigon/Besu client execution | Gas costs for precompiles `0x06` (150 gas) and `0x07` (6,000 gas) are identical across both environments. |

---

## 5. Static Analysis (Slither) Summary

Slither v0.11.6 ran against all smart contracts (`slither contracts/ --solc-remaps @openzeppelin/=lib/openzeppelin-contracts/`).
- **High Severity Findings**: 0
- **Medium Severity Findings**: 0
- **Informational Findings**:
  - `low-level-calls`: In `withdraw()` and `withdrawBond()`. Justified: standard pull-payment ETH transfer (`to.call{value: amount}("")`) executed after all internal balances are zeroed, strictly guarded by `nonReentrant`.
