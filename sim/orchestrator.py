"""End-to-end honest federated learning orchestration with on-chain anchoring on Anvil."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any
import numpy as np

from eth_account import Account
from ledger.chain import (
    get_web3,
    deploy_session,
    send_contract_tx,
    advance_blocks,
    DEFAULT_RPC_URL,
    DEFAULT_CHAIN_ID,
)
from ledger.commit import load_generators
from ledger.fixed import (
    quantise,
    DEFAULT_SCALE_BITS,
    DEFAULT_BOUND_B,
)
from ledger.merkle import MerkleTree
from sim.client import Client
from sim.model import SmallMLP, load_partitioned_data
from sim.server import HonestServer
from sim.watcher import Watcher

RESULTS_DIR = Path(__file__).parent.parent / "results"


def ensure_anvil_running() -> subprocess.Popen[Any] | None:
    """Ensure Anvil test node is running on default RPC URL."""
    w3 = get_web3()
    try:
        if w3.is_connected():
            return None
    except Exception:
        pass

    # Launch local anvil process
    proc = subprocess.Popen(
        ["anvil", "--port", "8545", "--chain-id", str(DEFAULT_CHAIN_ID), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for node readiness
    for _ in range(30):
        time.sleep(0.2)
        try:
            if w3.is_connected():
                return proc
        except Exception:
            pass

    raise RuntimeError("Failed to start or connect to Anvil node on 127.0.0.1:8545")


def run_honest_e2e(
    num_rounds: int = 3,
    num_clients: int = 3,
    block_size: int = 16,
    scale_bits: int = DEFAULT_SCALE_BITS,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute end-to-end honest FL rounds anchored on Session contract."""
    anvil_proc = ensure_anvil_running()
    try:
        w3 = get_web3()
        RESULTS_DIR.mkdir(exist_ok=True)

        # 1. Accounts setup (derive deterministic local test accounts from Anvil)
        admin_acct = Account.create(f"admin-{seed}")
        server_acct = Account.create(f"server-{seed}")
        treasury_acct = Account.create(f"treasury-{seed}")

        # Fund accounts from Anvil's rich default account (Account 0)
        funder = Account.from_key("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
        funder_nonce = w3.eth.get_transaction_count(funder.address)
        for target in [admin_acct.address, server_acct.address]:
            tx = {
                "from": funder.address,
                "to": target,
                "value": w3.to_wei(20, "ether"),
                "nonce": funder_nonce,
                "gas": 21000,
                "gasPrice": w3.eth.gas_price,
                "chainId": DEFAULT_CHAIN_ID,
            }
            funder_nonce += 1
            signed = funder.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)

        # 2. Deploy Session contract
        _, _, gen_hash = load_generators()
        session_params = {
            "initialAdmin": admin_acct.address,
            "adminDelay": 0,
            "server": server_acct.address,
            "treasury": treasury_acct.address,
            "maxClients": 16,
            "blockSize": block_size,
            "scaleBits": scale_bits,
            "challengeWindowBlocks": 20,
            "withdrawalDelayBlocks": 40,
            "bondAmountWei": w3.to_wei(10, "ether"),
            "challengerDepositWei": w3.to_wei(1, "ether"),
            "rewardShareBps": 5000,
            "generatorsHash": gen_hash,
        }
        contract_addr, deploy_receipt = deploy_session(w3, admin_acct.key.hex(), session_params)

        # 3. Setup dataset, clients, and models
        client_data, (x_test, y_test) = load_partitioned_data(num_clients=num_clients, seed=seed)
        clients: list[Client] = []
        for i in range(num_clients):
            c_acct = Account.create(f"client-{i}-{seed}")
            # Register client on contract
            send_contract_tx(
                w3, contract_addr, admin_acct.key.hex(),
                "register", c_acct.address, (i + 1) * 10
            )
            clients.append(Client(
                client_id=i,
                address=c_acct.address,
                private_key=c_acct.key.hex(),
                weight=(i + 1) * 10,
                data=client_data[i],
            ))

        # Deposit bond & start session
        send_contract_tx(
            w3, contract_addr, server_acct.key.hex(),
            "depositBond", value=w3.to_wei(10, "ether")
        )

        initial_model = SmallMLP(seed=seed)
        init_flat = initial_model.get_flat_weights()
        d_params = len(init_flat)

        # Quantised initial model blocks for root
        init_q = [quantise(float(v), scale_bits=scale_bits) for v in init_flat]
        init_leaves = []
        for b_idx in range(0, len(init_q), block_size):
            chunk = init_q[b_idx : b_idx + block_size]
            if len(chunk) < block_size:
                chunk = chunk + [0] * (block_size - len(chunk))
            leaf_bytes = b_idx.to_bytes(4, "big") + b"".join(
                val.to_bytes(32, "big", signed=True) for val in chunk
            )
            init_leaves.append(leaf_bytes)
        init_model_tree = MerkleTree(init_leaves)

        send_contract_tx(
            w3, contract_addr, admin_acct.key.hex(),
            "start", init_model_tree.root
        )

        # 4. Simulation loops
        server = HonestServer(init_flat, block_size=block_size, scale_bits=scale_bits)
        session_id = bytes.fromhex(contract_addr[2:].lower()).rjust(32, b"\x00")
        watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)

        # Floating-point baseline model for accuracy comparison
        float_model = SmallMLP(seed=seed)
        float_weights = init_flat.copy()

        metrics_records: list[dict[str, Any]] = []
        run_id = f"honest-run-{int(time.time())}"
        config_hash = hashlib.sha256(f"{num_clients}-{block_size}-{d_params}-{scale_bits}".encode()).hexdigest()[:10]

        for r in range(1, num_rounds + 1):
            # Client updates
            client_pkgs = []
            for client in clients:
                pkg = client.compute_update(
                    global_flat_weights=server.current_weights,
                    block_size=block_size,
                    session_id=session_id,
                    round_num=r,
                    chain_id=DEFAULT_CHAIN_ID,
                    contract_address=contract_addr,
                    nonce=r - 1,
                    scale_bits=scale_bits,
                    seed=seed,
                )
                client_pkgs.append(pkg)

            # Floating point baseline step
            float_deltas = []
            for i, client in enumerate(clients):
                m_local = SmallMLP(seed=seed + i)
                m_local.set_flat_weights(float_weights.copy())
                m_local.train_step(client.x_train, client.y_train, lr=0.05)
                float_deltas.append(m_local.get_flat_weights() - float_weights)
            total_w = sum(c.weight for c in clients)
            float_agg_delta = sum(c.weight * d for c, d in zip(clients, float_deltas)) / total_w
            float_weights += float_agg_delta
            float_model.set_flat_weights(float_weights)

            # Server aggregation
            mask = (1 << num_clients) - 1
            curr_w_blocks = []
            for b_idx in range(0, len(server.w_t_int), block_size):
                chunk = server.w_t_int[b_idx : b_idx + block_size]
                if len(chunk) < block_size:
                    chunk = chunk + [0] * (block_size - len(chunk))
                curr_w_blocks.append(chunk)

            post_pkg = server.aggregate_round(r, client_pkgs, mask)

            # On-chain postRound
            post_receipt = send_contract_tx(
                w3, contract_addr, server_acct.key.hex(),
                "postRound",
                r,
                post_pkg.model_root_next,
                post_pkg.agg_root,
                post_pkg.client_leaves_root,
                post_pkg.participant_mask,
                post_pkg.claimed_weight,
            )
            gas_post = post_receipt.gasUsed

            # Watcher audit
            audit_passed = watcher.verify_round(post_pkg, curr_w_blocks)
            if not audit_passed:
                raise RuntimeError(f"Watcher falsely flagged honest round {r}!")

            # Advance blocks past challenge window
            advance_blocks(w3, 21)

            # Finalize round
            fin_receipt = send_contract_tx(
                w3, contract_addr, admin_acct.key.hex(),
                "finalizeRound", r
            )
            gas_finalize = fin_receipt.gasUsed

            # Evaluate accuracies
            eval_model = SmallMLP(seed=seed)
            eval_model.set_flat_weights(server.current_weights)
            quant_acc = eval_model.evaluate(x_test, y_test)
            float_acc = float_model.evaluate(x_test, y_test)

            metrics_records.extend([
                {
                    "exp": "E1", "run_id": run_id, "seed": seed, "config_hash": config_hash,
                    "K": num_clients, "m": block_size, "d": d_params, "s": scale_bits,
                    "round": r, "method": "fl-ledger", "scenario": "honest",
                    "metric_name": "post_round_gas", "metric_value": gas_post, "unit": "gas",
                    "notes": "cold anchor storage" if r == 1 else "sequential round",
                },
                {
                    "exp": "E1", "run_id": run_id, "seed": seed, "config_hash": config_hash,
                    "K": num_clients, "m": block_size, "d": d_params, "s": scale_bits,
                    "round": r, "method": "fl-ledger", "scenario": "honest",
                    "metric_name": "finalize_round_gas", "metric_value": gas_finalize, "unit": "gas",
                    "notes": "round finalization state transition",
                },
                {
                    "exp": "E6", "run_id": run_id, "seed": seed, "config_hash": config_hash,
                    "K": num_clients, "m": block_size, "d": d_params, "s": scale_bits,
                    "round": r, "method": "fl-ledger", "scenario": "honest",
                    "metric_name": "quantised_accuracy", "metric_value": quant_acc, "unit": "fraction",
                    "notes": f"float_acc={float_acc:.4f}",
                },
            ])

        # Write CSV conforming to 06_EXPERIMENTS.md
        csv_path = RESULTS_DIR / "e1_anchor_cost.csv"
        file_exists = csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "exp", "run_id", "seed", "config_hash", "K", "m", "d", "s",
                "round", "method", "scenario", "metric_name", "metric_value", "unit", "notes"
            ])
            if not file_exists:
                writer.writeheader()
            writer.writerows(metrics_records)

        return {
            "status": "success",
            "rounds_completed": num_rounds,
            "contract_address": contract_addr,
            "final_quant_acc": quant_acc,
            "final_float_acc": float_acc,
            "csv_path": str(csv_path),
            "gas_post_round_1": metrics_records[0]["metric_value"],
        }
    finally:
        if anvil_proc is not None:
            anvil_proc.terminate()


if __name__ == "__main__":
    res = run_honest_e2e(num_rounds=3, num_clients=3, block_size=16)
    print("Honest End-to-End Run Successful!")
    print(f"Rounds: {res['rounds_completed']}")
    print(f"Final Quantised Accuracy: {res['final_quant_acc'] * 100:.2f}%")
    print(f"Final Float Accuracy:     {res['final_float_acc'] * 100:.2f}%")
    print(f"CSV saved to: {res['csv_path']}")
