"""
Broker, Exchange and Account State Machines — EAQTS V2.3 N1048–N1080.

Each state machine manages explicit trading permissions and drives
capability restrictions when the upstream system degrades.
"""

from __future__ import annotations

from enum import Enum

from loguru import logger

# ---------------------------------------------------------------------------
# Broker State Machine — N1048–N1059
# ---------------------------------------------------------------------------

class BrokerState(str, Enum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    HIGH_LATENCY = "high_latency"
    ORDER_RESTRICTED = "order_restricted"
    READ_ONLY = "read_only"
    DISCONNECTED = "disconnected"
    RECOVERING = "recovering"
    RECONCILING = "reconciling"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


# Each state maps to explicit permissions
BROKER_PERMISSIONS: dict[BrokerState, dict[str, bool]] = {
    BrokerState.CONNECTED:        {"can_trade": True,  "can_cancel": True,  "can_modify": True,  "can_read": True},
    BrokerState.DEGRADED:         {"can_trade": True,  "can_cancel": True,  "can_modify": False, "can_read": True},
    BrokerState.HIGH_LATENCY:     {"can_trade": False, "can_cancel": True,  "can_modify": False, "can_read": True},
    BrokerState.ORDER_RESTRICTED:{"can_trade": False, "can_cancel": True,  "can_modify": False, "can_read": True},
    BrokerState.READ_ONLY:        {"can_trade": False, "can_cancel": False, "can_modify": False, "can_read": True},
    BrokerState.DISCONNECTED:     {"can_trade": False, "can_cancel": False, "can_modify": False, "can_read": False},
    BrokerState.RECOVERING:       {"can_trade": False, "can_cancel": True,  "can_modify": False, "can_read": True},
    BrokerState.RECONCILING:      {"can_trade": False, "can_cancel": True,  "can_modify": False, "can_read": True},
    BrokerState.QUARANTINED:      {"can_trade": False, "can_cancel": False, "can_modify": False, "can_read": True},
    BrokerState.UNKNOWN:          {"can_trade": False, "can_cancel": False, "can_modify": False, "can_read": False},
}

BROKER_TRANSITIONS: dict[BrokerState, set[BrokerState]] = {
    BrokerState.CONNECTED: {BrokerState.DEGRADED, BrokerState.HIGH_LATENCY, BrokerState.ORDER_RESTRICTED, BrokerState.READ_ONLY, BrokerState.DISCONNECTED, BrokerState.UNKNOWN},
    BrokerState.DEGRADED: {BrokerState.CONNECTED, BrokerState.HIGH_LATENCY, BrokerState.READ_ONLY, BrokerState.DISCONNECTED},
    BrokerState.HIGH_LATENCY: {BrokerState.CONNECTED, BrokerState.DEGRADED, BrokerState.DISCONNECTED},
    BrokerState.ORDER_RESTRICTED: {BrokerState.CONNECTED, BrokerState.READ_ONLY, BrokerState.DISCONNECTED},
    BrokerState.READ_ONLY: {BrokerState.DISCONNECTED, BrokerState.RECOVERING},
    BrokerState.DISCONNECTED: {BrokerState.RECOVERING, BrokerState.UNKNOWN},
    BrokerState.RECOVERING: {BrokerState.RECONCILING, BrokerState.CONNECTED, BrokerState.UNKNOWN},
    BrokerState.RECONCILING: {BrokerState.CONNECTED, BrokerState.UNKNOWN},
    BrokerState.QUARANTINED: {BrokerState.RECOVERING},
    BrokerState.UNKNOWN: {BrokerState.RECOVERING, BrokerState.DISCONNECTED},
}


class BrokerStateMachine:
    """Manages broker connection state and maps states to trading permissions."""

    def __init__(self) -> None:
        self.state = BrokerState.UNKNOWN
        self.history: list[tuple[BrokerState, BrokerState]] = []

    def transition(self, new_state: BrokerState) -> bool:
        allowed = BROKER_TRANSITIONS.get(self.state, set())
        if new_state not in allowed and new_state != self.state:
            logger.warning(f"Broker transition {self.state.value} → {new_state.value} not allowed")
            return False
        old = self.state
        self.state = new_state
        self.history.append((old, new_state))
        logger.info(f"Broker state: {old.value} → {new_state.value}")
        return True

    @property
    def permissions(self) -> dict[str, bool]:
        return BROKER_PERMISSIONS.get(self.state, BROKER_PERMISSIONS[BrokerState.UNKNOWN])

    @property
    def can_trade(self) -> bool:
        return self.permissions.get("can_trade", False)

    @property
    def can_cancel(self) -> bool:
        return self.permissions.get("can_cancel", False)

    @property
    def can_modify(self) -> bool:
        return self.permissions.get("can_modify", False)

    @property
    def can_read(self) -> bool:
        return self.permissions.get("can_read", False)


# ---------------------------------------------------------------------------
# Exchange State Machine — N1060–N1070
# ---------------------------------------------------------------------------

class ExchangeState(str, Enum):
    OPEN = "open"
    PRE_OPEN = "pre_open"
    AUCTION = "auction"
    HALTED = "halted"
    LIMITED = "limited"
    CLOSED = "closed"
    MAINTENANCE = "maintenance"
    REOPENING = "reopening"
    UNKNOWN = "unknown"


EXCHANGE_PERMISSIONS: dict[ExchangeState, dict[str, bool]] = {
    ExchangeState.OPEN:        {"can_trade": True,  "can_market_order": True,  "can_limit_order": True},
    ExchangeState.PRE_OPEN:    {"can_trade": False, "can_market_order": False, "can_limit_order": True},
    ExchangeState.AUCTION:     {"can_trade": True,  "can_market_order": False, "can_limit_order": True},
    ExchangeState.HALTED:      {"can_trade": False, "can_market_order": False, "can_limit_order": False},
    ExchangeState.LIMITED:     {"can_trade": True,  "can_market_order": False, "can_limit_order": True},
    ExchangeState.CLOSED:      {"can_trade": False, "can_market_order": False, "can_limit_order": False},
    ExchangeState.MAINTENANCE: {"can_trade": False, "can_market_order": False, "can_limit_order": False},
    ExchangeState.REOPENING:   {"can_trade": False, "can_market_order": False, "can_limit_order": True},
    ExchangeState.UNKNOWN:     {"can_trade": False, "can_market_order": False, "can_limit_order": False},
}

EXCHANGE_TRANSITIONS: dict[ExchangeState, set[ExchangeState]] = {
    ExchangeState.OPEN: {ExchangeState.HALTED, ExchangeState.LIMITED, ExchangeState.CLOSED, ExchangeState.Pre_OPEN if hasattr(ExchangeState, 'Pre_OPEN') else ExchangeState.PRE_OPEN, ExchangeState.MAINTENANCE, ExchangeState.UNKNOWN},
    ExchangeState.PRE_OPEN: {ExchangeState.OPEN, ExchangeState.AUCTION, ExchangeState.HALTED},
    ExchangeState.AUCTION: {ExchangeState.OPEN, ExchangeState.HALTED, ExchangeState.CLOSED},
    ExchangeState.HALTED: {ExchangeState.REOPENING, ExchangeState.CLOSED, ExchangeState.MAINTENANCE},
    ExchangeState.LIMITED: {ExchangeState.OPEN, ExchangeState.HALTED, ExchangeState.CLOSED},
    ExchangeState.CLOSED: {ExchangeState.PRE_OPEN, ExchangeState.MAINTENANCE},
    ExchangeState.MAINTENANCE: {ExchangeState.CLOSED, ExchangeState.REOPENING},
    ExchangeState.REOPENING: {ExchangeState.OPEN, ExchangeState.HALTED},
    ExchangeState.UNKNOWN: {ExchangeState.CLOSED, ExchangeState.OPEN},
}

# Fix the OPEN transition set (clean up the conditional)
EXCHANGE_TRANSITIONS[ExchangeState.OPEN] = {
    ExchangeState.HALTED, ExchangeState.LIMITED, ExchangeState.CLOSED,
    ExchangeState.PRE_OPEN, ExchangeState.MAINTENANCE, ExchangeState.UNKNOWN,
}


class ExchangeStateMachine:
    """Tracks whether the exchange/market is accepting orders."""

    def __init__(self) -> None:
        self.state = ExchangeState.UNKNOWN
        self.history: list[tuple[ExchangeState, ExchangeState]] = []

    def transition(self, new_state: ExchangeState) -> bool:
        allowed = EXCHANGE_TRANSITIONS.get(self.state, set())
        if new_state not in allowed and new_state != self.state:
            logger.warning(f"Exchange transition {self.state.value} → {new_state.value} not allowed")
            return False
        old = self.state
        self.state = new_state
        self.history.append((old, new_state))
        logger.info(f"Exchange state: {old.value} → {new_state.value}")
        return True

    @property
    def permissions(self) -> dict[str, bool]:
        return EXCHANGE_PERMISSIONS.get(self.state, EXCHANGE_PERMISSIONS[ExchangeState.UNKNOWN])

    @property
    def can_trade(self) -> bool:
        return self.permissions.get("can_trade", False)

    @property
    def can_market_order(self) -> bool:
        return self.permissions.get("can_market_order", False)

    @property
    def can_limit_order(self) -> bool:
        return self.permissions.get("can_limit_order", False)


# ---------------------------------------------------------------------------
# Account State Machine — N1071–N1080
# ---------------------------------------------------------------------------

class AccountState(str, Enum):
    NORMAL = "normal"
    MARGIN_WARNING = "margin_warning"
    MARGIN_RESTRICTED = "margin_restricted"
    MARGIN_CRITICAL = "margin_critical"
    TRADING_RESTRICTED = "trading_restricted"
    LIQUIDATION_RISK = "liquidation_risk"
    HALTED = "halted"
    RECOVERY = "recovery"
    UNKNOWN = "unknown"


ACCOUNT_PERMISSIONS: dict[AccountState, dict[str, bool]] = {
    AccountState.NORMAL:            {"can_open": True,  "can_close": True,  "can_modify": True},
    AccountState.MARGIN_WARNING:     {"can_open": True,  "can_close": True,  "can_modify": True},
    AccountState.MARGIN_RESTRICTED: {"can_open": False, "can_close": True,  "can_modify": False},
    AccountState.MARGIN_CRITICAL:   {"can_open": False, "can_close": True,  "can_modify": False},
    AccountState.TRADING_RESTRICTED:{"can_open": False, "can_close": True,  "can_modify": False},
    AccountState.LIQUIDATION_RISK:  {"can_open": False, "can_close": True,  "can_modify": False},
    AccountState.HALTED:            {"can_open": False, "can_close": False,"can_modify": False},
    AccountState.RECOVERY:          {"can_open": False, "can_close": True,  "can_modify": False},
    AccountState.UNKNOWN:           {"can_open": False, "can_close": False,"can_modify": False},
}

ACCOUNT_TRANSITIONS: dict[AccountState, set[AccountState]] = {
    AccountState.NORMAL: {AccountState.MARGIN_WARNING, AccountState.TRADING_RESTRICTED, AccountState.HALTED, AccountState.UNKNOWN},
    AccountState.MARGIN_WARNING: {AccountState.NORMAL, AccountState.MARGIN_RESTRICTED, AccountState.MARGIN_CRITICAL},
    AccountState.MARGIN_RESTRICTED: {AccountState.MARGIN_CRITICAL, AccountState.NORMAL, AccountState.HALTED},
    AccountState.MARGIN_CRITICAL: {AccountState.LIQUIDATION_RISK, AccountState.HALTED, AccountState.MARGIN_RESTRICTED},
    AccountState.TRADING_RESTRICTED: {AccountState.NORMAL, AccountState.HALTED},
    AccountState.LIQUIDATION_RISK: {AccountState.HALTED, AccountState.MARGIN_CRITICAL},
    AccountState.HALTED: {AccountState.RECOVERY, AccountState.UNKNOWN},
    AccountState.RECOVERY: {AccountState.NORMAL, AccountState.MARGIN_WARNING, AccountState.HALTED},
    AccountState.UNKNOWN: {AccountState.RECOVERY, AccountState.HALTED},
}


class AccountStateMachine:
    """Tracks account-level margin, liquidation and trading-permission state."""

    def __init__(self) -> None:
        self.state = AccountState.UNKNOWN
        self.history: list[tuple[AccountState, AccountState]] = []

    def transition(self, new_state: AccountState) -> bool:
        allowed = ACCOUNT_TRANSITIONS.get(self.state, set())
        if new_state not in allowed and new_state != self.state:
            logger.warning(f"Account transition {self.state.value} → {new_state.value} not allowed")
            return False
        old = self.state
        self.state = new_state
        self.history.append((old, new_state))
        logger.info(f"Account state: {old.value} → {new_state.value}")
        return True

    @property
    def permissions(self) -> dict[str, bool]:
        return ACCOUNT_PERMISSIONS.get(self.state, ACCOUNT_PERMISSIONS[AccountState.UNKNOWN])

    @property
    def can_open(self) -> bool:
        return self.permissions.get("can_open", False)

    @property
    def can_close(self) -> bool:
        return self.permissions.get("can_close", False)

    @property
    def can_modify(self) -> bool:
        return self.permissions.get("can_modify", False)


# Singletons
broker_state_machine = BrokerStateMachine()
exchange_state_machine = ExchangeStateMachine()
account_state_machine = AccountStateMachine()
