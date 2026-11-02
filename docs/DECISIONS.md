# Decisions and open questions

The agent updates this file as answers arrive. Stage 0 turns the OPEN items into `docs/QUESTIONS.md`. The agent asks me to confirm each default, and may add new questions. It must not proceed on an OPEN item without an answer.

## Decided
| ID | Decision |
|---|---|
| D-01 | Local test chain only; no public network, no real funds, no real keys |
| D-02 | Solidity 0.8.28 (pinned, cancun EVM target), OpenZeppelin Contracts v5 for access control, reentrancy guard, safe casts, EIP-712, ECDSA |
| D-03 | Commitments on alt_bn128 (BN254) G1, using the EVM precompiles |
| D-04 | Optimistic design: nothing is verified on-chain unless challenged |
| D-05 | Windows measured in block numbers, never timestamps (Challenge window = 20 blocks, withdrawal delay = 40 blocks) |
| D-06 | Python orchestrates and talks to the chain via web3.py (Python 3.11 environment on Windows) |
| D-07 | Core logic in packages; experiments and analysis in notebooks; plots only from CSV |
| D-08 | Ledger never edits history; only commitments and hashes are anchored; no personal data on-chain |
| D-09 | Pull payments; challenger commit-reveal bound to msg.sender; challenger deposit (1 ETH), bond (10 ETH), 50% reward split |
| D-10 | Out of scope here: D3 calibration dispute, unlearning algorithms, ZK circuits, secure aggregation |
| D-11 | Toolchain: Foundry (`forge`, `anvil` local node) |
| D-12 | Python Curve Library: Benchmark `py_ecc` on small $d$ in Stage 2; compare with native if scaling demands it |
| D-13 | Value ranges: $B = 2^{31} - 1$, $s = 16$, $m \le 32$, $K \le 64$ |
| D-14 | Rounding rule: Truncation toward zero (`truncate`) matching Solidity native `/`, with Python `math.trunc` reference |
| D-15 | Generators: Off-chain derivation script in `params/` with committed hash stored on-chain |
| D-16 | Architecture: Standalone per-session contract (`Session.sol`), immutable (no proxies/upgradeability) |
| D-17 | Governance: Single admin account with two-step transfer and timelock |
| D-18 | Exclusion epoch: Stretch goal deferred to Stage 9 |
| D-19 | Merkle Tree: `keccak256` hashing with custom domain separation (`0x00` leaf, `0x01` internal node) |
| D-20 | Curve points: Uncompressed affine `(uint256 x, uint256 y)` in calldata and structs (`G1Point`) |
| D-21 | Model for FL sim: Small MLP on MNIST ($d \approx 10^4$); extrapolate larger $d$ via validated cost model |
| D-22 | License: MIT License |

## Open
None. All Stage 0 clarification items have been resolved and confirmed.

## Log of answers
| Date | ID | User Answer | Reason |
|---|---|---|---|
| 2026-11-01 | Q-01 | Foundry (`forge`, `anvil`) | Native EVM fuzzing, invariant testing, gas tracking, and instant local node |
| 2026-11-01 | Q-02 | Solidity `0.8.28` | Latest stable 0.8.x release, checked arithmetic, cancun EVM |
| 2026-11-01 | Q-03 | Benchmark `py_ecc` first | Portability on Windows; benchmark on small $d$ before adding native bindings |
| 2026-11-01 | Q-04 | $B = 2^{31}-1, s = 16, m \le 32, K \le 64$ | Entry sums comfortably fit within `int128`/`int256`, preventing overflow |
| 2026-11-01 | Q-05 | Truncation toward zero | Matches Solidity native integer division; mirrored in Python |
| 2026-11-01 | Q-06 | Off-chain derivation in `params/` | Saves deployment gas; hash anchored on-chain verifies integrity |
| 2026-11-01 | Q-07 | Standalone per-session contract | Simpler audit surface, eliminates proxy complexities |
| 2026-11-01 | Q-08 | No upgradeability | Immutable code prevents retroactive rule changes |
| 2026-11-01 | Q-09 | Two-phase commit-reveal with deposit | Protects challengers from front-running and MEV theft |
| 2026-11-01 | Q-10 | 10 ETH bond, 1 ETH deposit, 50% reward | Non-zero values test pull payments and balance conservation |
| 2026-11-01 | Q-11 | Small MLP on MNIST ($d \approx 10^4$) | Authentic FL non-linear model with fast iteration time |
| 2026-11-01 | Q-12 | `keccak256` | Native EVM opcode, 30 gas baseline |
| 2026-11-01 | Q-13 | Single admin, 2-step transfer | Prototype-appropriate governance with safety against mistyped addresses |
| 2026-11-01 | Q-14 | Defer exclusion epoch to Stage 9 | Preserves focus on core dispute protocol |
| 2026-11-01 | Q-15 | MIT License | Standard permissive academic open-source license |
| 2026-11-01 | Q-16 | Python 3.11 on Windows | Full wheel support for crypto, web3, and ML libraries |
| 2026-11-01 | Q-17 | Custom domain-separated verifier | Adheres to binding PRD spec (`0x00`/`0x01` prefixes) preventing second-preimage attacks |
| 2026-11-01 | Q-18 | Uncompressed affine `(x, y)` | Direct pass-through to EVM precompiles 0x06 and 0x07 without on-chain decompression gas |
| 2026-11-01 | Q-19 | Signed `int256[]` in leaves | Enables direct signed division in D2 update rule checking |
| 2026-11-01 | Q-20 | Window = 20 blocks, Delay = 40 blocks | Safe from timestamp manipulation, swift in local Anvil tests |

## Security Risks & Edge Cases
- **Toolchain Integrity:** Installing Foundry on Windows requires PowerShell execution policy checks or official binary releases. Ensure verification of downloaded binaries.
- **Python Environment Isolation:** Ensure virtual environment (`.venv`) uses Python 3.11 specifically (`py -3.11 -m venv .venv`), avoiding Python 3.14 which lacks pre-built wheels.
- **Checked Arithmetic Consistency:** Any arithmetic discrepancy between Solidity 0.8.28 checked signed division and Python's `math.trunc` implementation could result in false slashing. Fuzz tests will test edge cases around zero, maximum/minimum bounds, and signs.
