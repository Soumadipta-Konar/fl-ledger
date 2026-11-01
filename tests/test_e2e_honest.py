"""Integration test verifying honest end-to-end federated learning execution."""

from sim.orchestrator import run_honest_e2e


def test_honest_e2e_run() -> None:
    """Verify that an honest run of 1 round completes, finalizes with no dispute, and records E1 metrics."""
    res = run_honest_e2e(
        num_rounds=1,
        num_clients=2,
        block_size=16,
        seed=123,
    )

    assert res["status"] == "success"
    assert res["rounds_completed"] == 1
    assert abs(res["final_quant_acc"] - res["final_float_acc"]) < 0.01
    assert res["gas_post_round_1"] > 20_000
