"""Benchmark script for BN254 G1 curve operations and Pedersen commitments.

Measures:
- Point addition and scalar multiplication latency in py_ecc.
- Block commitment time across block sizes m in {8, 16, 32}.
- Projected client-round commitment latency across model dimensions d in {16, 64, 256, 1024, 10000}.
"""

from __future__ import annotations

import time
import random
from ledger.commit import commit_block, scalar_mul, add_points, get_default_generators


def benchmark() -> dict[str, float]:
    h_gen, g_gens = get_default_generators()
    results: dict[str, float] = {}

    # 1. Micro-benchmark: single scalar multiplication
    n_trials = 100
    scalars = [random.randint(1, 2**31) for _ in range(n_trials)]
    start = time.perf_counter()
    for s in scalars:
        _ = scalar_mul(h_gen, s)
    elapsed_mul = (time.perf_counter() - start) / n_trials
    results["single_mul_ms"] = elapsed_mul * 1000.0

    # 2. Micro-benchmark: single point addition
    p1 = scalar_mul(h_gen, 12345)
    p2 = scalar_mul(g_gens[0], 67890)
    start = time.perf_counter()
    for _ in range(n_trials):
        _ = add_points(p1, p2)
    elapsed_add = (time.perf_counter() - start) / n_trials
    results["single_add_ms"] = elapsed_add * 1000.0

    # 3. Block commitments across block size m
    for m in [8, 16, 32]:
        q_block = [random.randint(-1000, 1000) for _ in range(m)]
        r_val = random.randint(1, 2**31)
        trials = 20
        start = time.perf_counter()
        for _ in range(trials):
            _ = commit_block(q_block, r_val, h_gen=h_gen, g_gens=g_gens[:m])
        elapsed_block = (time.perf_counter() - start) / trials
        results[f"commit_m_{m}_ms"] = elapsed_block * 1000.0

    # 4. Projected client-round commitment times for model size d (m = 16)
    m_default = 16
    t_per_block = results[f"commit_m_{m_default}_ms"] / 1000.0
    for d in [16, 64, 256, 1024, 10000]:
        num_blocks = (d + m_default - 1) // m_default
        results[f"proj_client_round_d_{d}_s"] = num_blocks * t_per_block

    return results


def main() -> None:
    print("Running BN254 G1 Pedersen commitment benchmark (py_ecc)...")
    res = benchmark()

    print("\n--- Micro-benchmark Results ---")
    print(f"Point multiplication (py_ecc): {res['single_mul_ms']:.3f} ms / op")
    print(f"Point addition (py_ecc):       {res['single_add_ms']:.3f} ms / op")

    print("\n--- Block Commitment Latency (1 blinding + m weights) ---")
    for m in [8, 16, 32]:
        print(f"Block size m={m:2d}: {res[f'commit_m_{m}_ms']:.2f} ms")

    print("\n--- Projected Client-Round Commitment Time (m=16) ---")
    for d in [16, 64, 256, 1024, 10000]:
        t_sec = res[f"proj_client_round_d_{d}_s"]
        if t_sec < 1.0:
            print(f"Model dim d={d:5d} ({d//16:3d} blocks): {t_sec*1000.0:.1f} ms")
        else:
            print(f"Model dim d={d:5d} ({d//16:3d} blocks): {t_sec:.2f} s")


if __name__ == "__main__":
    main()
