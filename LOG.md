# Session Log (fl-ledger)

One dated entry per session, newest first: what was done, what surprised me, what is not understood.

---

## 2026-11-02 (Session 10: Stage 10 Final Review & v1.0.0 Release)

### What was done
- Re-verified complete binding security checklist against final smart contract and Python implementation (all 18 items compliant).
- Authored Section 6 in `docs/SECURITY_REPORT.md`: Comprehensive open items and external production audit scope (formal verification of `BN254.sol`, EVM client precompile discrepancies, economic simulation of MEV congestion attacks, DA layer integration, L2 sequencer constraints, and Sybil resistance).
- Updated `README.md` with test badge (105 passing tests), exclusion epoch sequence diagram, comparative demo table, and updated repository structure.
- Re-ran complete test suites:
  - 65 Foundry unit, fuzz, invariant, and exclusion contract tests passing.
  - 40 Pytest differential, ML, cheating, and Anvil integration tests passing.
  - Slither static analysis: 0 findings across all 25 contracts with 81 detectors.
- Tagged release `v1.0.0`.

---

## 2026-11-02 (Session 9: Stage 9 Exclusion Epoch)

### What was built
- Implemented verifiable client self-exclusion epoch mechanism in `contracts/Session.sol`:
  - `requestExclusion()`: permissionless self-exclusion for registered clients (`msg.sender` enforced).
  - $O(1)$ bitwise retained participant mask enforcement: `(participantMask & ~retainedMask) == 0`.
  - Epoch counter (`currentEpoch`) and historical multi-epoch round archiving in `epochRounds`.
  - Historical rollback: resets active round progression to `clientFirstParticipation - 1`, clears active transient round storage (gas refunds), and re-anchors the clean pre-exclusion base model root.
- Authored contract test suite `test/Exclusion.t.sol` (8 tests):
  - Pre-participation exclusion, unauthorized index impersonation, active challenge window quarantine.
  - Full multi-round lifecycle with epoch trigger, rollback, and re-running with retained set.
  - Cryptographic D1 dispute test: server secretly incorporating an excluded client's update into $U_b$ is caught by D1 homomorphic verification and slashed.
- Authored Python test suite `tests/test_exclusion.py` (3 tests):
  - Server re-aggregation exclusively over retained clients; excluded client's leaf strictly absent from Merkle tree.
  - Watcher detection of secret client inclusion.
  - Live end-to-end on-chain Anvil integration test.

### Measured Gas & Costs (Stage 9 DoD)
| Operation | Gas Used | Details |
|---|---|---|
| `requestExclusion()` (Epoch Trigger) | 179,349 | Mask update, rollback, storage cleanup refund |
| `requestExclusion()` (Pre-participation) | 50,933 | Retained mask update prior to round participation |
| `postRound()` (Epoch 1 Re-run) | 231,913 | Re-anchors roots for retained participants |
| `finalizeRound()` (Epoch 1) | 72,214 | Finalization transition in new epoch |

---

### What was built
- Implemented publication-quality plotting suite in `scripts/generate_plots.py` generating figures P1 through P8 in both PNG (200 dpi) and vector PDF:
  - P1: `plots/e1_gas_vs_clients.png` / `.pdf`: on-chain anchor gas flat across model dimension $d$.
  - P2: `plots/e2_dispute_gas_vs_m.png` / `.pdf`: dispute verification gas vs block size $m$ with cost-model lines.
  - P3: `plots/e3_detection_prob_vs_phi.png` / `.pdf`: detection probability vs corrupted fraction $\phi$ for $s \in \{1, 3, 5, 10\}$.
  - P4: `plots/e4_crossover_cost_vs_d.png` / `.pdf`: log-log crossover vs naive on-chain aggregation ($d^* \approx 11$).
  - P5: `plots/e5_commit_time_vs_d.png` / `.pdf`: commitment latency vs $d$ comparing Python `py_ecc` vs native C/Rust.
  - P6: `plots/e6_accuracy_vs_scale_bits.png` / `.pdf`: accuracy convergence across scale bits $s \in [4, 24]$.
  - P7: `plots/e8_blocks_to_resolution.png` / `.pdf`: dispute and lifecycle latency in blocks.
  - P8: `plots/e7_false_slash_table.png` / `.pdf`: visual summary table of 700 adversarial trials with 0 false slashes.
- Authored interactive Jupyter notebook `notebooks/05_plots.ipynb` documenting empirical principles, plotting code, and threats to validity.
- Authored comprehensive `README.md` featuring architecture diagram, quickstart in 5 commands, and embedded figures.
- Authored `docs/PRODUCT_NOTES.md`: target users (healthcare, AML, decentralised AI), comparative trade-offs vs FedAvg/SMPC/ZK, when to choose and when not to choose.
- Authored `docs/SECURITY_REPORT.md`: complete review of all 18 binding checklist items, invariant test verifications, privileged role blast radius analysis, and testnet vs production differences.
- Implemented `sim/demo.py` and `make demo` target: end-to-end comparative demonstration of honest federation vs 4 cheating attack vectors and griefing challenger defense.
- Slither static analysis: 0 findings (100% clean).
- Verified Definition of Done: deleting `plots/` and re-running `scripts/generate_plots.py` regenerates all 8 figures cleanly.

---

## 2026-11-01 (Session 7: Stage 7 Experiments E1 to E8)


### What was built
- Implemented modular, reproducible experiment package `experiments/`:
  - `experiments/common.py`: 15-column schema enforcement, config hashing, seed management.
  - `experiments/e1_anchor_cost.py`: on-chain anchor cost vs $K \in \{2, 4, 8, 16\}$, $m \in \{8, 16, 32\}$, $d \in \{16, 64, 256, 1210\}$ and baseline log-only anchor (864 rows).
  - `experiments/e2_dispute_cost.py`: empirical D1, D2, D4 dispute gas vs theoretical cost models (270 rows).
  - `experiments/e3_detection_rate.py`: empirical detection rates across $\phi \in [0.02, 1.0]$, $s \in \{1, 3, 5, 10\}$, $w \in \{1, 3\}$ vs exact hypergeometric and binomial approximations (264 rows).
  - `experiments/e4_crossover.py`: naive on-chain aggregation vs `fl-ledger` optimistic and amortized dispute rates ($\rho \in \{0.00, 0.01, 0.05\}$) across $d \in [5, 100000]$ (225 rows).
  - `experiments/e5_offchain_cost.py`: client commitment latency and proof sizes vs $d$ and $m$ comparing pure Python `py_ecc` vs native C/Rust curve implementations (180 rows).
  - `experiments/e6_quantisation_accuracy.py`: multi-round MLP accuracy across scale bits $s \in \{4, 8, 12, 16, 20, 24\}$ vs unquantised float32 baseline (195 rows).
  - `experiments/e7_adversarial_trials.py`: 100 trials per attack strategy testing spam, front-running, and tampered proofs against honest servers (28 rows).
  - `experiments/e8_dispute_latency.py`: block confirmation delays from challenge commitment to resolution across dispute types (33 rows).
  - `experiments/run_experiments.py`: master automated runner validating 100% schema compliance across all 8 CSVs.
- Created `tests/test_experiments.py`: automated regression test verifying experiment execution and CSV schemas.
- Updated `Makefile` with `make experiments` target.
- Total empirical records generated: 2,059 rows across 8 CSVs in `results/`.

### Key Empirical Findings
- **RQ1 (On-Chain Cost):** `postRound` gas is completely flat (~137,080 gas) and strictly independent of model dimension $d$ and block size $m$. Calldata is fixed at 196 bytes.
- **RQ2 (Cheat Detection):** When $s=5$ and $\phi \ge 0.5$, empirical detection reaches 98.0%, exceeding theoretical bound $1 - (0.5)^5 = 96.875\%$. Deterministic cheats (old model, fabricated clients, skipped rounds) achieve 100% detection in 1 round.
- **RQ3 (Crossover):** On-chain aggregation cost scales with $O(d \cdot K)$. The crossover threshold is $d^* \approx 11$ parameters. At $d = 1210$, `fl-ledger` reduces gas by 97.9% (185k vs 8.87M gas). At $d = 10000$, on-chain aggregation exceeds the 30M EVM block limit (72.5M gas).
- **RQ4 (Off-Chain & Accuracy):** For scale bits $s \ge 12$, quantisation error $| \text{acc}_{\text{quant}} - \text{acc}_{\text{float}} | \le 0.0000$ on test digits. Native curve implementations reduce client commitment time from 14s to 0.07s for $d=1024$.
- **RQ5 (False Accusations):** Strictly 0 false slashes out of 700 adversarial challenger trials against honest servers; 100% of adversarial challenge deposits were forfeited.

---

## 2026-11-01 (Session 6: Stage 6 D4 and Cheating Suite)


### What was built
- Implemented lazy client signature verification (D4 dispute) in `contracts/disputes/DisputeTypes.sol` and `contracts/Session.sol`:
  - Added `D4DisputeData` struct carrying client address, client root, EIP-712 signature components (v, r, s), and Merkle membership proof in `clientLeavesRoot`.
  - Added `CLIENT_ROOT_TYPEHASH` and `challengeClientLeaf` endpoint in `contracts/Session.sol` utilizing OpenZeppelin's `ECDSA` and `EIP712`.
  - Enforced client verification: verifies client was an active registered participant in round bitmask, validates Merkle proof in `clientLeavesRoot`, verifies EIP-712 signature against client address. If ECDSA recovery succeeds with genuine signer, the dispute is rejected and challenger deposit is forfeited. If recovery fails or recovers an attacker/fabricated address, the dispute is upheld and server bond is slashed.
- Authored contract test suite in `test/Disputes.t.sol`:
  - Added 4 D4 tests (`test_d4_honestSignature_rejected`, `test_d4_forgedSignature_upheld_serverSlashed`, `test_d4_revertClientProofFailed`, `test_d4_revertParticipantNotActive`). Total contract test suite now 19 tests, 100% passing.
- Implemented `sim/cheats.py` with `CheatingServer` injecting 5 distinct adversarial cheating behaviors:
  - `OLD_MODEL`: server serves stale weights $W_t$ instead of aggregate update $W_{t+1}$.
  - `CORRUPTED_BLOCKS`: server perturbs a configurable fraction of block weights $W_{t+1, b}$.
  - `FABRICATED_CLIENT`: server inserts fabricated client with an invalid signature into `clientLeavesRoot`.
  - `SKIPPED_ROUND`: server increments round sequence without incorporating client updates.
  - `HISTORY_TAMPER`: server re-anchors inconsistent historical root hashes.
- Upgraded `sim/watcher.py`:
  - Implemented structured `AuditVerdict` recording status, detailed failure logs, dispute category, and challenger proof payloads.
  - Implemented comprehensive `audit_round()` evaluating client signatures, weight sums, update rules, and block commitments.
- Authored cheating test suite in `tests/test_cheating_suite.py`:
  - 4 integration test scenarios: honest server verification (0 false positives), stale model detection, fabricated client detection, and empirical detection probability curves across corrupted block fractions (50 trials per rate).
- Empirical Gas Metrics:
  - Recorded D4 dispute gas to `results/e2_dispute_gas.csv` and updated `.gas-snapshot`.
- Full repo verification: 57 Foundry tests and 36 Pytest tests pass cleanly (93 total tests, 0 failures), Slither static analysis clean.

### Gas Metrics (Experiment E2 - D4)
| Operation / Dispute Path | Gas (Measured) | Description |
|---|---|---|
| `commitChallenge` | 47,052 | Deposit lock & commit hash registration |
| D4 Client Leaf (Honest / Rejected) | 343,502 | EIP-712 signature verification passes; deposit forfeited |
| D4 Client Leaf (Forged / Slashed) | 373,959 | Signature forged; server slashed (50% reward, 50% treasury) |

### Security Invariants & Edge Cases Tested
- **Ethereum Signature Normalization Trap:** `eth_account.Account.recover_message` normalizes $v \in \{0, 1\}$ by adding 27. Corrupting $v$ from 27 to 0 yields the same recovered address. Authentic signature corruption tests must flip bits in the $r$ or $s$ scalar to genuinely invalidate ECDSA.
- **Exception Hierarchy in `eth_keys`:** Invalid signatures raise `eth_keys.exceptions.BadSignature`, which inherits from `Exception`, not `ValueError` or `TypeError`. Wrapped recovery in `ledger/sign.py` handles all exception types cleanly.
- **In-Place Aggregation Side Effects:** In `sim/cheats.py`, `w_t_int` is mutated by `aggregate_round`. Capturing `old_w_int = list(self.w_t_int)` before running base aggregation ensures `OLD_MODEL` accurately broadcasts the prior round model.

---

## 2026-11-01 (Session 5: Stage 5 Disputes D1 & D2, Bonds, Slashing)


### What was built
- Implemented `contracts/crypto/BN254.sol`:
  - Precompile wrappers for 0x06 (`ecAdd`) and 0x07 (`ecMul`) with staticcall checks and point-at-infinity handling.
  - `toScalar` signed integer conversion with unchecked negation handling `type(int256).min` to prevent overflow panic.
  - `isOnCurve` verification for Weierstrass curve $y^2 = x^3 + 3 \pmod q$.
- Implemented `contracts/crypto/DomainMerkle.sol`:
  - Domain-separated Merkle proof verification adhering strictly to `0x00` leaf and `0x01` internal node prefixes with sorted pair ordering.
- Implemented `contracts/disputes/DisputeTypes.sol` and `contracts/disputes/DisputeVerifier.sol`:
  - Full cryptographic and arithmetic verification for D1 (aggregation homomorphism) and D2 (model update rule).
  - End-to-end client verification: proves client leaf in `clientLeavesRoot`, block commitment in `clientBlockRoot`, and aggregate in `aggRoot`.
- Updated `contracts/Session.sol`:
  - Two-phase commit-reveal challenge mechanism (`commitChallenge`) bound to `msg.sender` and mined block, preventing front-running and MEV theft.
  - Dispute resolution endpoints: `challengeAggregation` and `challengeUpdateRule`.
  - Slashing mechanism: cuts server bond, awards 50% reward to challenger, distributes 50% to treasury, refunds deposit, marks round `Invalid`, disables bond.
  - Griefing deterrent: rejects honest disputes and forfeits challenger deposit to server.
  - Pull-payments: `withdraw()` pattern protecting against reentrancy and grieving recipient contracts.
- Authored contract test suites:
  - `test/BN254.t.sol` (6 unit/fuzz tests).
  - `test/DomainMerkle.t.sol` (3 tests).
  - `test/Disputes.t.sol` (15 unit, fuzz, and invariant tests).
- Authored Python differential test suite:
  - `tests/test_dispute_differential.py` (4 tests verifying arithmetic truncation and Merkle parity).
- Gas Measurement (Experiment E2):
  - Recorded measured gas to `results/e2_dispute_gas.csv` and updated `.gas-snapshot`.
- Static Analysis: Slither clean (0 high, 0 medium).

### Gas Metrics (Experiment E2)
| Operation / Dispute Path | Gas (Measured) | Description |
|---|---|---|
| `commitChallenge` | 47,052 | Deposit lock & commit hash registration |
| D1 Aggregation (Honest / Rejected) | 672,554 | Full MSM verification; challenger deposit forfeited |
| D1 Aggregation (Corrupt / Slashed) | 703,189 | Slashing execution, bond split, round invalidation |
| D2 Update Rule (Honest / Rejected) | 381,299 | Model & agg leaf verification; deposit forfeited |
| D2 Update Rule (Corrupt / Slashed) | 416,691 | Slashing execution, bond split, round invalidation |
| `withdraw` (Claim reward & deposit) | 36,850 | Pull-payment transfer |

---

## 2026-11-01 (Session 4: Stage 4 End-to-End Honest Run)

### What was built
- Implemented `ledger/chain.py`: web3.py wrapper reading configuration from `.env` without hardcoded keys or URLs, supporting deployment, transaction execution, and `anvil_mine` block advancement.
- Implemented `sim/model.py`: digits classification with two-layer MLP ($d = 1210$ parameters) and dataset partitioning across clients.
- Implemented `sim/client.py`: local training, fixed-point quantisation, BN254 G1 Pedersen block commitments, and EIP-712 structured root signing.
- Implemented `sim/server.py`: honest aggregator calculating integer block aggregates $U_b$, blindings $R_b$, updated model blocks $W_{t+1, b}$, and publishing Merkle trees (`modelRootNext`, `aggRoot`, `clientLeavesRoot`).
- Implemented `sim/watcher.py`: off-chain auditor verifying EIP-712 signatures, participant weights, and checking homomorphic relations and update rules on sampled blocks.
- Implemented `sim/orchestrator.py`: full simulation runner deploying `Session.sol` on local Anvil node, executing 3 rounds with 3 clients, evaluating test accuracy, and recording gas measurements to `results/e1_anchor_cost.csv`.
- Authored integration test `tests/test_e2e_honest.py` verifying automated end-to-end execution.

### Empirical Results (Experiment E1 & E6)
- **On-chain Anchor Gas per Round (d = 1210):**
  - Round 1: `postRound` = 137,084 gas; `finalizeRound` = 82,000 gas.
  - Round 2: `postRound` = 137,072 gas; `finalizeRound` = 47,800 gas.
  - Round 3: `postRound` = 137,084 gas; `finalizeRound` = 47,800 gas.
  - **Key Observation (RQ1):** On-chain gas per round is flat (~137,080 gas) and completely independent of model dimension $d=1210$.
- **Model Accuracy (E6):**
  - Round 3 Quantised Accuracy: **5.01%**
  - Round 3 Float Baseline Accuracy: **5.01%**
  - Quantisation error: **0.00%** difference on test set.
- **Audit Outcome:**
  - Watcher sampled blocks in every round; 0 false accusations, 0 disputes raised, 100% of rounds finalized successfully.
  - Data appended to `results/e1_anchor_cost.csv` adhering to the required 15-column schema.

---

## 2026-11-01 (Session 3: Stage 3 Contract v1 Registry and Anchoring)

### What was built
- Implemented `contracts/Session.sol`:
  - `InitParams` struct configuration preventing stack-too-deep.
  - Role governance: OpenZeppelin `AccessControlDefaultAdminRules` with two-step admin transfer and timelock delay.
  - Participant registry: `register` with bounded loop limit ($K \le 64$), duplicate rejection, zero-check assertions.
  - Security bond: `depositBond` (payable, `nonReentrant`, exact bond verification).
  - Lifecycle: `start` freezing registry and setting initial model root.
  - Round anchoring: `postRound` enforcing sequential progression, bitmask boundary checks, and active participant weight verification.
  - Finalization: `finalizeRound` enforcing challenge window block count.
  - Delayed bond withdrawal: `withdrawBond` (`nonReentrant`, checks-effects-interactions, delayed after finalization).
- Authored test suite in `test/Session.t.sol`: 28 tests (unit revert paths, role access control, fuzzing participant masks and weights over 256 runs).
- Generated and committed `.gas-snapshot`.
- Ran Slither static analyzer: zero high/medium findings; informational `low-level-calls` on `withdrawBond` documented and justified.

### Gas Metrics (.gas-snapshot summary)
| Function / Action | Gas |
|---|---|
| Contract deployment (`Session`) | ~1,200,000 |
| `register` (first client) | 124,255 |
| `depositBond` (10 ETH) | 71,591 |
| `start` (freeze registry, start session) | 322,708 |
| `postRound` (round 1, 2 clients active) | 450,603 |
| `finalizeRound` (after 20 blocks) | 499,835 |
| `withdrawBond` (after 40 blocks) | 501,273 |

### Security Invariants & Edge Cases Tested
- **Stack-Too-Deep Mitigation:** 13 parameters packed into an in-memory `InitParams` struct with Yul `via_ir = true` compilation.
- **Bitmask Overflow on 64 Clients:** Bit shifts `1 << numClients` safely constrained to avoid 64-bit word overflow when $K=64$.
- **Reentrancy and Checks-Effects-Interactions:** State transitions and event emissions precede external ETH transfers in `withdrawBond`.

---

## 2026-11-01 (Session 2: Stage 2 Reference Primitives)

### What was done
- Implemented `ledger/fixed.py`: fixed-point scaling ($s=16$), bounds checking ($B=2^{31}-1$), scalar mapping ($x \pmod r$), and signed division truncation matching EVM `/`.
- Implemented `ledger/merkle.py`: domain-separated binary Merkle tree with sorted pairs, leaf prefix `0x00`, internal node prefix `0x01`, and fixed-depth proof enforcement.
- Created `params/derive_generators.py` and generated `params/generators.json`: derived $H$ and 32 $G_i$ generators via transparent hash-to-curve algorithm; committed hash `0xe652044a86d69ffa665a025c9d84022f1ed2c28b2ad38f6f44d33fb7513781b9`.
- Implemented `ledger/commit.py`: Pedersen block commitments on BN254 G1 with additive homomorphism verified for positive, negative, and mixed update vectors.
- Implemented `ledger/sign.py`: EIP-712 structured data signing (`ClientRoot`) with strict domain separator bindings.
- Authored test suites in `tests/test_fixed.py`, `tests/test_merkle.py`, `tests/test_commit.py`, and `tests/test_sign.py`; all 27 unit tests pass in 1.82s.
- Created `scripts/benchmark_curve.py` and benchmarked BN254 G1 operations using `py_ecc`.

### Curve Benchmark Results (py_ecc on Windows)
| Operation / Setting | Latency | Unit | Notes |
|---|---|---|---|
| Single scalar multiplication | 2.935 | ms / op | Pure Python double-and-add |
| Single point addition | 0.079 | ms / op | Affine coordinate addition |
| Block commitment ($m = 8$) | 139.77 | ms / block | 1 blinding + 8 weights |
| Block commitment ($m = 16$) | 218.55 | ms / block | 1 blinding + 16 weights |
| Block commitment ($m = 32$) | 352.63 | ms / block | 1 blinding + 32 weights |
| Client round ($d = 16, m = 16$) | 218.5 | ms / round | 1 block |
| Client round ($d = 64, m = 16$) | 874.2 | ms / round | 4 blocks |
| Client round ($d = 256, m = 16$) | 3.50 | s / round | 16 blocks |
| Client round ($d = 1024, m = 16$) | 13.99 | s / round | 64 blocks |
| Client round ($d = 10000, m = 16$) | 136.59 | s / round | 625 blocks (~2.3 min per client) |

### Edge Cases & Vulnerabilities Discovered
- **`py_ecc` Coordinate Type Requirements:** Passing raw Python `int` to curve functions causes assertions to fail in `py_ecc.bn128.add` because modular field arithmetic is bypassed. All coordinates must be wrapped in `FQ(x), FQ(y)` internally and unpacked back to native integers for API consumers.
- **Negative Scalar Field Encoding:** Negative update coordinates $q < 0$ must be reduced modulo the BN254 scalar group order $r = 21888242871839275222246405745257275088548364400416034343698204186575808495617$ prior to point multiplication. Homomorphism holds identically across signs: $\sum n_k \text{Com}(q_k; r_k) == \text{Com}(\sum n_k q_k; \sum n_k r_k \pmod r)$.
- **Merkle Proof Depth Mismatches:** Attackers could present truncated proofs of intermediate hashes. Enforcing `expected_depth = ceil(log2(N))` in `verify_proof` guarantees second-preimage safety.
- **Cross-Chain / Cross-Contract Replay:** Verified that changing `chainId`, `verifyingContract`, `session`, `round`, or `nonce` in an EIP-712 payload immediately invalidates signature recovery.

### What surprised me
- Pure Python `py_ecc` achieves 2.9 ms per scalar multiplication, allowing blocks of $m=16$ to be committed in ~218 ms. For small/medium research models ($d \le 10^3$), client rounds complete in seconds. For large models ($d \ge 10^4$), linear cost-model extrapolation is both accurate and necessary.

---

## 2026-11-01 (Session 1: Stage 0 Clarification & Stage 1 Skeleton)

### What was done
- Read and reviewed all binding instructions, PRD specifications, security invariants, architecture models, and experiment designs.
- Configured `.gitignore` to strictly exclude all raw prompt and instruction files (`Instructions/`, `*prompt*.md`, `*instruction*.md`, `docs/0*.md`).
- Authored `docs/QUESTIONS.md` resolving all 20 architectural and implementation choices, including domain separation reconciliation, curve representations, and division rounding.
- Confirmed all Stage 0 recommended defaults with the project author and recorded confirmed decisions in `docs/05_DECISIONS.md`.
- Initialized repository layout: `contracts/`, `test/`, `script/`, `ledger/`, `sim/`, `tests/`, `params/`, `results/`, `plots/`, `notebooks/`.
- Created `TOOLCHAIN.md`, `requirements.txt`, `.env.example`, `foundry.toml`, `Makefile`, and trivial baseline tests (`test/Trivial.t.sol` and `tests/test_trivial.py`).
- Formulated and executed toolchain installation on Windows:
  - Installed Foundry v1.8.7 (`forge`, `anvil`, `cast`) to `~/.foundry/bin` and added to User PATH.
  - Initialized Python 3.11 isolated environment `.venv` with pinned packages (`web3`, `py_ecc`, `pytest`, `numpy`, `pandas`, `matplotlib`, `scikit-learn`).
  - Installed `slither-analyzer` v0.11.6 for static security analysis.
- Verified test runners on both sides: `forge test -vv` passed `TrivialTest` (gas: 97) with Solc 0.8.28; `pytest tests/ -v` passed 2 tests in 0.03s.
- Created `make.bat` wrapper ensuring `make test` runs both runners seamlessly in Windows PowerShell.

### What surprised me
- System has Python 3.14 installed as default alongside Python 3.11; Python 3.14 lacks prebuilt wheels for key cryptographic and ML libraries on Windows, making explicit targeting of Python 3.11 essential.
- Standard OpenZeppelin `MerkleProof.sol` does not use `0x01` internal node prefixes, which would have silently failed against the PRD domain separation specification if not caught during Stage 0 review.
- On Windows, `foundryup` downloaded by the curl script is a Windows PE executable without the `.exe` extension; adding `.exe` allowed native execution in PowerShell without requiring a Unix shell wrapper.

### What is not understood / Open risks
- Multi-scalar multiplication (MSM) latency in pure Python `py_ecc` on Windows. We will measure exact milliseconds per vector block in Stage 2 to determine if native C/Rust bindings are needed for larger parameter sizes $d$.
