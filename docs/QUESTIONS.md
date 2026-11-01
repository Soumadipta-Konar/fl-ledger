# Clarification Questions (Stage 0)

This document turns the open decisions from `Instructions/05_DECISIONS.md` and new architectural ambiguities discovered during the documentation review into concrete questions. Each question is numbered, grouped, provides viable options, gives a recommended default with rationale, and states why the decision matters.

---

## Group 1: Toolchain, OS & Environment

### Q-01: Smart Contract Development Toolchain
- **Question:** Which Ethereum development framework should be used for compiling, testing, and generating gas snapshots for contracts?
- **Options:**
  1. **Foundry (`forge`, `anvil`)** (Recommended)
  2. **Hardhat** (Node.js/TypeScript)
- **Recommended Default:** **Foundry**.
- **Reason & Impact:** Foundry provides native EVM property-based fuzz testing, stateful invariant testing, differential testing against Python outputs, built-in gas snapshots, and the local `anvil` node with instant JSON-RPC controls (`anvil_mine`, `evm_setAutomine`). Hardhat requires JS glue code and external fuzzing plugins. Python scripts can talk directly to `anvil` via `web3.py`.

### Q-02: Solidity Compiler Version
- **Question:** Which exact Solidity compiler version should be pinned?
- **Options:**
  1. **`0.8.28`** (Recommended - latest stable release of Solidity 0.8.x with transient storage and Prague EVM support, or `cancun` target)
  2. **`0.8.26`** (Broadly supported stable release)
  3. **`0.8.24`** (Well-established with Cancun opcode support)
- **Recommended Default:** **`0.8.28`** (targeting the `cancun` EVM).
- **Reason & Impact:** Pinned stable version prevents compiler discrepancies. Checked arithmetic is built-in; no floating pragmas will be permitted in deployed contracts.

### Q-03: Python Elliptic-Curve Library
- **Question:** Which Python library should be used for alt_bn128 (BN254) G1 group scalar multiplications and additions?
- **Options:**
  1. **Benchmark `py_ecc` vs native bindings (e.g. `py_ecc` for pure-Python fallback, native C/Rust binding for large $d$)** (Recommended)
  2. **`py_ecc` exclusively** (Pure Python, slow for $d > 10^3$, but zero C-compiler build dependencies on Windows)
  3. **Native library exclusively** (e.g., via CFFI/Rust bindings)
- **Recommended Default:** **Benchmark `py_ecc` first in Stage 2 on small $d$ (~$10^2 - 10^3$)**. If MSM (multi-scalar multiplication) for client rounds exceeds acceptable time (>2s per client round), benchmark native bindings before Stage 4.
- **Reason & Impact:** Python MSM throughput directly determines simulation execution time for FL experiments. Pure Python `py_ecc` is portable on Windows without MSVC C-compilers, while native bindings are required for scaling.

### Q-16: Python Version & Operating System Environment
- **Question:** Which Python version and virtual environment configuration should be targeted on the Windows host?
- **Options:**
  1. **Python 3.11 (`C:\Users\Soumadipta Konar\AppData\Local\Programs\Python\Python311\python.exe`)** (Recommended)
  2. **Python 3.14 (`C:\Users\Soumadipta Konar\AppData\Local\Python\pythoncore-3.14-64\python.exe`)**
- **Recommended Default:** **Python 3.11**.
- **Reason & Impact:** System inspection reveals both Python 3.14 and Python 3.11 are installed. Python 3.14 lacks precompiled binary wheels for key cryptography, web3, and machine learning packages (`web3.py`, `py_ecc`, `torch`/`scikit-learn`, `bitarray`), whereas Python 3.11 has full ecosystem compatibility on Windows.

---

## Group 2: Cryptography, Group Arithmetic & Encodings

### Q-06: Generator Points ($G_i, H$) Derivation and Storage
- **Question:** How should the public generators $G_1, \dots, G_m$ and blinding generator $H$ on BN254 G1 be generated and made accessible to the smart contract?
- **Options:**
  1. **Off-chain derivation via verifiable hash-to-curve script with points stored in contract storage/constants or passed at deployment, and derivation hash committed** (Recommended)
  2. **On-chain runtime derivation via EVM hash-to-curve**
- **Recommended Default:** **Off-chain derivation script in `params/`**, calculating uncompressed affine points $(x, y)$, publishing their SHA-256/keccak256 hash, and deploying a dedicated immutable parameter contract or passing the generator root/points at initialization.
- **Reason & Impact:** On-chain hash-to-curve for $m$ generators consumes substantial deployment gas. An off-chain transparent derivation script with committed point hashes eliminates trust assumptions and minimizes gas.

### Q-12: Hash Function for Merkle Trees
- **Question:** Which cryptographic hash function should be used for the off-chain and on-chain Merkle tree roots and inclusion proofs?
- **Options:**
  1. **`keccak256`** (Recommended)
  2. **`sha256`**
- **Recommended Default:** **`keccak256`**.
- **Reason & Impact:** `keccak256` is a native EVM opcode costing 30 gas + 6 gas/word, whereas `sha256` requires the 0x02 precompile costing 60 gas + 12 gas/word. Keccak256 cuts dispute gas in half for Merkle verification.

### Q-17: Merkle Tree Domain Separation vs Standard OpenZeppelin Library
- **Question:** How should domain separation (leaf prefix `0x00`, internal node prefix `0x01`) be reconciled with OpenZeppelin's `MerkleProof.sol` library?
- **Options:**
  1. **Custom minimal Merkle verifier contract (`MerkleTree.sol`, <60 lines) enforcing `0x00` leaf and `0x01` internal node prefixes with sorted sibling pairs, mirrored in Python `merkle.py`** (Recommended)
  2. **Standard OpenZeppelin `MerkleProof.sol` (which does not prepend `0x01` to internal pairs), relying strictly on fixed leaf depth / leaf count to thwart second-preimage attacks**
- **Recommended Default:** **Option 1: Custom minimal domain-separated verifier**.
- **Reason & Impact:** Standard OpenZeppelin `MerkleProof` hashes `keccak256(abi.encodePacked(a, b))` directly. Adhering to the binding specification in `03_ARCHITECTURE.md` Section 4 requires the `0x01` prefix for internal nodes. A compact, tested internal library ensures 100% specification compliance and cryptographic safety against second-preimage vulnerabilities.

### Q-18: Calldata Format for BN254 Curve Points
- **Question:** How should elliptic curve points on BN254 G1 be structured in calldata and contract storage?
- **Options:**
  1. **Uncompressed affine coordinates `(uint256 x, uint256 y)` represented as `struct G1Point { uint256 x; uint256 y; }`** (Recommended)
  2. **Compressed 32-byte format requiring on-chain point decompression**
- **Recommended Default:** **Uncompressed affine coordinates (`G1Point`)**.
- **Reason & Impact:** EVM precompiles 0x06 (`ecAdd`) and 0x07 (`ecMul`) require uncompressed 64-byte input `(x, y)`. Point decompression in Solidity requires modular square roots (Tonelli-Shanks), costing ~50,000+ gas per point. Uncompressed coordinates avoid unnecessary gas and complex on-chain field math.

---

## Group 3: Number Ranges, Fixed-Point & Rounding

### Q-04: Fixed-Point Quantisation Parameters and Integer Ranges
- **Question:** What should the concrete bounds and bit-widths be for model parameter updates ($q$), client weights ($n_k$), block size ($m$), and scale bits ($s$)?
- **Options:**
  1. **$B = 2^{31} - 1$, entry bit-width `int64`, client weights $n_k \in [1, 2^{32}-1]$, scale $s = 16$, block size $m \in [8, 32]$, maximum clients $K = 64$** (Recommended)
  2. **$B = 2^{15} - 1$, entry bit-width `int32`, scale $s = 8$, $m = 16$, $K = 32$**
  3. **Arbitrary precision field representations**
- **Recommended Default:** **Option 1 ($B = 2^{31}-1$, $s = 16$, $m \le 32$, $K \le 64$)**.
- **Reason & Impact:** With $K \le 64$ and $n_k < 2^{32}$, total aggregate weight $n_t < 2^{38}$. Max aggregate entry $U_b \le 64 \cdot 2^{32} \cdot 2^{31} \approx 2^{69}$, well within safe `int128` / `int256` bounds, preventing any possibility of integer overflow before scalar reduction.

### Q-05: Rounding Rule for Model Update Division `div(U, n)`
- **Question:** Which explicit integer division rounding rule should be adopted for the federated averaging update step $W_{t+1, b} = W_{t, b} + \text{div}(U_b, n_t)$?
- **Options:**
  1. **Truncation toward zero (`truncate`)** (Solidity native integer division `/`) (Recommended)
  2. **Floor division (`floor`)** (Python native `//` division)
  3. **Nearest-integer with half-away-from-zero rounding**
- **Recommended Default:** **Truncation toward zero (`truncate`)**.
- **Reason & Impact:** Solidity's native signed division `/` truncates toward zero (e.g., `-5 / 2 == -2`). Adopting truncation toward zero allows the contract to use clean checked native EVM operations without expensive custom division branches, while Python's `fixed.py` will implement matching `math.trunc(u / n)` with comprehensive test suites for negative numbers.

### Q-19: Merkle Leaf Encoding for Updates and Blindings
- **Question:** How should aggregate block leaves (`U_b, R_b`) and client commitments be encoded prior to hashing?
- **Options:**
  1. **`keccak256(abi.encodePacked(bytes1(0x00), uint32(blockIndex), abi.encode(int256[] u_b, uint256 r_b)))`** (Recommended)
  2. **Encode entries as scalar field elements `(order - |x|) mod order` inside the leaf**
- **Recommended Default:** **Option 1: Signed `int256[]` with raw blinding `uint256 r_b`**.
- **Reason & Impact:** Dispute D2 checks the model update rule $W_{t+1} = W_t + U / n$ using integer division. Storing signed integer entries directly in the leaf allows D2 to verify update arithmetic directly without reversing modular scalar field representations.

---

## Group 4: Smart Contract Architecture & Governance

### Q-07: Contract Deployment Architecture: Per-Session vs Factory
- **Question:** Should each FL session be deployed as an independent standalone contract or instantiated through a factory contract?
- **Options:**
  1. **Standalone per-session contract deployment (`Session.sol`)** (Recommended)
  2. **Factory contract creating minimal proxy clones (ERC-1167)**
- **Recommended Default:** **Standalone per-session deployment**.
- **Reason & Impact:** Minimal clones and factories introduce proxy redirection and initialization edge cases. Standalone contracts are significantly simpler to audit, verify, and reason about, strictly matching the PRD prototype scope.

### Q-08: Upgradeability Pattern
- **Question:** Should contracts support upgradeability (e.g. ERC-1967 transparent or UUPS proxies)?
- **Options:**
  1. **No upgradeability (immutable contracts)** (Recommended)
  2. **UUPS or Transparent Upgradeable Proxy**
- **Recommended Default:** **No upgradeability**.
- **Reason & Impact:** `04_SECURITY.md` explicitly forbids upgradeability by default. Immutable code guarantees that neither the server nor admin can alter dispute logic, slashing rules, or frozen registry state after deployment.

### Q-13: Consortium Admin and Governance Model
- **Question:** What access control model should govern the administrative setup before session start?
- **Options:**
  1. **Single admin account using OpenZeppelin `AccessControlDefaultAdminRules` (two-step transfer with enforced timelock delay)** (Recommended)
  2. **Multi-signature governance contract (Gnosis Safe style)**
- **Recommended Default:** **Option 1: Single account with two-step transfer and timelock**.
- **Reason & Impact:** For local test chain research prototypes, a single account with two-step transfer is straightforward and fully testable, while eliminating single-step key compromise risks. Admin capabilities freeze completely upon calling `start()`.

### Q-14: Exclusion Epoch (Verifiable Unlearning) Scope
- **Question:** How should the stretch goal for client exclusion epochs be phased?
- **Options:**
  1. **Defer until Stages 1 through 8 are fully verified and benchmarked** (Recommended)
  2. **Include exclusion data structures in contract v1 from Stage 3**
- **Recommended Default:** **Defer to Stage 9 as an isolated extension**.
- **Reason & Impact:** Preserves core focus on verifying base aggregation and dispute resolution (D1, D2, D4) first, eliminating scope creep.

### Q-20: Dispute Timing Windows and Bond Withdrawal Delay
- **Question:** What should the default challenge window and post-finalization bond withdrawal delay be (expressed in block counts)?
- **Options:**
  1. **Challenge window $W = 20$ blocks; Bond withdrawal delay $D = 40$ blocks ($2 \times W$)** (Recommended)
  2. **Challenge window $W = 100$ blocks; Bond withdrawal delay $D = 200$ blocks**
- **Recommended Default:** **$W = 20$ blocks, $D = 40$ blocks (passed as constructor arguments)**.
- **Reason & Impact:** Using block numbers prevents timestamp manipulation attacks. Setting 20 blocks allows local Foundry Anvil tests to execute swiftly via `vm.roll()` without slow block mining loops, while ensuring sufficient duration for commit-reveal challenge sequences.

---

## Group 5: Economic Parameters & Griefing Protection

### Q-09: Challenge Submission Mechanism
- **Question:** How should challengers submit disputes to prevent front-running and MEV transaction copying?
- **Options:**
  1. **Two-phase Commit-Reveal bound to `msg.sender` with challenger deposit** (Recommended)
  2. **Single-phase open challenge with deposit**
- **Recommended Default:** **Commit-Reveal bound to `msg.sender` with challenger deposit**.
- **Reason & Impact:** A single-phase dispute allows the malicious server or front-running bots to observe the proof in the mempool, steal the challenger's reward, or censor the transaction. Commit-reveal `hash(data, msg.sender, salt)` guarantees that only the original prover can reveal the dispute.

### Q-10: Economic Parameters (Bonds, Rewards, Deposits)
- **Question:** What symbolic economic values should be configured in constructor arguments for local test chain experiments?
- **Options:**
  1. **Server Bond: 10 ETH; Challenger Deposit: 1 ETH; Challenger Reward: 50% of slashed bond (5 ETH); Treasury: 50% (5 ETH)** (Recommended)
  2. **Zero-value symbolic deposits (mock accounting)**
- **Recommended Default:** **Option 1: 10 ETH bond, 1 ETH deposit, 50% reward split**.
- **Reason & Impact:** Realistic non-zero ETH amounts validate reentrancy protections, balance conservation invariants, and pull-payment withdrawal patterns on the local node.

---

## Group 6: Machine Learning Model & Experiment Scope

### Q-11: Machine Learning Model and Dataset for Simulation
- **Question:** What benchmark machine learning architecture and dataset should be used for the end-to-end Python simulation (`sim/`)?
- **Options:**
  1. **Small Multi-Layer Perceptron (MLP, ~10,000 parameters) on MNIST / Fashion-MNIST** (Recommended)
  2. **Multinomial Logistic Regression on MNIST (~7,840 parameters)**
  3. **Convolutional Neural Network (CNN, >100,000 parameters)**
- **Recommended Default:** **Small MLP on MNIST ($d \approx 10^4$)**.
- **Reason & Impact:** Enables real non-linear federated training off-chain, completes training in under 10 seconds per round, and provides an authentic parameter vector for quantisation and block commitment benchmarking. Larger model scaling ($d \ge 10^5, 10^6$) will be evaluated through validated cost model extrapolation per RQ3/RQ4.

### Q-15: Open Source Licence
- **Question:** Which open-source software licence should be placed in `LICENSE` and contract SPDX identifiers?
- **Options:**
  1. **MIT License** (Recommended)
  2. **Apache-2.0**
  3. **PolyForm Noncommercial 1.0.0**
- **Recommended Default:** **MIT License** (SPDX: `MIT`).
- **Reason & Impact:** Standard, widely recognized open-source academic license compatible with OpenZeppelin Contracts.

---

## Security Risks & Edge Cases (Stage 0 Design Analysis)

### 1. Elliptic-Curve Scalar vs Field Modulus Confusion
- **Risk:** BN254 has two distinct 254-bit primes: the base field prime $q = 21888242871839275222246405745257275088696311157297823662689037894645226208583$ and the scalar group order $r = 21888242871839275222246405745257275088548364400416034343698204186575808495617$.
- **Failure Mode:** Reducing scalar exponents mod $q$ instead of mod $r$ breaks homomorphic binding and allows an adversary to construct forgeable commitment relations.
- **Defense Plan:** Enforce strict type safety and dedicated modular reduction helper libraries (`scalar_mod = scalar % r`). Point coordinates are verified against $q$, while scalars are strictly reduced modulo $r$.

### 2. Negative Number Representation and Modular Wrap-Around
- **Risk:** Negative model updates $q < 0$ encoded into the scalar field as $r - |q|$ could wrap around if added naively or checked without range enforcement.
- **Failure Mode:** If entry bound checks are performed after scalar encoding, an adversary can submit updates equivalent to negative integers that bypass magnitude bounds.
- **Defense Plan:** Strict bound checks $|q| \le B$ executed in Python and on-chain in signed two's complement integer space *prior* to scalar mapping.

### 3. Asymmetric Signed Integer Division Rounding
- **Risk:** Discrepancy between Python's floor division (`//`) and Solidity's truncation toward zero (`/`) for negative quotients.
- **Failure Mode:** When $U_b < 0$ and $U_b \pmod n \ne 0$, Python `floor` produces $\lfloor U_b / n \rfloor$ while EVM produces $\lceil U_b / n \rceil$. An honest server computing with Python floor division would be falsely accused and slashed by an on-chain dispute checker.
- **Defense Plan:** Standardize strictly on truncation toward zero in `fixed.py` (`math.trunc(u / n)`). Comprehensive differential fuzz testing across thousands of negative and positive integer pairs.

### 4. Front-Running Challenger Reveals
- **Risk:** Challenger submits an on-chain dispute proof; the server or an MEV searcher front-runs with higher priority gas to steal the reward or censor the proof.
- **Defense Plan:** Enforce a 2-step commit-reveal protocol. Commit phase stores `keccak256(abi.encodePacked(challengeData, msg.sender, salt))` at block $N$. Reveal phase only accepts transactions from `msg.sender` at block $\ge N + 1$.

### 5. Denial-of-Service via Memory and Calldata Expansion in Disputes
- **Risk:** Malicious challenger or server supplies excessively large arrays of commitments or proofs in dispute calldata, causing out-of-gas reverts or unbounded iteration.
- **Defense Plan:** Enforce strict constant upper bounds: $K \le 64$, $m \le 32$. Loop counters are bounded by immutable constants, using `calldata` slices rather than copying to memory.
