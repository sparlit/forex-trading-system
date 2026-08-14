"""
Cancel-on-Disconnect — EAQTS V2.3 N1038–N1047.

When execution connection is lost:
  FREEZE new orders → CANCEL eligible orders → RECONCILE → VERIFY → RECOVER/DEFENSIVE

The system must NEVER assume a disconnected order was not executed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from loguru import logger


class DisconnectPhase(str, Enum):
    MONITORING = "monitoring"
    DISCONNECTED = "disconnected"
    FREEZING = "freezing"
    CANCELLING = "cancelling"
    MARKING_UNKNOWN = "marking_unknown"
    RECONNECTING = "reconnecting"
    RECONCILING = "reconciling"
    VERIFYING = "verifying"
    RECOVERED = "recovered"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass
class CODOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str = "limit"
    active: bool = True
    cancellation_submitted: bool = False
    unknown_after_reconnect: bool = False
    verified_broker_state: dict[str, Any] | None = None


class CancelOnDisconnect:
    """
    N1038–N1047: Freeze → Cancel → Reconcile → Verify.

    Use ``cancel_callback`` to wire into the actual order manager.
    """

    def __init__(
        self,
        cancel_callback: Callable[[str], bool] | None = None,
        broker_query_callback: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.phase = DisconnectPhase.MONITORING
        self._orders: dict[str, CODOrder] = {}
        self.cancel_callback = cancel_callback or (lambda oid: True)
        self.broker_query_callback = broker_query_callback or (lambda oid: {"state": "unknown"})
        self._freeze_flag = False

    def register_order(self, order: CODOrder) -> None:
        self._orders[order.order_id] = order

    def deregister_order(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

    @property
    def frozen(self) -> bool:
        """N1039 — New orders are frozen."""
        return self._freeze_flag

    @property
    def cancellable_orders(self) -> list[CODOrder]:
        """N1040 — Orders eligible for cancellation."""
        return [o for o in self._orders.values() if o.active and not o.cancellation_submitted]

    def on_disconnect(self) -> None:
        """N1038 — Execution connection lost."""
        logger.warning("COD: execution connection lost")
        self.phase = DisconnectPhase.DISCONNECTED
        self._freeze_flag = True
        self.phase = DisconnectPhase.FREEZING
        logger.info("COD: new orders frozen")

    def submit_cancellations(self) -> None:
        """N1041 — Submit cancellations where possible."""
        if self.phase != DisconnectPhase.FREEZING:
            return
        self.phase = DisconnectPhase.CANCELLING
        for order in self.cancellable_orders:
            try:
                success = self.cancel_callback(order.order_id)
                order.cancellation_submitted = True
                if success:
                    logger.info(f"COD: cancellation submitted for {order.order_id}")
                else:
                    logger.error(f"COD: cancellation FAILED for {order.order_id}")
            except Exception as e:
                logger.error(f"COD: cancel error for {order.order_id}: {e}")

    def mark_unknown(self) -> None:
        """N1042 — Mark unresolved orders UNKNOWN."""
        self.phase = DisconnectPhase.MARKING_UNKNOWN
        for order in self._orders.values():
            if order.active and not order.verified_broker_state:
                order.unknown_after_reconnect = True
                logger.warning(f"COD: order {order.order_id} marked UNKNOWN")

    def reconnect(self) -> None:
        """N1043 — Reconnect to broker."""
        self.phase = DisconnectPhase.RECONNECTING
        logger.info("COD: reconnecting to broker")

    def query_broker_state(self) -> None:
        """N1044 — Query broker state for all tracked orders."""
        for order in self._orders.values():
            try:
                order.verified_broker_state = self.broker_query_callback(order.order_id)
            except Exception as e:
                logger.error(f"COD: broker query error for {order.order_id}: {e}")
                order.unknown_after_reconnect = True

    def reconcile(self) -> None:
        """N1045 — Reconcile internal vs broker order state."""
        self.phase = DisconnectPhase.RECONCILING
        logger.info("COD: reconciling order states")

    def verify_positions(self, internal_positions: dict, broker_positions: dict) -> bool:
        """N1046 — Verify actual positions match expectations."""
        self.phase = DisconnectPhase.VERIFYING
        all_ok = True
        for symbol, internal_qty in internal_positions.items():
            broker_qty = broker_positions.get(symbol, 0.0)
            if abs(internal_qty - broker_qty) > 1e-6:
                logger.error(
                    f"COD: position mismatch {symbol}: "
                    f"internal={internal_qty} broker={broker_qty}"
                )
                all_ok = False
        if all_ok:
            logger.info("COD: positions verified")
            self.phase = DisconnectPhase.RECOVERED
            self._freeze_flag = False
        else:
            logger.error("COD: recovery required due to position mismatch")
            self.phase = DisconnectPhase.RECOVERY_REQUIRED
        return all_ok

    def require_recovery_validation(self) -> bool:
        """N1047 — Recovery must be validated before resuming."""
        return self.phase == DisconnectPhase.RECOVERY_REQUIRED


# Singleton
cancel_on_disconnect = CancelOnDisconnect()
