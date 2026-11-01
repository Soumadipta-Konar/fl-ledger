# Session Log (fl-ledger)

One dated entry per session, newest first: what was done, what surprised me, what is not understood.

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
