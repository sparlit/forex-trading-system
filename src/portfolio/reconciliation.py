"""
Position Reconciliation Job
============================

Provides periodic position reconciliation between local state and broker state.
Ensures positions are in sync and detects discrepancies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from loguru import logger

from src.data.models import Position
from src.execution.brokers import (
    CCXTBrokerAdapter,
    CTraderAdapter,
    IBKRAdapter,
    MT5BrokerAdapter,
)
from src.execution.order_manager import BrokerType
from src.execution.position_manager import PositionManager


@dataclass
class ReconciliationConfig:
    """Configuration for position reconciliation."""
    # Schedule
    interval_seconds: int = 60  # Run every 60 seconds
    
    # Tolerance for position differences
    volume_tolerance: Decimal = Decimal("0.01")  # 1% volume tolerance
    price_tolerance: Decimal = Decimal("0.0001")  # Price tolerance
    
    # Actions on mismatch
    auto_correct: bool = False  # Whether to auto-correct mismatches
    alert_on_mismatch: bool = True  # Send alert on mismatch
    
    # Brokers to reconcile
    brokers: list[BrokerType] = field(default_factory=lambda: [
        BrokerType.MT5,
        BrokerType.CCXT,
    ])
    
    # Retry on broker errors
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class PositionMismatch:
    """Represents a position mismatch between local and broker."""
    symbol: str
    broker: BrokerType
    local_position: Position | None
    broker_position: Position | None
    volume_diff: Decimal
    price_diff: Decimal
    mismatch_type: str  # "missing_local", "missing_broker", "volume", "price", "direction"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    run_id: str
    start_time: datetime
    end_time: datetime
    brokers_checked: list[BrokerType]
    total_local_positions: int
    total_broker_positions: int
    mismatches: list[PositionMismatch]
    errors: list[str]
    success: bool
    
    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)


class PositionReconciler:
    """
    Reconciles local positions with broker positions.
    
    Features:
    - Periodic reconciliation on configurable interval
    - Multi-broker support (MT5, CCXT, cTrader, IBKR)
    - Configurable tolerance for volume/price differences
    - Alerting on mismatches
    - Optional auto-correction
    - Detailed mismatch reporting
    """
    
    def __init__(
        self,
        position_manager: PositionManager,
        config: ReconciliationConfig | None = None,
    ):
        self.position_manager = position_manager
        self.config = config or ReconciliationConfig()
        
        self._brokers: dict[BrokerType, Any] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_result: ReconciliationResult | None = None
        
        # Stats
        self._runs_total = 0
        self._mismatches_total = 0
        self._errors_total = 0
    
    async def initialize(self) -> None:
        """Initialize broker connections."""
        for broker_type in self.config.brokers:
            try:
                broker = await self._create_broker(broker_type)
                if broker:
                    await broker.connect()
                    self._brokers[broker_type] = broker
                    logger.info(f"Reconciler connected to {broker_type.value}")
            except Exception as e:
                logger.error(f"Failed to connect to {broker_type.value}: {e}")
    
    async def _create_broker(self, broker_type: BrokerType) -> Any:
        """Create broker adapter instance."""
        if broker_type == BrokerType.MT5:
            return MT5BrokerAdapter()
        elif broker_type == BrokerType.CCXT:
            return CCXTBrokerAdapter()
        elif broker_type == BrokerType.CTRADER:
            return CTraderAdapter()
        elif broker_type == BrokerType.IBKR:
            return IBKRAdapter()
        return None
    
    async def start(self) -> None:
        """Start periodic reconciliation."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Position reconciler started (interval: {self.config.interval_seconds}s)")
    
    async def stop(self) -> None:
        """Stop periodic reconciliation."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                raise NotImplementedError("Not implemented")
        
        # Close broker connections
        for broker in self._brokers.values():
            try:
                await broker.disconnect()
            except Exception as e:
                logger.error(f"Exception occurred: {e}")
        
        logger.info("Position reconciler stopped")
    
    async def _run_loop(self) -> None:
        """Main reconciliation loop."""
        while self._running:
            try:
                await self.reconcile()
            except Exception as e:
                logger.error(f"Reconciliation loop error: {e}")
            
            try:
                await asyncio.sleep(self.config.interval_seconds)
            except asyncio.CancelledError:
                break
    
    async def reconcile(self) -> ReconciliationResult:
        """
        Run one reconciliation cycle.
        
        Returns:
            ReconciliationResult with details
        """
        run_id = f"recon_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now(UTC)
        
        logger.info(f"Starting reconciliation run: {run_id}")
        
        all_mismatches = []
        all_errors = []
        brokers_checked = []
        
        # Get local positions
        local_positions = await self.position_manager.get_all_positions()
        local_by_symbol = {p.symbol: p for p in local_positions}
        
        for broker_type in self.config.brokers:
            try:
                broker = self._brokers.get(broker_type)
                if not broker:
                    logger.warning(f"Broker {broker_type.value} not initialized, skipping")
                    continue
                
                brokers_checked.append(broker_type)
                
                # Get broker positions with retry
                broker_positions = await self._get_broker_positions_with_retry(broker, broker_type)
                broker_by_symbol = {p.symbol: p for p in broker_positions}
                
                # Compare positions
                mismatches = self._compare_positions(
                    local_by_symbol,
                    broker_by_symbol,
                    broker_type,
                )
                
                all_mismatches.extend(mismatches)
                
            except Exception as e:
                error_msg = f"Broker {broker_type.value} reconciliation failed: {e}"
                logger.error(error_msg)
                all_errors.append(error_msg)
        
        end_time = datetime.now(UTC)
        
        # Get broker positions for total count
        broker_positions_list = []
        for bt in brokers_checked:
            positions = await self._get_broker_positions_with_retry(self._brokers.get(bt), bt)
            broker_positions_list.append(positions)
        
        result = ReconciliationResult(
            run_id=run_id,
            start_time=start_time,
            end_time=end_time,
            brokers_checked=brokers_checked,
            total_local_positions=len(local_positions),
            total_broker_positions=sum(len(positions) for positions in broker_positions_list),
            mismatches=all_mismatches,
            errors=all_errors,
            success=len(all_errors) == 0,
        )
        
        self._last_result = result
        self._runs_total += 1
        self._mismatches_total += len(all_mismatches)
        self._errors_total += len(all_errors)
        
        # Log summary
        if all_mismatches:
            logger.warning(f"Reconciliation {run_id}: {len(all_mismatches)} mismatches found")
            for mismatch in all_mismatches:
                logger.warning(
                    f"  {mismatch.symbol} [{mismatch.broker.value}]: "
                    f"{mismatch.mismatch_type} - vol_diff={mismatch.volume_diff}, "
                    f"price_diff={mismatch.price_diff}"
                )
        else:
            logger.info(f"Reconciliation {run_id}: No mismatches found")
        
        # Alert on mismatches
        if all_mismatches and self.config.alert_on_mismatch:
            await self._alert_mismatches(all_mismatches)
        
        return result
    
    async def _get_broker_positions_with_retry(
        self,
        broker: Any,
        broker_type: BrokerType,
    ) -> list[Position]:
        """Get positions with retry logic."""
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                positions = await broker.get_positions()
                return positions
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                    logger.warning(f"Retry {attempt + 1}/{self.config.max_retries} for {broker_type.value}: {e}")
        
        raise last_error
    
    def _compare_positions(
        self,
        local_positions: dict[str, Position],
        broker_positions: dict[str, Position],
        broker_type: BrokerType,
    ) -> list[PositionMismatch]:
        """Compare local and broker positions."""
        mismatches = []
        
        all_symbols = set(local_positions.keys()) | set(broker_positions.keys())
        
        for symbol in all_symbols:
            local = local_positions.get(symbol)
            broker = broker_positions.get(symbol)
            
            if local is None and broker is not None:
                # Position exists at broker but not locally
                mismatches.append(PositionMismatch(
                    symbol=symbol,
                    broker=broker_type,
                    local_position=None,
                    broker_position=broker,
                    volume_diff=broker.volume,
                    price_diff=Decimal(0),
                    mismatch_type="missing_local",
                ))
            
            elif local is not None and broker is None:
                # Position exists locally but not at broker
                mismatches.append(PositionMismatch(
                    symbol=symbol,
                    broker=broker_type,
                    local_position=local,
                    broker_position=None,
                    volume_diff=local.volume,
                    price_diff=Decimal(0),
                    mismatch_type="missing_broker",
                ))
            
            else:
                # Both exist, check for differences
                volume_diff = abs(local.volume - broker.volume)
                price_diff = abs(local.entry_price - broker.entry_price)
                direction_match = local.direction == broker.direction
                
                if volume_diff > self.config.volume_tolerance:
                    mismatches.append(PositionMismatch(
                        symbol=symbol,
                        broker=broker_type,
                        local_position=local,
                        broker_position=broker,
                        volume_diff=volume_diff,
                        price_diff=price_diff,
                        mismatch_type="volume",
                    ))
                
                if price_diff > self.config.price_tolerance:
                    mismatches.append(PositionMismatch(
                        symbol=symbol,
                        broker=broker_type,
                        local_position=local,
                        broker_position=broker,
                        volume_diff=volume_diff,
                        price_diff=price_diff,
                        mismatch_type="price",
                    ))
                
                if not direction_match:
                    mismatches.append(PositionMismatch(
                        symbol=symbol,
                        broker=broker_type,
                        local_position=local,
                        broker_position=broker,
                        volume_diff=volume_diff,
                        price_diff=price_diff,
                        mismatch_type="direction",
                    ))
        
        return mismatches
    
    async def _alert_mismatches(self, mismatches: list[PositionMismatch]) -> None:
        """Send alert for mismatches."""
        # In production, integrate with alerting system
        summary = {
            "total_mismatches": len(mismatches),
            "by_type": {},
            "by_broker": {},
        }
        
        for m in mismatches:
            summary["by_type"][m.mismatch_type] = summary["by_type"].get(m.mismatch_type, 0) + 1
            summary["by_broker"][m.broker.value] = summary["by_broker"].get(m.broker.value, 0) + 1
        
        logger.warning(f"Position reconciliation alert: {summary}")
        
        # Could integrate with AlertManager here
        # from src.infra.monitoring import alert_error
        # await alert_error("Position Mismatch", f"Found {len(mismatches)} position mismatches", metadata=summary)
    
    async def auto_correct_mismatches(self, mismatches: list[PositionMismatch]) -> list[str]:
        """
        Attempt to auto-correct mismatches.
        
        Returns:
            List of correction actions taken
        """
        actions = []
        
        for mismatch in mismatches:
            try:
                if mismatch.mismatch_type == "missing_local" and mismatch.broker_position:
                    # Add missing local position
                    await self.position_manager.add_position(mismatch.broker_position)
                    actions.append(f"Added local position for {mismatch.symbol}")
                
                elif mismatch.mismatch_type == "missing_broker" and mismatch.local_position:
                    # Position closed at broker but still local - remove local
                    await self.position_manager.close_position(mismatch.symbol)
                    actions.append(f"Removed local position for {mismatch.symbol} (closed at broker)")
                
                elif mismatch.mismatch_type == "volume" and mismatch.local_position and mismatch.broker_position:
                    # Update local volume to match broker
                    mismatch.local_position.volume = mismatch.broker_position.volume
                    actions.append(f"Updated volume for {mismatch.symbol} to {mismatch.broker_position.volume}")
                
                elif mismatch.mismatch_type == "price" and mismatch.local_position and mismatch.broker_position:
                    # Update local entry price to match broker
                    mismatch.local_position.entry_price = mismatch.broker_position.entry_price
                    actions.append(f"Updated entry price for {mismatch.symbol} to {mismatch.broker_position.entry_price}")
                
            except Exception as e:
                logger.error(f"Auto-correction failed for {mismatch.symbol}: {e}")
                actions.append(f"FAILED: {mismatch.symbol} - {e}")
        
        return actions
    
    def get_stats(self) -> dict[str, Any]:
        """Get reconciler statistics."""
        return {
            "running": self._running,
            "runs_total": self._runs_total,
            "mismatches_total": self._mismatches_total,
            "errors_total": self._errors_total,
            "brokers_connected": list(self._brokers.keys()),
            "last_result": {
                "run_id": self._last_result.run_id,
                "start_time": self._last_result.start_time.isoformat(),
                "end_time": self._last_result.end_time.isoformat(),
                "mismatches": self._last_result.mismatch_count,
                "success": self._last_result.success,
            } if self._last_result else None,
        }
    
    async def manual_reconcile(self) -> ReconciliationResult:
        """Trigger manual reconciliation."""
        return await self.reconcile()


# Global instance
_reconciler: PositionReconciler | None = None


def get_position_reconciler() -> PositionReconciler | None:
    """Get global position reconciler."""
    return _reconciler


async def init_position_reconciler(
    position_manager: PositionManager,
    config: ReconciliationConfig | None = None,
) -> PositionReconciler:
    """Initialize global position reconciler."""
    global _reconciler
    _reconciler = PositionReconciler(position_manager, config)
    await _reconciler.initialize()
    return _reconciler


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Would need actual PositionManager
        # This is a demonstration
        
        _config = ReconciliationConfig(
            interval_seconds=30,
            volume_tolerance=Decimal("0.01"),
            brokers=[BrokerType.MT5, BrokerType.CCXT],
            alert_on_mismatch=True,
        )
        
        # reconciler = await init_position_reconciler(position_manager, config)
        # await reconciler.start()
        
        # Let it run
        # await asyncio.sleep(120)
        
        # await reconciler.stop()
        
        print("Position reconciler example - integrate with actual PositionManager")
    
    asyncio.run(example())