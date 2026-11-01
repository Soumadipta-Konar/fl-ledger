"""Master Experiment Runner for Stage 7 (Experiments E1 to E8).

Executes all 8 empirical evaluation modules and verifies that all output CSVs
adhere strictly to the 15-column schema:
`exp, run_id, seed, config_hash, K, m, d, s, round, method, scenario, metric_name, metric_value, unit, notes`
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from experiments.common import RESULTS_DIR, SCHEMA
from experiments.e1_anchor_cost import run_e1_experiments
from experiments.e2_dispute_cost import run_e2_experiments
from experiments.e3_detection_rate import run_e3_experiments
from experiments.e4_crossover import run_e4_experiments
from experiments.e5_offchain_cost import run_e5_experiments
from experiments.e6_quantisation_accuracy import run_e6_experiments
from experiments.e7_adversarial_trials import run_e7_experiments
from experiments.e8_dispute_latency import run_e8_experiments

EXPECTED_FILES = [
    ("E1", "e1_anchor_cost.csv"),
    ("E2", "e2_dispute_gas.csv"),
    ("E3", "e3_detection_rate.csv"),
    ("E4", "e4_crossover.csv"),
    ("E5", "e5_commit_time.csv"),
    ("E6", "e6_quantisation_accuracy.csv"),
    ("E7", "e7_adversarial_trials.csv"),
    ("E8", "e8_dispute_latency.csv"),
]


def verify_csv_schema(csv_path: Path) -> tuple[bool, int, str]:
    """Verify that CSV file exists, is non-empty, and matches the 15-column schema."""
    if not csv_path.exists():
        return False, 0, f"File {csv_path.name} not found"

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return False, 0, f"File {csv_path.name} is empty"

        if header != SCHEMA:
            return False, 0, f"Header mismatch in {csv_path.name}: expected {SCHEMA}, got {header}"

        row_count = 0
        for line_num, row in enumerate(reader, start=2):
            if len(row) != len(SCHEMA):
                return False, row_count, f"Row {line_num} in {csv_path.name} has {len(row)} columns, expected {len(SCHEMA)}"
            row_count += 1

    return True, row_count, "OK"


def run_all() -> None:
    """Run all 8 experiments sequentially and validate results."""
    print("=" * 70)
    print("STARTING STAGE 7: REPRODUCIBLE EXPERIMENT SUITE (E1 to E8)")
    print("=" * 70)

    start_total = time.time()
    runners = [
        ("E1: On-Chain Anchor Cost", run_e1_experiments),
        ("E2: Dispute Gas vs Cost Model", run_e2_experiments),
        ("E3: Adversarial Cheat Detection Rate", run_e3_experiments),
        ("E4: On-Chain Crossover vs Baseline", run_e4_experiments),
        ("E5: Off-Chain Latency & Proof Sizes", run_e5_experiments),
        ("E6: Fixed-Point Quantisation Accuracy", run_e6_experiments),
        ("E7: False Accusation Adversarial Trials", run_e7_experiments),
        ("E8: Dispute & Lifecycle Latency", run_e8_experiments),
    ]

    for label, fn in runners:
        t0 = time.time()
        print(f"\n[RUNNING] {label}...")
        res = fn()
        elapsed = time.time() - t0
        print(f"  -> Generated {len(res)} rows in {elapsed:.2f}s")

    print("\n" + "=" * 70)
    print("VERIFYING RESULTS CSV INTEGRITY & 15-COLUMN SCHEMA CONFORMANCE")
    print("=" * 70)

    all_valid = True
    total_records = 0

    print(f"{'Exp':<6} | {'Filename':<32} | {'Rows':<8} | {'Schema Status'}")
    print("-" * 70)

    for exp_id, filename in EXPECTED_FILES:
        filepath = RESULTS_DIR / filename
        valid, count, msg = verify_csv_schema(filepath)
        total_records += count
        if not valid:
            all_valid = False
            print(f"{exp_id:<6} | {filename:<32} | {count:<8} | FAILED: {msg}")
        else:
            print(f"{exp_id:<6} | {filename:<32} | {count:<8} | PASS ({msg})")

    print("-" * 70)
    print(f"Total Rows Generated across all 8 experiments: {total_records}")
    print(f"Total Execution Time: {time.time() - start_total:.2f}s")

    if not all_valid:
        print("\nERROR: Schema verification failed on one or more CSVs!")
        sys.exit(1)
    else:
        print("\nSUCCESS: All 8 experiment CSVs adhere strictly to the 15-column schema!")


if __name__ == "__main__":
    run_all()
