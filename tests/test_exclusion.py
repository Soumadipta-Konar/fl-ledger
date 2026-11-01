"""Tests for Stage 9: Exclusion Epoch, retained mask tracking, and on-chain verification."""

import pytest
import numpy as np
from eth_account import Account

from sim.model import SmallMLP, load_partitioned_data
from sim.client import Client
from sim.server import HonestServer
from sim.watcher import Watcher
from ledger.chain import (
    get_web3,
    deploy_session,
    send_contract_tx,
    advance_blocks,
    DEFAULT_CHAIN_ID,
)
from ledger.commit import load_generators
from ledger.fixed import DEFAULT_SCALE_BITS, quantise
from ledger.merkle import MerkleTree
from sim.orchestrator import ensure_anvil_running


@pytest.fixture(scope="module")
def exclusion_setup():
    """Setup 3 clients, initial model weights, and compute initial round-1 updates."""
    seed = 42
    num_clients = 3
    block_size = 16
    client_data, _ = load_partitioned_data(num_clients=num_clients, seed=seed)

    contract_addr = "0x1234567890123456789012345678901234567890"
    session_id = bytes.fromhex(contract_addr[2:].lower()).rjust(32, b"\x00")

    clients = []
    for i in range(num_clients):
        c_acct = Account.create(f"client-{i}-{seed}")
        clients.append(Client(
            client_id=i,
            address=c_acct.address,
            private_key=c_acct.key.hex(),
            weight=(i + 1) * 10,
            data=client_data[i],
        ))

    initial_model = SmallMLP(seed=seed)
    init_flat = initial_model.get_flat_weights()

    client_pkgs = [
        c.compute_update(
            global_flat_weights=init_flat,
            block_size=block_size,
            session_id=session_id,
            round_num=1,
            chain_id=DEFAULT_CHAIN_ID,
            contract_address=contract_addr,
            nonce=0,
            seed=42,
        )
        for c in clients
    ]

    return clients, init_flat, block_size, contract_addr, session_id, client_pkgs


def test_server_reaggregation_with_retained_mask(exclusion_setup):
    """Verify off-chain server re-aggregates exclusively over retained participants."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = exclusion_setup

    server = HonestServer(init_flat, block_size=block_size)
    init_w_blocks = [
        server.w_t_int[i : i + block_size]
        for i in range(0, len(server.w_t_int), block_size)
    ]

    # Full aggregation in Round 1 (mask = 0b111 = 7)
    pkg_full = server.aggregate_round(1, client_pkgs, participant_mask=7)
    assert pkg_full.participant_mask == 7
    assert pkg_full.claimed_weight == 60
    assert len(pkg_full.active_packages) == 3

    # Client 2 requests exclusion -> retained mask = 0b011 = 3
    retained_mask = 3
    server_rerun = HonestServer(init_flat, block_size=block_size)
    pkg_rerun = server_rerun.aggregate_round(1, client_pkgs, participant_mask=retained_mask)

    # 1. Verification of exclusion in post package
    assert pkg_rerun.participant_mask == 3
    assert pkg_rerun.claimed_weight == clients[0].weight + clients[1].weight  # 10 + 20 = 30
    assert len(pkg_rerun.active_packages) == 2
    active_ids = [p.client_id for p in pkg_rerun.active_packages]
    assert 2 not in active_ids
    assert active_ids == [0, 1]

    # 2. Excluded client leaf is absent from client leaves tree
    leaf_c2 = (
        client_pkgs[2].client_id.to_bytes(1, "big")
        + bytes.fromhex(client_pkgs[2].address[2:])
        + client_pkgs[2].client_block_root
        + client_pkgs[2].signature
    )
    for leaf in pkg_rerun.client_merkle_tree.raw_leaves:
        assert leaf != leaf_c2

    # 3. Model root changes because excluded client is removed
    assert pkg_rerun.model_root_next != pkg_full.model_root_next

    # 4. Watcher audits and passes faithful retained aggregation
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)
    audit_passed = watcher.verify_round(pkg_rerun, init_w_blocks)
    assert audit_passed is True


def test_cheating_secret_inclusion_caught_by_watcher(exclusion_setup):
    """Verify watcher detects and flags when server secretly includes excluded client."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = exclusion_setup

    server = HonestServer(init_flat, block_size=block_size)
    init_w_blocks = [
        server.w_t_int[i : i + block_size]
        for i in range(0, len(server.w_t_int), block_size)
    ]

    # Retained aggregation (mask = 3)
    pkg = server.aggregate_round(1, client_pkgs, participant_mask=3)

    # Server secretly taints U_b by incorporating client 2's contribution
    pkg.u_blocks[0][0] += clients[2].weight * 10

    # Rebuild agg merkle tree with tainted U_b
    agg_leaves = []
    for b_idx in range(len(pkg.u_blocks)):
        agg_leaves.append(
            b_idx.to_bytes(4, "big")
            + pkg.r_blocks[b_idx].to_bytes(32, "big")
            + b"".join(v.to_bytes(32, "big", signed=True) for v in pkg.u_blocks[b_idx])
        )
    pkg.agg_merkle_tree = MerkleTree(agg_leaves)
    pkg.agg_root = pkg.agg_merkle_tree.root

    # Watcher audits block 0 and catches D1 homomorphism violation
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)
    verdict = watcher.audit_round(pkg, init_w_blocks, sampled_block_indices=[0])
    assert verdict.passed is False
    assert verdict.deviation_type == "D1_HOMOMORPHISM"


def test_onchain_exclusion_epoch_flow():
    """Verify live end-to-end on-chain exclusion epoch workflow on Anvil."""
    anvil_proc = ensure_anvil_running()
    w3 = get_web3()

    seed = 1337
    admin_acct = Account.create(f"admin-ex-{seed}")
    server_acct = Account.create(f"server-ex-{seed}")
    treasury_acct = Account.create(f"treasury-ex-{seed}")

    funder = Account.from_key("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
    f_nonce = w3.eth.get_transaction_count(funder.address)
    for target in [admin_acct.address, server_acct.address]:
        tx = {
            "from": funder.address,
            "to": target,
            "value": w3.to_wei(20, "ether"),
            "nonce": f_nonce,
            "gas": 21000,
            "gasPrice": w3.eth.gas_price,
            "chainId": DEFAULT_CHAIN_ID,
        }
        signed = funder.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        f_nonce += 1

    # Setup 3 clients
    num_clients = 3
    block_size = 16
    client_data, _ = load_partitioned_data(num_clients=num_clients, seed=seed)
    clients = []
    for i in range(num_clients):
        c_acct = Account.create(f"client-onchain-{i}-{seed}")
        # Fund client account for sending requestExclusion tx
        tx = {
            "from": funder.address,
            "to": c_acct.address,
            "value": w3.to_wei(2, "ether"),
            "nonce": f_nonce,
            "gas": 21000,
            "gasPrice": w3.eth.gas_price,
            "chainId": DEFAULT_CHAIN_ID,
        }
        signed = funder.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        f_nonce += 1

        clients.append(Client(
            client_id=i,
            address=c_acct.address,
            private_key=c_acct.key.hex(),
            weight=(i + 1) * 10,
            data=client_data[i],
        ))

    # Generators and session deployment
    h_gen, g_gens, gens_hash = load_generators()
    init_model = SmallMLP(seed=seed)
    init_flat = init_model.get_flat_weights()
    d_params = len(init_flat)

    init_int = [quantise(float(v)) for v in init_flat]
    model_leaves = []
    num_blocks = (d_params + block_size - 1) // block_size
    for b_idx in range(num_blocks):
        chunk = init_int[b_idx * block_size : (b_idx + 1) * block_size]
        if len(chunk) < block_size:
            chunk = chunk + [0] * (block_size - len(chunk))
        leaf = b_idx.to_bytes(4, "big") + b"".join(v.to_bytes(32, "big", signed=True) for v in chunk)
        model_leaves.append(leaf)
    init_model_root = MerkleTree(model_leaves).root

    params = {
        "initialAdmin": admin_acct.address,
        "adminDelay": 0,
        "server": server_acct.address,
        "treasury": treasury_acct.address,
        "maxClients": num_clients,
        "blockSize": block_size,
        "scaleBits": DEFAULT_SCALE_BITS,
        "challengeWindowBlocks": 20,
        "withdrawalDelayBlocks": 40,
        "bondAmountWei": w3.to_wei(10, "ether"),
        "challengerDepositWei": w3.to_wei(1, "ether"),
        "rewardShareBps": 5000,
        "generatorsHash": gens_hash,
    }

    contract_addr, _ = deploy_session(w3, admin_acct.key.hex(), params)
    session_id = bytes.fromhex(contract_addr[2:].lower()).rjust(32, b"\x00")

    # Register clients
    for c in clients:
        send_contract_tx(w3, contract_addr, admin_acct.key.hex(), "register", c.address, c.weight)

    # Deposit bond and start
    send_contract_tx(w3, contract_addr, server_acct.key.hex(), "depositBond", value=w3.to_wei(10, "ether"))
    send_contract_tx(w3, contract_addr, admin_acct.key.hex(), "start", init_model_root)

    # 1. Execute Round 1 with all 3 clients (mask = 7)
    server = HonestServer(init_flat, block_size=block_size)
    client_pkgs = [
        c.compute_update(
            global_flat_weights=init_flat,
            block_size=block_size,
            session_id=session_id,
            round_num=1,
            chain_id=DEFAULT_CHAIN_ID,
            contract_address=contract_addr,
            nonce=0,
            seed=seed,
        )
        for c in clients
    ]

    pkg_r1 = server.aggregate_round(1, client_pkgs, participant_mask=7)
    send_contract_tx(
        w3, contract_addr, server_acct.key.hex(), "postRound",
        1, pkg_r1.model_root_next, pkg_r1.agg_root, pkg_r1.client_leaves_root,
        pkg_r1.participant_mask, pkg_r1.claimed_weight
    )
    advance_blocks(w3, 21)
    send_contract_tx(w3, contract_addr, admin_acct.key.hex(), "finalizeRound", 1)

    # Verify on-chain round 1 finalized
    from ledger.chain import load_session_abi_and_bytecode
    abi, _ = load_session_abi_and_bytecode()
    contract = w3.eth.contract(address=contract_addr, abi=abi)
    assert contract.functions.currentRound().call() == 1
    assert contract.functions.getEpoch().call() == 0
    assert contract.functions.getRetainedMask().call() == 7

    # 2. Client 2 requests exclusion on-chain
    receipt_ex = send_contract_tx(w3, contract_addr, clients[2].private_key, "requestExclusion")
    gas_exclusion = receipt_ex.gasUsed
    assert receipt_ex.status == 1

    # Verify on-chain exclusion epoch state
    assert contract.functions.getEpoch().call() == 1
    assert contract.functions.getRetainedMask().call() == 3
    assert contract.functions.isExcluded(clients[2].address).call() is True
    assert contract.functions.currentRound().call() == 0

    # 3. Server attempts cheating: include excluded client 2 in Epoch 1 Round 1
    receipt_cheat = send_contract_tx(
        w3, contract_addr, server_acct.key.hex(), "postRound",
        1, pkg_r1.model_root_next, pkg_r1.agg_root, pkg_r1.client_leaves_root,
        7, 60  # Mask 7 contains excluded client 2
    )
    assert receipt_cheat.status == 0, "Cheating postRound with excluded client must revert (status == 0)!"

    # 4. Server faithfully re-runs Round 1 with retained set (clients 0 and 1)
    server_rerun = HonestServer(init_flat, block_size=block_size)
    client_pkgs_rerun = [
        c.compute_update(
            global_flat_weights=init_flat,
            block_size=block_size,
            session_id=session_id,
            round_num=1,
            chain_id=DEFAULT_CHAIN_ID,
            contract_address=contract_addr,
            nonce=0,
            seed=seed + 1,
        )
        for c in clients[:2]
    ]

    pkg_rerun = server_rerun.aggregate_round(1, client_pkgs_rerun, participant_mask=3)
    receipt_post_rerun = send_contract_tx(
        w3, contract_addr, server_acct.key.hex(), "postRound",
        1, pkg_rerun.model_root_next, pkg_rerun.agg_root, pkg_rerun.client_leaves_root,
        pkg_rerun.participant_mask, pkg_rerun.claimed_weight
    )
    gas_post_rerun = receipt_post_rerun.gasUsed
    assert receipt_post_rerun.status == 1

    advance_blocks(w3, 21)
    receipt_fin_rerun = send_contract_tx(w3, contract_addr, admin_acct.key.hex(), "finalizeRound", 1)
    gas_finalize_rerun = receipt_fin_rerun.gasUsed

    assert contract.functions.currentRound().call() == 1
    assert contract.functions.getRound(1).call()[0] == pkg_rerun.model_root_next

    # Print reported costs for Stage 9 DoD
    print(f"\n[Stage 9 Exclusion Epoch Reported Costs]")
    print(f"  requestExclusion() Gas: {gas_exclusion:,} gas")
    print(f"  Epoch 1 postRound() Gas: {gas_post_rerun:,} gas")
    print(f"  Epoch 1 finalizeRound() Gas: {gas_finalize_rerun:,} gas")
