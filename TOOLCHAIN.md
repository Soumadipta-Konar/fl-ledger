# Toolchain Specifications

This document pins all language versions, toolchains, and primary libraries required to build, test, and analyze `fl-ledger`.

## Core Languages & Runtimes
| Tool | Pinned Version | Purpose |
|---|---|---|
| **Solidity** | `0.8.28` (EVM target: `cancun`) | Smart contracts and EVM execution logic |
| **Python** | `3.11.x` (`>= 3.11.0, < 3.12.0`) | Orchestration, fixed-point reference, simulation, verification |
| **Foundry** | Latest stable (`forge`, `cast`, `anvil`) | Contract compilation, testing, fuzzing, local chain node |
| **Node.js** | `>= 20.0.0` (Host installed: `v24.14.1`) | Utility scripting, tool support |

## Contract Dependencies (Foundry / Git Submodules)
| Package | Version | Source | Purpose |
|---|---|---|---|
| `forge-std` | `v1.9.5` | `foundry-rs/forge-std` | Foundry standard testing library and assertion framework |
| `openzeppelin-contracts` | `v5.1.0` | `OpenZeppelin/openzeppelin-contracts` | AccessControl, ECDSA, EIP-712, SafeCast, ReentrancyGuard |

## Python Dependencies (`requirements.txt`)
| Package | Pinned Version Range | Purpose |
|---|---|---|
| `web3` | `>= 6.15.0, < 7.0.0` | JSON-RPC interaction with local Anvil test node |
| `eth-account` | `>= 0.11.0, < 1.0.0` | EIP-712 structured signing and key management |
| `eth-abi` | `>= 5.0.0, < 6.0.0` | ABI encoding matching EVM conventions |
| `py_ecc` | `>= 7.0.0, < 8.0.0` | Reference BN254 (alt_bn128) curve arithmetic and pairings |
| `numpy` | `>= 1.26.0, < 2.0.0` | Array and vector manipulation for FL weights |
| `pandas` | `>= 2.2.0, < 3.0.0` | Structured CSV result tables adhering to experiments schema |
| `matplotlib` | `>= 3.8.0, < 4.0.0` | Publication plots adhering to Okabe-Ito styling |
| `scikit-learn` | `>= 1.4.0, < 2.0.0` | Baseline ML dataset helpers and metrics |
| `python-dotenv` | `>= 1.0.0, < 2.0.0` | Environment configuration loading |
| `pytest` | `>= 8.0.0, < 9.0.0` | Python unit and differential test suite |

## Static Analysis & Security
| Tool | Target Version | Purpose |
|---|---|---|
| **Slither** | `>= 0.10.0` | Static analysis for Solidity security vulnerabilities |

## Security Risks & Edge Cases
- **Compiler Drift:** Ensure `foundry.toml` explicitly sets `solc_version = "0.8.28"` rather than allowing auto-detection of system `solc`.
- **EVM Target Mismatch:** Using the `cancun` EVM target enables ephemeral data opcodes if needed, but local Anvil must also run in Cancun mode (default in current Foundry versions).
- **Python Binary Extension Compatibility:** Python 3.11 is strictly pinned on Windows to ensure precompiled wheels for `py_ecc`, `web3`, and crypto libraries install cleanly without requiring local C++ build toolchains.
