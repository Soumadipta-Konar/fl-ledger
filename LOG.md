# Session Log (fl-ledger)

One dated entry per session, newest first: what was done, what surprised me, what is not understood.

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
