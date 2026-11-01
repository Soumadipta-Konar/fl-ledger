"""Experiment E6: Fixed-Point Quantisation Accuracy vs Scale Bits s.

Hypothesis: For scale bits s >= 12 (including default s = 16), fixed-point quantisation
incur zero measurable accuracy degradation compared to unquantised float32 training (|delta| < 0.05%),
while strictly maintaining integer weights within safe bounds [-2^31, 2^31 - 1].
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
import numpy as np

from experiments.common import (
    RESULTS_DIR,
    compute_config_hash,
    SCHEMA,
)
from sim.model import SmallMLP, load_partitioned_data
from sim.client import Client
from sim.server import HonestServer
from ledger.fixed import quantise, dequantise

E6_CSV = RESULTS_DIR / "e6_quantisation_accuracy.csv"


def train_fl_simulation(
    num_rounds: int,
    scale_bits: int | None,
    client_data: list[tuple[np.ndarray, np.ndarray]],
    test_set: tuple[np.ndarray, np.ndarray],
    seed: int,
) -> list[float]:
    """Train federated model with or without fixed-point quantisation."""
    x_test, y_test = test_set
    num_clients = len(client_data)
    initial_model = SmallMLP(seed=seed)
    w_curr = initial_model.get_flat_weights().copy()

    accuracies: list[float] = []

    for r in range(1, num_rounds + 1):
        # 1. Clients compute local updates
        client_updates = []
        total_weight = 0
        for i in range(num_clients):
            c_weight = (i + 1) * 10
            total_weight += c_weight
            m = SmallMLP(seed=seed + r * 10 + i)
            m.set_flat_weights(w_curr)
            x_c, y_c = client_data[i]
            m.train_step(x_c, y_c, lr=0.05)
            delta = m.get_flat_weights() - w_curr

            if scale_bits is not None:
                # Fixed-point quantisation
                delta_int = np.array([quantise(float(v), scale_bits=scale_bits) for v in delta], dtype=np.int64)
                delta_q = np.array([dequantise(int(v), scale_bits=scale_bits) for v in delta_int], dtype=np.float32)
                client_updates.append(delta_q * c_weight)
            else:
                # Pure float32
                client_updates.append(delta * c_weight)

        # 2. Server aggregates weighted updates
        agg_update = np.sum(client_updates, axis=0) / total_weight
        w_curr = w_curr + agg_update

        # 3. Evaluate on global test set
        eval_model = SmallMLP(seed=seed)
        eval_model.set_flat_weights(w_curr)
        acc = eval_model.evaluate(x_test, y_test)
        accuracies.append(acc)

    return accuracies


def run_e6_experiments() -> list[dict[str, Any]]:
    """Execute E6 accuracy evaluation across scale bits s in {4, 8, 12, 16, 20, 24}."""
    rows: list[dict[str, Any]] = []

    num_clients = 3
    num_rounds = 5
    d_model = 1210
    block_size = 16
    scale_bits_list = [4, 8, 12, 16, 20, 24]
    seeds = [42, 101, 202]

    for seed in seeds:
        client_data, test_set = load_partitioned_data(num_clients=num_clients, seed=seed)

        # Run float baseline
        float_accs = train_fl_simulation(num_rounds, None, client_data, test_set, seed)

        for r_idx, f_acc in enumerate(float_accs, start=1):
            config_f = {"exp": "E6", "method": "float_baseline", "round": r_idx, "seed": seed}
            rows.append({
                "exp": "E6", "run_id": f"e6-float-s{seed}", "seed": seed,
                "config_hash": compute_config_hash(config_f),
                "K": num_clients, "m": block_size, "d": d_model, "s": 0, "round": r_idx,
                "method": "float-baseline", "scenario": "unquantised_float32",
                "metric_name": "test_accuracy", "metric_value": round(float(f_acc), 4),
                "unit": "fraction", "notes": "unquantised float32 reference training",
            })

        # Run quantised for each scale bits s
        for s in scale_bits_list:
            quant_accs = train_fl_simulation(num_rounds, s, client_data, test_set, seed)
            config_q = {"exp": "E6", "scale_bits": s, "seed": seed}
            cfg_hash = compute_config_hash(config_q)
            run_id = f"e6-s{s}-seed{seed}"

            for r_idx, q_acc in enumerate(quant_accs, start=1):
                f_acc = float_accs[r_idx - 1]
                abs_diff = abs(q_acc - f_acc)

                # Accuracy
                rows.append({
                    "exp": "E6", "run_id": run_id, "seed": seed, "config_hash": cfg_hash,
                    "K": num_clients, "m": block_size, "d": d_model, "s": s, "round": r_idx,
                    "method": "fl-ledger", "scenario": f"quantised_s{s}",
                    "metric_name": "test_accuracy", "metric_value": round(float(q_acc), 4),
                    "unit": "fraction", "notes": f"quantised accuracy with scale_bits={s}",
                })

                # Accuracy difference vs float baseline
                rows.append({
                    "exp": "E6", "run_id": run_id, "seed": seed, "config_hash": cfg_hash,
                    "K": num_clients, "m": block_size, "d": d_model, "s": s, "round": r_idx,
                    "method": "fl-ledger", "scenario": f"quantised_s{s}",
                    "metric_name": "quantisation_error", "metric_value": round(float(abs_diff), 6),
                    "unit": "fraction", "notes": f"|acc_quant - acc_float| vs float baseline",
                })

    # Overwrite E6 CSV
    with open(E6_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SCHEMA)
        for r in rows:
            writer.writerow([str(r.get(col, "")) for col in SCHEMA])

    return rows


if __name__ == "__main__":
    results = run_e6_experiments()
    print(f"E6 Complete: {len(results)} rows written to {E6_CSV}")
