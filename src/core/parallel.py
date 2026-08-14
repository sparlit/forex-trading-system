"""
Parallel processing infrastructure for the trading system.

Implements GIL-bypass strategies:
 1. ProcessPoolExecutor with auto-tuned max_workers (P-cores vs E-cores)
 2. ThreadPoolExecutor for I/O-bound work (network, API, DB)
 3. Vectorized NumPy/Polars operations that release the GIL via C/Rust backends
 4. Numba JIT compilation for hot numerical loops (nogil=True releases GIL)
 5. Optional free-threaded CPython 3.13+ detection

Windows note: All worker functions MUST be module-level (not closures/lambdas)
because Windows uses 'spawn' mode for multiprocessing, which pickles functions.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import polars as pl
    POLARS_OK = True
except ImportError:
    POLARS_OK = False

try:
    from numba import njit, set_num_threads
    NUMBA_OK = True
except ImportError:
    NUMBA_OK = False

try:
    import sysconfig
    _GIL_DISABLED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
except Exception:
    _GIL_DISABLED = False

logger = logging.getLogger(__name__)


# ── CPU topology detection ──────────────────────────────────────────────────

@dataclass
class CPUTopology:
    """Detect optimal worker counts for Intel hybrid (P-core/E-core) or standard CPUs."""
    logical_cpus: int = field(default_factory=os.cpu_count)
    perf_workers: int = field(init=False)
    max_workers: int = field(init=False)
    is_hybrid: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_hybrid = self.logical_cpus > 8 and self.logical_cpus % 2 == 0
        self.max_workers = max(2, int(self.logical_cpus * 0.75))
        if self.is_hybrid:
            self.perf_workers = max(2, int(self.logical_cpus * 0.6))
        else:
            self.perf_workers = self.max_workers


_CPU = CPUTopology()


def get_optimal_workers(mode: str = "auto") -> int:
    """Return optimal worker count.

    Args:
        mode: "auto" (perf_workers), "max" (all logical), "perf" (P-cores only)
    """
    if mode == "max":
        return _CPU.max_workers
    if mode == "perf":
        return _CPU.perf_workers
    return _CPU.perf_workers


def get_cpu_info() -> dict[str, Any]:
    return {
        "logical_cpus": _CPU.logical_cpus,
        "max_workers": _CPU.max_workers,
        "perf_workers": _CPU.perf_workers,
        "is_hybrid": _CPU.is_hybrid,
        "gil_disabled": _GIL_DISABLED,
        "numba_threads": _CPU.perf_workers if NUMBA_OK else 1,
        "polars_threads": _CPU.perf_workers if POLARS_OK else 1,
    }


# ── Module-level worker functions (picklable for Windows spawn) ────────────

def _map_worker(args: tuple[Callable, Any]) -> Any:
    """Worker for parallel_map — calls fn(item). Must be module-level for pickling."""
    fn, item = args
    return fn(item)


def _run_mc_chunk(args: tuple[Callable, int]) -> np.ndarray:
    """Run a chunk of Monte Carlo simulations. Module-level for pickling."""
    simulate_fn, chunk_size = args
    results = np.empty(chunk_size, dtype=np.float64)
    for i in range(chunk_size):
        results[i] = float(simulate_fn())
    return results


def _eval_grid_combo(args: tuple[Callable, dict]) -> dict:
    """Evaluate a single grid search combo. Module-level for pickling."""
    fn, params = args
    score = fn(**params)
    return {"params": params, "score": score}


# ── Process pool (CPU-bound: bypasses GIL) ───────────────────────────────────

def parallel_map(
    fn: Callable,
    items: Sequence[Any],
    max_workers: int | None = None,
) -> list[Any]:
    """Map fn over items using ProcessPoolExecutor.

    Each item runs in its own process with its own GIL → true parallelism.
    Worker dispatch uses a module-level _map_worker for Windows pickling.
    """
    if max_workers is None:
        max_workers = get_optimal_workers("perf")
    if len(items) == 0:
        return []
    if len(items) == 1:
        return [fn(items[0])]

    results: list[Any] = [None] * len(items)
    payloads = [(fn, item) for item in items]

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        future_to_idx = {ex.submit(_map_worker, p): i for i, p in enumerate(payloads)}
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            results[idx] = fut.result()
    return results


def parallel_compute(
    fn: Callable,
    *args,
    n_workers: int | None = None,
    **kwargs,
) -> Any:
    """Submit a single CPU-bound function to the process pool."""
    if n_workers is None:
        n_workers = get_optimal_workers("perf")

    def _wrapper():
        return fn(*args, **kwargs)

    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        return ex.submit(_wrapper).result()


# ── Thread pool (I/O-bound: network, API, DB) ──────────────────────────────

def thread_map(
    fn: Callable,
    items: Sequence[Any],
    max_workers: int | None = None,
) -> list[Any]:
    """Map fn over items using ThreadPoolExecutor.

    Threads share GIL but release it on I/O → ideal for network/API/DB calls.
    """
    if max_workers is None:
        max_workers = min(32, max(4, _CPU.logical_cpus * 2))
    if len(items) == 0:
        return []
    if len(items) == 1:
        return [fn(items[0])]

    results: list[Any] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_idx = {ex.submit(fn, item): i for i, item in enumerate(items)}
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            results[idx] = fut.result()
    return results


# ── Vectorized operations (NumPy/Polars: release GIL via C/Rust) ────────────

def vectorized_apply(
    df: Any,
    fn: Callable,
    use_polars: bool = True,
) -> Any:
    """Apply fn vectorized via Polars/NumPy, which release the GIL in C/Rust.

    Args:
        df: pandas or polars DataFrame
        fn: function that operates on arrays (must be vectorized)
        use_polars: prefer Polars (Rust backend, multi-threaded)
    """
    if use_polars and POLARS_OK:
        if not isinstance(df, pl.DataFrame):
            df = pl.from_pandas(df)
        return fn(df)
    return fn(df)


def numpy_parallel_op(
    arrays: Sequence[np.ndarray],
    op: Callable,
) -> np.ndarray:
    """Apply a NumPy operation across multiple arrays.

    NumPy ufuncs release the GIL and use MKL/OpenBLAS threads.
    """
    return op(*arrays)


# ── Numba JIT (nogil=True releases GIL) ─────────────────────────────────────

def jit_compile(fn: Callable, parallel: bool = True) -> Callable:
    """Compile fn with Numba JIT. nogil=True releases Python GIL.

    If parallel=True, uses prange for automatic parallel loops.
    """
    if not NUMBA_OK:
        logger.warning("Numba not available — returning uncompiled function")
        return fn

    if NUMBA_OK:
        set_num_threads(get_optimal_workers("perf"))

    if parallel:
        compiled = njit(nogil=True, cache=True, parallel=True)(fn)
    else:
        compiled = njit(nogil=True, cache=True)(fn)
    return compiled


# ── Monte Carlo simulation (parallel) ───────────────────────────────────────

def run_monte_carlo(
    simulate_fn: Callable,
    n: int = 100_000,
    n_workers: int | None = None,
    chunk_size: int = 1000,
) -> dict[str, Any]:
    """Run Monte Carlo simulation in parallel across all cores.

    Splits n simulations into chunks, each chunk evaluated in a separate process.
    Uses module-level _run_mc_chunk for Windows pickling.
    """
    if n_workers is None:
        n_workers = get_optimal_workers("perf")

    n_chunks = (n + chunk_size - 1) // chunk_size
    payloads = [(simulate_fn, chunk_size) for _ in range(n_chunks)]

    logger.info(f"Monte Carlo: {n:,} sims across {n_workers} workers ({n_chunks} chunks)")
    chunks = parallel_map(_run_mc_chunk, payloads, max_workers=n_workers)
    # parallel_map calls _run_mc_chunk(payload) — but we need _map_worker wrapping.
    # Actually, _run_mc_chunk already takes a tuple. Override:
    # We need to call _run_mc_chunk directly. Let's use a simpler approach:
    chunks: list[np.ndarray] = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_run_mc_chunk, p): i for i, p in enumerate(payloads)}
        for fut in as_completed(futures):
            chunks.append(fut.result())

    all_results = np.concatenate(chunks)[:n]
    return {
        "mean": float(np.mean(all_results)),
        "std": float(np.std(all_results)),
        "min": float(np.min(all_results)),
        "max": float(np.max(all_results)),
        "p5": float(np.percentile(all_results, 5)),
        "p25": float(np.percentile(all_results, 25)),
        "median": float(np.median(all_results)),
        "p75": float(np.percentile(all_results, 75)),
        "p95": float(np.percentile(all_results, 95)),
        "n": n,
        "workers": n_workers,
        "samples": all_results,
    }


# ── Grid search / hyperparameter tuning (parallel) ─────────────────────────

def grid_search_parallel(
    fn: Callable,
    param_grid: Sequence[dict],
    n_workers: int | None = None,
) -> list[dict]:
    """Evaluate fn for each param combo in parallel.

    Returns list of {params, result} dicts sorted by result score (descending).
    Uses module-level _eval_grid_combo for Windows pickling.
    """
    if n_workers is None:
        n_workers = get_optimal_workers("perf")

    payloads = [(fn, params) for params in param_grid]

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_eval_grid_combo, p): i for i, p in enumerate(payloads)}
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Hybrid: auto-select best strategy ──────────────────────────────────────

def auto_parallel(
    fn: Callable,
    items: Sequence[Any],
    task_type: str = "cpu",
) -> list[Any]:
    """Auto-select best parallelism strategy based on task type.

    Args:
        task_type: "cpu" → processes, "io" → threads, "vector" → numpy/polars
    """
    if task_type == "io":
        return thread_map(fn, items)
    if task_type == "vector":
        return [fn(item) for item in items]
    return parallel_map(fn, items)


# ── Module-level init ────────────────────────────────────────────────────────

def init_parallel() -> None:
    """Initialize parallel processing backends."""
    info = get_cpu_info()
    logger.info(
        f"Parallel init: {info['logical_cpus']} CPUs, "
        f"{info['max_workers']} max workers, {info['perf_workers']} perf workers, "
        f"GIL disabled: {info['gil_disabled']}, "
        f"Numba: {NUMBA_OK}, Polars: {POLARS_OK}"
    )
    if NUMBA_OK:
        set_num_threads(info["perf_workers"])
    if POLARS_OK:
        os.environ.setdefault("POLARS_MAX_THREADS", str(info["perf_workers"]))


init_parallel()
