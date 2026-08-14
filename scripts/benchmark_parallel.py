#!/usr/bin/env python3
"""Benchmark parallel processing infrastructure."""
from __future__ import annotations

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.parallel import (
    get_cpu_info,
    get_optimal_workers,
    grid_search_parallel,
    parallel_map,
    run_monte_carlo,
    thread_map,
)

# ── Module-level worker functions (picklable for Windows spawn) ────────────

def cpu_task(x: float) -> float:
    """CPU-heavy task: 2M iterations of math."""
    s = 0.0
    for i in range(2_000_000):
        s += math.sqrt(i) * math.sin(x) + math.cos(i * x)
    return s


def simulate_trade() -> float:
    return random.gauss(0, 1) * 50


def strategy_eval(risk_mult: float, take_profit: float, stop_loss: float) -> float:
    return random.gauss(0, 1) * risk_mult + take_profit - stop_loss


def io_task(url: str) -> str:
    time.sleep(0.5)
    return f"data from {url}"


def main() -> None:
    info = get_cpu_info()
    print("=" * 60)
    print("PARALLEL PROCESSING BENCHMARK")
    print("=" * 60)
    print(f"Logical CPUs:     {info['logical_cpus']}")
    print(f"Max workers:     {info['max_workers']}")
    print(f"Perf workers:    {info['perf_workers']}")
    print(f"Hybrid CPU:       {info['is_hybrid']}")
    print(f"GIL disabled:     {info['gil_disabled']}")
    print(f"Numba threads:    {info['numba_threads']}")
    print(f"Polars threads:   {info['polars_threads']}")
    print()

    # ── Benchmark 1: CPU-bound parallel_map ───────────────────────────
    print("── Benchmark 1: CPU-bound (8 tasks × 2M iterations) ──")
    items = [0.5 * i for i in range(8)]

    t0 = time.time()
    _serial = [cpu_task(x) for x in items]
    t_serial = time.time() - t0

    t0 = time.time()
    _parallel = parallel_map(cpu_task, items)
    t_parallel = time.time() - t0

    speedup = t_serial / t_parallel if t_parallel > 0 else 0
    print(f"  Serial:   {t_serial:.2f}s")
    print(f"  Parallel: {t_parallel:.2f}s  ({get_optimal_workers()} workers)")
    print(f"  Speedup:  {speedup:.2f}x")

    # ── Benchmark 2: Monte Carlo ──────────────────────────────────────
    print("\n── Benchmark 2: Monte Carlo (10k simulations) ──")
    t0 = time.time()
    stats = run_monte_carlo(simulate_trade, n=10_000, chunk_size=1000)
    t_mc = time.time() - t0
    print(f"  Time:      {t_mc:.2f}s")
    print(f"  Workers:   {stats['workers']}")
    print(f"  Mean PnL:  ${stats['mean']:.2f}")
    print(f"  Std:       ${stats['std']:.2f}")
    print(f"  P5:        ${stats['p5']:.2f}")
    print(f"  P95:       ${stats['p95']:.2f}")
    print(f"  Median:    ${stats['median']:.2f}")

    # ── Benchmark 3: Grid search ──────────────────────────────────────
    print("\n── Benchmark 3: Grid Search (27 param combos) ──")
    grid = [
        {"risk_mult": r, "take_profit": tp, "stop_loss": sl}
        for r in [0.5, 1.0, 2.0]
        for tp in [10, 20, 30]
        for sl in [5, 10, 15]
    ]
    t0 = time.time()
    results = grid_search_parallel(strategy_eval, grid)
    t_gs = time.time() - t0
    print(f"  Time:     {t_gs:.2f}s")
    print(f"  Combos:   {len(grid)}")
    print(f"  Best:     score={results[0]['score']:.4f} params={results[0]['params']}")

    # ── Benchmark 4: Thread map (I/O simulation) ────────────────────────
    print("\n── Benchmark 4: Thread Map (8 I/O tasks × 0.5s) ──")
    urls = [f"api://endpoint{i}" for i in range(8)]
    t0 = time.time()
    _ = thread_map(io_task, urls)
    t_thread = time.time() - t0
    print(f"  Time:     {t_thread:.2f}s  (serial would be 4.0s)")

    print("\n" + "=" * 60)
    print("ALL BENCHMARKS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
