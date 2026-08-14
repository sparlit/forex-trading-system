from __future__ import annotations

"""Independent Execution Verifier (V2.2 Section 87 / EAQTS-3296-3313).

Provides a deterministic validation that the internal execution state matches the
broker's reported state. Mismatches are logged and returned in a structured
result.
"""

import logging
import math
import time
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExecutionMismatch:
    field: str
    internal_value: Any
    broker_value: Any
    tolerance: float
    exceeds_tolerance: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d["exceeds_tolerance"] = self.exceeds_tolerance
        return d

@dataclass(slots=True)
class ExecutionVerificationResult:
    matches: bool
    mismatches: list[ExecutionMismatch]
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "matches": self.matches,
            "mismatches": [m.to_dict() for m in self.mismatches],
            "timestamp": self.timestamp,
        }

# ---------------------------------------------------------------------------
# Helper verification functions (pure comparison with tolerances)
# ---------------------------------------------------------------------------

def _compare_numeric(internal: float, broker: float, tolerance: float) -> bool:
    return math.isclose(internal, broker, rel_tol=0.0, abs_tol=tolerance)

def verify_order(order: dict[str, Any], broker_order: dict[str, Any]) -> bool:
    """Validate that an internal order matches the broker's representation.

    Checks ``order_id`` existence, ``state`` equality, and ``quantity`` within a
    small tolerance (default 1e-6). Returns ``True`` if all checks pass.
    """
    required_fields = ["order_id", "state", "quantity"]
    for f in required_fields:
        if f not in order:
            logger.error("Internal order missing required field %s", f)
            return False
        if f not in broker_order:
            logger.error("Broker order missing required field %s", f)
            return False

    if order["order_id"] != broker_order["order_id"]:
        logger.error("Order ID mismatch: %s vs %s", order["order_id"], broker_order["order_id"])
        return False
    if order["state"] != broker_order["state"]:
        logger.error("Order state mismatch for %s: %s vs %s", order["order_id"], order["state"], broker_order["state"])
        return False
    # Quantity tolerance of 1e-6 units (e.g., lots)
    if not _compare_numeric(float(order["quantity"]), float(broker_order["quantity"]), 1e-6):
        logger.error("Order quantity mismatch for %s: %s vs %s", order["order_id"], order["quantity"], broker_order["quantity"])
        return False
    return True

def verify_fill(fill: dict[str, Any], broker_fill: dict[str, Any]) -> bool:
    """Validate that an internal fill matches the broker's fill.

    Checks ``fill_id``, ``quantity`` and ``price`` within a small tolerance.
    """
    required = ["fill_id", "quantity", "price"]
    for f in required:
        if f not in fill or f not in broker_fill:
            logger.error("Missing fill field %s in internal or broker representation", f)
            return False
    if fill["fill_id"] != broker_fill["fill_id"]:
        logger.error("Fill ID mismatch: %s vs %s", fill["fill_id"], broker_fill["fill_id"])
        return False
    if not _compare_numeric(float(fill["quantity"]), float(broker_fill["quantity"]), 1e-6):
        logger.error("Fill quantity mismatch for %s: %s vs %s", fill["fill_id"], fill["quantity"], broker_fill["quantity"])
        return False
    if not _compare_numeric(float(fill["price"]), float(broker_fill["price"]), 1e-8):
        logger.error("Fill price mismatch for %s: %s vs %s", fill["fill_id"], fill["price"], broker_fill["price"])
        return False
    return True

def verify_position(position: dict[str, Any], broker_position: dict[str, Any]) -> bool:
    """Validate that an internal position matches the broker's position.

    Checks ``position_id``, ``size`` and ``state`` with tolerances.
    """
    required = ["position_id", "size", "state"]
    for f in required:
        if f not in position or f not in broker_position:
            logger.error("Missing position field %s in internal or broker representation", f)
            return False
    if position["position_id"] != broker_position["position_id"]:
        logger.error("Position ID mismatch: %s vs %s", position["position_id"], broker_position["position_id"])
        return False
    if not _compare_numeric(float(position["size"]), float(broker_position["size"]), 1e-6):
        logger.error("Position size mismatch for %s: %s vs %s", position["position_id"], position["size"], broker_position["size"])
        return False
    if position["state"] != broker_position["state"]:
        logger.error("Position state mismatch for %s: %s vs %s", position["position_id"], position["state"], broker_position["state"])
        return False
    return True

def verify_state(internal_state: dict[str, Any], broker_state: dict[str, Any]) -> ExecutionVerificationResult:
    """Perform a comprehensive verification between internal and broker states.

    Returns an ``ExecutionVerificationResult`` indicating overall success and a
    list of any mismatches.
    """
    mismatches: list[ExecutionMismatch] = []
    timestamp = time.time()

    # Verify orders – assume both structures contain a list keyed by "orders"
    for order in internal_state.get("orders", []):
        broker_order = next((b for b in broker_state.get("orders", []) if b.get("order_id") == order.get("order_id")), None)
        if broker_order is None:
            mismatches.append(ExecutionMismatch(
                field="order_missing",
                internal_value=order.get("order_id"),
                broker_value=None,
                tolerance=0.0,
                exceeds_tolerance=True,
            ))
            continue
        # Compare fields individually to capture detailed mismatches.
        if order.get("state") != broker_order.get("state"):
            mismatches.append(ExecutionMismatch(
                field="order_state",
                internal_value=order.get("state"),
                broker_value=broker_order.get("state"),
                tolerance=0.0,
                exceeds_tolerance=True,
            ))
        if not _compare_numeric(float(order.get("quantity", 0.0)), float(broker_order.get("quantity", 0.0)), 1e-6):
            mismatches.append(ExecutionMismatch(
                field="order_quantity",
                internal_value=order.get("quantity"),
                broker_value=broker_order.get("quantity"),
                tolerance=1e-6,
                exceeds_tolerance=True,
            ))

    # Verify fills
    for fill in internal_state.get("fills", []):
        broker_fill = next((b for b in broker_state.get("fills", []) if b.get("fill_id") == fill.get("fill_id")), None)
        if broker_fill is None:
            mismatches.append(ExecutionMismatch(
                field="fill_missing",
                internal_value=fill.get("fill_id"),
                broker_value=None,
                tolerance=0.0,
                exceeds_tolerance=True,
            ))
            continue
        if not _compare_numeric(float(fill.get("quantity", 0.0)), float(broker_fill.get("quantity", 0.0)), 1e-6):
            mismatches.append(ExecutionMismatch(
                field="fill_quantity",
                internal_value=fill.get("quantity"),
                broker_value=broker_fill.get("quantity"),
                tolerance=1e-6,
                exceeds_tolerance=True,
            ))
        if not _compare_numeric(float(fill.get("price", 0.0)), float(broker_fill.get("price", 0.0)), 1e-8):
            mismatches.append(ExecutionMismatch(
                field="fill_price",
                internal_value=fill.get("price"),
                broker_value=broker_fill.get("price"),
                tolerance=1e-8,
                exceeds_tolerance=True,
            ))

    # Verify positions
    for pos in internal_state.get("positions", []):
        broker_pos = next((b for b in broker_state.get("positions", []) if b.get("position_id") == pos.get("position_id")), None)
        if broker_pos is None:
            mismatches.append(ExecutionMismatch(
                field="position_missing",
                internal_value=pos.get("position_id"),
                broker_value=None,
                tolerance=0.0,
                exceeds_tolerance=True,
            ))
            continue
        if not _compare_numeric(float(pos.get("size", 0.0)), float(broker_pos.get("size", 0.0)), 1e-6):
            mismatches.append(ExecutionMismatch(
                field="position_size",
                internal_value=pos.get("size"),
                broker_value=broker_pos.get("size"),
                tolerance=1e-6,
                exceeds_tolerance=True,
            ))
        if pos.get("state") != broker_pos.get("state"):
            mismatches.append(ExecutionMismatch(
                field="position_state",
                internal_value=pos.get("state"),
                broker_value=broker_pos.get("state"),
                tolerance=0.0,
                exceeds_tolerance=True,
            ))

    matches = len(mismatches) == 0
    if not matches:
        logger.warning("Execution verification detected %d mismatches", len(mismatches))
    else:
        logger.info("Execution verification succeeded with no mismatches")
    return ExecutionVerificationResult(matches, mismatches, timestamp)
