# Product Notes: fl-ledger

## 1. Executive Summary & Problem Context

Federated learning (FL) enables distributed parties to collaboratively train machine learning models without centralizing raw training data. However, traditional federated learning architectures rely on an untrusted central coordinator to aggregate client updates. In untrusted or multi-institutional settings, this central coordinator introduces critical failure modes:
1. **Silent Cheating / Model Poisoning**: A malicious server can serve stale models, bias aggregate weights toward specific classes, or insert targeted backdoors without detection.
2. **Fabrication of Participants**: A server can inject Sybil or fabricated client updates with forged signatures.
3. **Lack of Economic Recourse**: Victims have no cryptographic evidence to prove malfeasance or hold the coordinator accountable.

`fl-ledger` addresses this by combining **homomorphic Pedersen commitments on the BN254 elliptic curve**, **domain-separated Merkle trees**, and **optimistic smart contract anchoring** on Ethereum. It turns federated aggregation into an auditable protocol backed by an on-chain security bond.

---

## 2. Target Users & Use Cases

`fl-ledger` is engineered for environments where participants possess valuable proprietary data, operate under strict regulatory compliance, and lack mutual trust:

### A. Healthcare & Genomic Research Consortiums
- **Problem**: Multiple hospital networks wish to train diagnostic models on patient electronic health records (EHR) without sharing raw patient data under HIPAA/GDPR.
- **Why `fl-ledger`**: Independent medical researchers or regulatory auditors run watcher nodes. If the coordinator manipulates model weights to favor specific pharmaceutical outcomes, the server is cryptographically proven fraudulent and slashed.

### B. Banking & Anti-Money Laundering (AML) Networks
- **Problem**: Competing financial institutions train shared anomaly detection models to detect cross-institutional fraud syndicates.
- **Why `fl-ledger`**: Banks cannot expose proprietary transaction graphs. `fl-ledger` guarantees that every participant's update is genuinely incorporated according to registered institutional weights, while keeping individual client data localized.

### C. Decentralized AI Protocols & Open Compute Markets
- **Problem**: Decentralized networks paying compute coordinators to aggregate community contributions.
- **Why `fl-ledger`**: Provides an automated, trustless dispute resolution pipeline where anyone can audit the server and claim a 50% slashing reward if malfeasance is proven.

---

## 3. Comparative Architecture Analysis

| Dimension | Centralized Server (FedAvg) | Naive On-Chain Aggregation | Secure Multi-Party Compute (SMPC) | Zero-Knowledge FL (zk-SNARKs) | `fl-ledger` (This Architecture) |
|---|---|---|---|---|---|
| **Trust Model** | Fully trusted coordinator | Trustless (Ethereum consensus) | Threshold honest majority | Trustless (Cryptographic proofs) | Optimistic with cryptographic watchers |
| **Model Size Scalability** | Unbounded ($d > 10^9$) | Severely constrained ($d < 4{,}100$) | Moderate ($d \le 10^6$) | Prover-constrained ($d \le 10^5$) | High ($d \ge 10^7$) |
| **On-Chain Gas Cost** | 0 (Off-chain) | $O(d \cdot K)$ (Astronomical) | 0 (Off-chain) | High proof verification (~300k-500k gas) | **$O(1)$ flat (~185k gas/round)** |
| **Client Compute Overhead** | Low (Local SGD only) | Low | High (Multi-party protocols) | Very High (Circuit proof generation) | **Low (~218 ms/block for commitments)** |
| **Network Bandwidth** | $O(K \cdot d)$ | $O(K \cdot d)$ calldata | $O(K^2 \cdot d)$ | $O(K \cdot d)$ | **$O(K \cdot d)$** |
| **Client Dropout Resilience** | High | High | Very Low (Requires resharing) | High | **High (Bitmask representation)** |
| **Public Slashing & Recourse** | None | Automatic | None | Automatic | **Automatic on-chain slashing** |

---

## 4. When to Choose `fl-ledger`

`fl-ledger` is the optimal architectural choice when:
1. **The Model Dimension Exceeds On-Chain Compute Limits**: The model has more than a few dozen parameters ($d > 50$). Our crossover analysis (Experiment E4) proves that `fl-ledger` becomes strictly cheaper than on-chain aggregation at $d^* \approx 11$ parameters. At $d = 1210$, `fl-ledger` is 97.9% cheaper; at $d = 10{,}000$, naive on-chain aggregation exceeds Ethereum's block limit entirely.
2. **Mutual Trust is Lacking**: Participants refuse to trust the server's good faith and require an immutable dispute mechanism.
3. **Client Computation Must Remain Lightweight**: Unlike zk-SNARKs, which require gigabytes of memory and minutes of prover time per client update, Pedersen commitments require only standard elliptic curve scalar multiplications (~218 ms per block in Python, ~1.1 ms in native C/Rust).
4. **Economic Slashing Provides Sufficient Deterrence**: Sashing a 10 ETH bond is economically sufficient to deter coordinator malfeasance relative to the value of an undetected cheating attempt.

---

## 5. When NOT to Choose `fl-ledger`

Do NOT choose `fl-ledger` under the following conditions:
1. **Sub-Second / High-Frequency Training**: If the application requires sub-second round turnaround, Ethereum's block confirmation time (12s on mainnet) makes on-chain anchoring unsuitable.
2. **Zero Watcher Availability**: If no independent participant or auditor is willing to run an off-chain watcher node, server cheating will go unflagged during the challenge window, allowing corrupt rounds to finalize.
3. **Full Model Privacy Against Watchers**: Watchers inspect plaintext vector blocks and blinding factors to verify arithmetic update rules (D2). If the aggregated weights themselves must remain confidential from all non-training parties, an encryption or ZK layer is necessary.
4. **Data Availability Guarantee Without External Layers**: If the server withholds the block data entirely from watchers, the smart contract cannot detect this without an external Data Availability (DA) layer or committee.

---

## 6. Engineering Trade-offs & Limitations

1. **Fixed-Point Arithmetic Truncation**:
   - Neural network weights are natively represented as IEEE-754 32-bit floats. EVM execution requires integer representation.
   - We utilize fixed-point scaling ($s = 16$). Experiment E6 proves that for $s \ge 12$, test accuracy matches float32 baselines to $<0.01\%$. However, models requiring dynamic exponent ranges exceeding $[-32768, 32767]$ require adaptive pre-scaling.
2. **Two-Phase Dispute Latency**:
   - To defeat front-running searchers and MEV bots, challenges require a two-phase commit-reveal mechanism (`commitChallenge` $\to$ wait 1 block $\to$ reveal). This introduces a mandatory 1-block delay before dispute resolution.
3. **Pure Python vs Native Curve MSM Performance**:
   - Pure Python `py_ecc` achieves 2.9 ms per scalar multiplication, requiring ~14 seconds per client round at $d = 1024$. For large models ($d \ge 10^4$), deploying native C/Rust bindings (such as `arkworks` or `mcl`) is mandatory to achieve sub-second client performance (~0.07s).
