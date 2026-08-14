"""
Elite Autonomous Quantum Trading System - Parallel Processing Framework
High-performance parallel processing for brain modules.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from typing import Any, TypeVar

import numpy as np
import pandas as pd

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False

try:
    import importlib.util
    DASK_AVAILABLE = importlib.util.find_spec('dask') is not None
    if DASK_AVAILABLE:
        from dask import compute, delayed
        from dask.distributed import Client, LocalCluster
except ImportError:
    DASK_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False


logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class BackendType(Enum):
    """Parallel processing backends."""
    THREADING = "threading"
    MULTIPROCESSING = "multiprocessing"
    RAY = "ray"
    DASK = "dask"
    JOBLIB = "joblib"
    ASYNCIO = "asyncio"


@dataclass
class ParallelConfig:
    """Configuration for parallel processing."""
    backend: BackendType = BackendType.THREADING
    max_workers: int = field(default_factory=lambda: min(32, (os.cpu_count() or 4) * 2))
    chunk_size: int = 100
    timeout: float = 300.0
    use_gpu: bool = False
    ray_address: str | None = None
    dask_scheduler: str | None = None


@dataclass
class TaskResult:
    """Result of a parallel task."""
    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    execution_time: float = 0.0
    worker_id: int | None = None


class ParallelProcessor:
    """
    High-performance parallel processing engine.
    Supports multiple backends for CPU/GPU parallelism.
    """
    
    def __init__(self, config: ParallelConfig | None = None):
        self.config = config or ParallelConfig()
        self.executor: concurrent.futures.Executor | None = None
        self.ray_client = None
        self.dask_client = None
        self.task_count = 0
        self.total_execution_time = 0.0
        
        logger.info(f"ParallelProcessor initialized with {self.config.backend.value} backend")
    
    async def initialize(self):
        """Initialize the parallel backend."""
        if self.config.backend == BackendType.RAY and RAY_AVAILABLE:
            await self._init_ray()
        elif self.config.backend == BackendType.DASK and DASK_AVAILABLE:
            await self._init_dask()
        elif self.config.backend == BackendType.MULTIPROCESSING:
            self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.config.max_workers)
        elif self.config.backend == BackendType.THREADING:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_workers)
        elif self.config.backend == BackendType.JOBLIB and JOBLIB_AVAILABLE:
            pass  # joblib uses context managers
        
        logger.info(f"Parallel backend {self.config.backend.value} initialized")
    
    async def _init_ray(self):
        """Initialize Ray cluster."""
        if not ray.is_initialized():
            if self.config.ray_address:
                ray.init(address=self.config.ray_address, ignore_reinit_error=True)
            else:
                ray.init(num_cpus=self.config.max_workers, ignore_reinit_error=True)
        self.ray_client = ray
        logger.info(f"Ray initialized with {ray.available_resources()}")
    
    async def _init_dask(self):
        """Initialize Dask cluster."""
        if self.config.dask_scheduler:
            self.dask_client = Client(self.config.dask_scheduler)
        else:
            cluster = LocalCluster(n_workers=self.config.max_workers, threads_per_worker=2)
            self.dask_client = Client(cluster)
        logger.info(f"Dask initialized: {self.dask_client}")
    
    async def shutdown(self):
        """Shutdown the parallel backend."""
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None
        
        if self.ray_client and ray.is_initialized():
            ray.shutdown()
            self.ray_client = None
        
        if self.dask_client:
            self.dask_client.close()
            self.dask_client = None
        
        logger.info("Parallel backend shutdown complete")
    
    def map(self, func: Callable[[T], R], items: list[T], **kwargs) -> list[R]:
            """Map function over items in parallel."""
            start_time = time.time()
        
            if self.config.backend == BackendType.RAY and RAY_AVAILABLE:
                return self._map_ray(func, items)
            elif self.config.backend == BackendType.DASK and DASK_AVAILABLE:
                return self._map_dask(func, items)
            elif self.config.backend == BackendType.JOBLIB and JOBLIB_AVAILABLE:
                return self._map_joblib(func, items)
            elif self.config.backend == BackendType.MULTIPROCESSING or self.config.backend == BackendType.THREADING:
                return self._map_executor(func, items, start_time)
            else:
                # Sequential fallback
                return [func(item) for item in items]
    
    async def amap(self, func: Callable[[T], R], items: list[T]) -> list[R]:
        """Async map function over items."""
        if self.config.backend == BackendType.ASYNCIO:
            return await self._amap_asyncio(func, items)
        else:
            # Run in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, partial(self.map, func, items))
    
    def _map_executor(self, func: Callable[[T], R], items: list[T], start_time: float) -> list[R]:
            """Map using ThreadPoolExecutor or ProcessPoolExecutor."""
            if not self.executor:
                raise RuntimeError("Executor not initialized")
        
            futures = [self.executor.submit(func, item) for item in items]
            results = [f.result(timeout=self.config.timeout) for f in futures]
        
            self.task_count += len(items)
            self.total_execution_time += time.time() - start_time
        
            return results
    
    def _map_ray(self, func: Callable[[T], R], items: list[T]) -> list[R]:
        """Map using Ray."""
        @ray.remote
        def ray_func(item):
            return func(item)
        
        futures = [ray_func.remote(item) for item in items]
        results = ray.get(futures, timeout=self.config.timeout)
        
        self.task_count += len(items)
        return results
    
    def _map_dask(self, func: Callable[[T], R], items: list[T]) -> list[R]:
        """Map using Dask."""
        delayed_func = delayed(func)
        tasks = [delayed_func(item) for item in items]
        results = compute(*tasks, scheduler='threads' if self.config.backend == BackendType.THREADING else 'processes')
        
        self.task_count += len(items)
        return list(results)
    
    def _map_joblib(self, func: Callable[[T], R], items: list[T]) -> list[R]:
        """Map using joblib."""
        with joblib.parallel_backend('threading' if self.config.backend == BackendType.THREADING else 'multiprocessing', n_jobs=self.config.max_workers):
            results = joblib.Parallel()(joblib.delayed(func)(item) for item in items)
        
        self.task_count += len(items)
        return results
    
    async def _amap_asyncio(self, func: Callable[[T], R], items: list[T]) -> list[R]:
        """Map using asyncio for I/O bound tasks."""
        semaphore = asyncio.Semaphore(self.config.max_workers)
        
        async def bounded_func(item):
            async with semaphore:
                if asyncio.iscoroutinefunction(func):
                    return await func(item)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, func, item)
        
        tasks = [bounded_func(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {i} failed: {result}")
                final_results.append(None)
            else:
                final_results.append(result)
        
        self.task_count += len(items)
        return final_results
    
    def parallel_apply(self, df: pd.DataFrame, func: Callable, axis: int = 1, **kwargs) -> pd.DataFrame:
        """Apply function to DataFrame rows/columns in parallel."""
        if self.config.backend == BackendType.DASK and DASK_AVAILABLE:
            import dask.dataframe as dd
            ddf = dd.from_pandas(df, npartitions=self.config.max_workers)
            result = ddf.map_partitions(lambda partition: partition.apply(func, axis=axis, **kwargs)).compute()
            return result
        else:
            # Split DataFrame and process chunks
            chunks = np.array_split(df, self.config.max_workers)
            results = self.map(lambda chunk: chunk.apply(func, axis=axis, **kwargs), chunks)
            return pd.concat(results)
    
    def parallel_groupby_apply(self, df: pd.DataFrame, groupby_col: str, func: Callable) -> pd.DataFrame:
        """Apply function to groupby groups in parallel."""
        groups = [group for _, group in df.groupby(groupby_col)]
        results = self.map(func, groups)
        return pd.concat(results)
    
    def get_stats(self) -> dict[str, Any]:
        """Get processor statistics."""
        return {
            "backend": self.config.backend.value,
            "max_workers": self.config.max_workers,
            "tasks_completed": self.task_count,
            "total_execution_time": self.total_execution_time,
            "avg_task_time": self.total_execution_time / self.task_count if self.task_count > 0 else 0,
        }


class ParallelBrainMixin:
    """
    Mixin to add parallel processing capabilities to brain modules.
    """
    
    def __init__(self):
        self.parallel_processor: ParallelProcessor | None = None
        self.parallel_config = ParallelConfig()
    
    async def init_parallel(self, config: ParallelConfig | None = None):
        """Initialize parallel processing."""
        if config:
            self.parallel_config = config
        
        self.parallel_processor = ParallelProcessor(self.parallel_config)
        await self.parallel_processor.initialize()
        logger.info(f"Parallel processing initialized for {self.__class__.__name__}")
    
    async def shutdown_parallel(self):
        """Shutdown parallel processing."""
        if self.parallel_processor:
            await self.parallel_processor.shutdown()
            self.parallel_processor = None
    
    def parallel_map(self, func: Callable, items: list[Any]) -> list[Any]:
        """Map function over items using parallel processor."""
        if not self.parallel_processor:
            return [func(item) for item in items]
        return self.parallel_processor.map(func, items)
    
    async def aparallel_map(self, func: Callable, items: list[Any]) -> list[Any]:
        """Async map function over items."""
        if not self.parallel_processor:
            return [func(item) for item in items]
        return await self.parallel_processor.amap(func, items)
    
    def parallel_dataframe_apply(self, df: pd.DataFrame, func: Callable, axis: int = 1) -> pd.DataFrame:
        """Apply function to DataFrame in parallel."""
        if not self.parallel_processor:
            return df.apply(func, axis=axis)
        return self.parallel_processor.parallel_apply(df, func, axis)
    
    def parallel_groupby(self, df: pd.DataFrame, groupby_col: str, func: Callable) -> pd.DataFrame:
        """Apply function to groupby groups in parallel."""
        if not self.parallel_processor:
            return df.groupby(groupby_col).apply(func)
        return self.parallel_processor.parallel_groupby_apply(df, groupby_col, func)
    
    def get_parallel_stats(self) -> dict[str, Any]:
        """Get parallel processing statistics."""
        if self.parallel_processor:
            return self.parallel_processor.get_stats()
        return {}


# Global parallel processor instance
parallel_processor = ParallelProcessor()


async def get_parallel_processor(config: ParallelConfig | None = None) -> ParallelProcessor:
    """Get or create global parallel processor."""
    global parallel_processor
    if config and parallel_processor.config != config:
        await parallel_processor.shutdown()
        parallel_processor = ParallelProcessor(config)
        await parallel_processor.initialize()
    elif not parallel_processor.executor and parallel_processor.config.backend != BackendType.ASYNCIO:
        await parallel_processor.initialize()
    return parallel_processor