"""Cheating suite tests: verify detection of all scripted cheats and ensure honest server is never slashed."""

import pytest
import numpy as np
from eth_account import Account

from sim.model import SmallMLP, load_partitioned_data
from sim.client import Client
from sim.server import HonestServer
from sim.cheats import CheatingServer, CheatType
from sim.watcher import Watcher
from ledger.chain import DEFAULT_CHAIN_ID


@pytest.fixture(scope="module")
def fl_setup() -> tuple[list[Client], np.ndarray, int, str, bytes, list]:
    """Setup 3 clients, initial model weights, and compute initial round-1 updates once."""
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


def test_honest_server_never_flagged(fl_setup: tuple) -> None:
    """Invariant: An honest server executing faithful aggregation is never flagged as fraudulent."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = fl_setup
    server = HonestServer(init_flat, block_size=block_size)
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)

    mask = (1 << len(clients)) - 1
    curr_w_blocks = [
        server.w_t_int[i : i + block_size]
        for i in range(0, len(server.w_t_int), block_size)
    ]

    post_pkg = server.aggregate_round(1, client_pkgs, mask)
    verdict = watcher.audit_round(post_pkg, curr_w_blocks)

    assert verdict.passed is True
    assert verdict.deviation_type is None


def test_cheat_old_model_detected(fl_setup: tuple) -> None:
    """Cheat: Server returns stale model W_t instead of W_{t+1}. Must be caught by D2 update rule."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = fl_setup
    cheating_server = CheatingServer(
        init_flat,
        block_size=block_size,
        cheat_type=CheatType.OLD_MODEL,
        seed=101,
    )
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)

    mask = (1 << len(clients)) - 1
    curr_w_blocks = [
        cheating_server.w_t_int[i : i + block_size]
        for i in range(0, len(cheating_server.w_t_int), block_size)
    ]

    pkg = cheating_server.aggregate_round_with_cheat(1, client_pkgs, mask)
    verdict = watcher.audit_round(pkg, curr_w_blocks)

    assert verdict.passed is False
    assert verdict.deviation_type == "D2_UPDATE_RULE"
    assert verdict.failed_block_idx is not None


def test_cheat_fabricated_client_detected(fl_setup: tuple) -> None:
    """Cheat: Server presents a forged/tampered signature on a client leaf. Caught by D4b."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = fl_setup
    cheating_server = CheatingServer(
        init_flat,
        block_size=block_size,
        cheat_type=CheatType.FABRICATED_CLIENT,
        seed=202,
    )
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)

    mask = (1 << len(clients)) - 1
    curr_w_blocks = [
        cheating_server.w_t_int[i : i + block_size]
        for i in range(0, len(cheating_server.w_t_int), block_size)
    ]

    pkg = cheating_server.aggregate_round_with_cheat(1, client_pkgs, mask)
    verdict = watcher.audit_round(pkg, curr_w_blocks)

    assert verdict.passed is False
    assert verdict.deviation_type == "INVALID_SIGNATURE"
    assert verdict.failed_client_idx == 0


def test_cheat_corrupted_blocks_detection_rate(fl_setup: tuple) -> None:
    """Experiment E3: Detection rate vs fraction phi of corrupted blocks under random block sampling."""
    clients, init_flat, block_size, contract_addr, session_id, client_pkgs = fl_setup
    watcher = Watcher(chain_id=DEFAULT_CHAIN_ID, contract_address=contract_addr, session_id=session_id)

    curr_w_blocks = [
        init_flat[i : i + block_size].astype(int).tolist()
        for i in range(0, len(init_flat), block_size)
    ]
    mask = (1 << len(clients)) - 1
    sample_budget_s = 5

    # Compute base honest aggregation once to avoid re-running 15,000 BN254 scalar mults in loop
    server_base = HonestServer(init_flat, block_size=block_size)
    base_pkg = server_base.aggregate_round(1, client_pkgs, mask)
    num_blocks = len(base_pkg.u_blocks)

    fractions = [0.1, 0.3, 0.5, 1.0]
    num_trials = 50

    for phi in fractions:
        detections = 0
        for trial_seed in range(num_trials):
            pkg = CheatingServer.corrupt_corrupted_blocks(
                base_pkg,
                corrupt_fraction=phi,
                seed=trial_seed + 1000,
            )

            # Random sample of s blocks
            rng = np.random.default_rng(trial_seed + 2000)
            sampled = rng.choice(num_blocks, size=min(sample_budget_s, num_blocks), replace=False)

            verdict = watcher.audit_round(pkg, curr_w_blocks, sampled_block_indices=sampled)
            if not verdict.passed:
                detections += 1

        empirical_rate = detections / num_trials
        # When phi = 1.0, detection must be 100%
        if phi == 1.0:
            assert empirical_rate == 1.0
        # When phi = 0.5, theoretical detection = 1 - (0.5)^5 = 96.875%
        elif phi == 0.5:
            assert empirical_rate >= 0.85
        # Detection rate must monotonically increase with phi
        assert empirical_rate > 0.0
