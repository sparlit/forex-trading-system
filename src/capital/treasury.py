from __future__ import annotations

"""Multi-Currency Treasury Engine – EAQTS V2.3 (Section 57 / EAQTS-3050-3069)
Tracks multi-currency cash positions, FX translation risk, and treasury status.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import ClassVar

from loguru import logger


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CHF = "CHF"
    AUD = "AUD"
    CAD = "CAD"
    NZD = "NZD"
    CNY = "CNY"
    HKD = "HKD"
    SGD = "SGD"
    SEK = "SEK"
    NOK = "NOK"
    MXN = "MXN"
    ZAR = "ZAR"


class CashType(str, Enum):
    BROKER_CASH = "broker_cash"
    AVAILABLE_CASH = "available_cash"
    RESERVED_CASH = "reserved_cash"
    SETTLEMENT_CASH = "settlement_cash"
    EMERGENCY_CASH = "emergency_cash"


@dataclass(slots=True)
class CurrencyConfig:
    base_currency: Currency = Currency.USD
    cash_currency: Currency = Currency.USD
    settlement_currency: Currency = Currency.USD
    margin_currency: Currency = Currency.USD
    pnl_currency: Currency = Currency.USD
    funding_currency: Currency = Currency.USD


@dataclass(slots=True)
class CashPosition:
    currency: Currency
    cash_type: CashType
    amount: Decimal = Decimal(0)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def add(self, amount: Decimal) -> None:
        self.amount += amount
        self.last_updated = datetime.now(timezone.utc)

    def subtract(self, amount: Decimal) -> bool:
        if self.amount >= amount:
            self.amount -= amount
            self.last_updated = datetime.now(timezone.utc)
            return True
        return False


@dataclass(slots=True)
class FXRate:
    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "internal"


@dataclass(slots=True)
class TreasuryState:
    currency_config: CurrencyConfig
    cash_positions: dict[str, CashPosition] = field(default_factory=dict)
    fx_rates: dict[str, FXRate] = field(default_factory=dict)
    base_currency_equity: Decimal = Decimal(0)
    total_translation_risk: Decimal = Decimal(0)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TreasuryEngine:
    """Multi-Currency Treasury Engine. Thread-safe."""

    _VOLATILITY: ClassVar[dict[Currency, Decimal]] = {
        Currency.USD: Decimal("0.01"),
        Currency.EUR: Decimal("0.015"),
        Currency.GBP: Decimal("0.02"),
        Currency.JPY: Decimal("0.015"),
        Currency.CHF: Decimal("0.01"),
        Currency.AUD: Decimal("0.025"),
        Currency.CAD: Decimal("0.02"),
        Currency.NZD: Decimal("0.03"),
        Currency.CNY: Decimal("0.02"),
        Currency.HKD: Decimal("0.005"),
        Currency.SGD: Decimal("0.015"),
        Currency.SEK: Decimal("0.025"),
        Currency.NOK: Decimal("0.025"),
        Currency.MXN: Decimal("0.04"),
        Currency.ZAR: Decimal("0.05"),
    }

    def __init__(self, config: CurrencyConfig | None = None):
        self._lock = threading.RLock()
        self._config = config or CurrencyConfig()
        self._cash_positions: dict[str, CashPosition] = {}
        self._fx_rates: dict[str, FXRate] = {}
        self._initialize_cash_positions()
        logger.info(
            "TreasuryEngine initialized: base={}, cash={}, settlement={}, margin={}, pnl={}, funding={}",
            self._config.base_currency, self._config.cash_currency, self._config.settlement_currency,
            self._config.margin_currency, self._config.pnl_currency, self._config.funding_currency,
        )

    def _initialize_cash_positions(self) -> None:
        currencies = {
            self._config.base_currency, self._config.cash_currency,
            self._config.settlement_currency, self._config.margin_currency,
            self._config.pnl_currency, self._config.funding_currency,
        }
        for ccy in currencies:
            for ct in CashType:
                self._cash_positions[f"{ccy.value}_{ct.value}"] = CashPosition(ccy, ct)

    def _fx_key(self, from_c: Currency, to_c: Currency) -> str:
        return f"{from_c.value}/{to_c.value}"

    def record_cash(self, currency: Currency, cash_type: CashType, amount: Decimal, desc: str = "") -> bool:
        with self._lock:
            pos = self._cash_positions.get(f"{currency.value}_{cash_type.value}")
            if not pos or pos.amount + amount < 0:
                logger.warning("Insufficient {} {}: have {}, need {}", currency, cash_type, pos.amount if pos else 0, -amount if amount < 0 else amount)
                return False
            pos.add(amount)
            logger.info("Recorded {} {} {} (bal: {}) {}", currency, cash_type, amount, pos.amount, desc)
            return True

    def get_cash_balance(self, currency: Currency, cash_type: CashType) -> Decimal:
        with self._lock:
            pos = self._cash_positions.get(f"{currency.value}_{cash_type.value}")
            return pos.amount if pos else Decimal(0)

    def set_fx_rate(self, from_c: Currency, to_c: Currency, rate: Decimal, src: str = "internal") -> None:
        with self._lock:
            self._fx_rates[self._fx_key(from_c, to_c)] = FXRate(from_c, to_c, rate, source=src)
            self._fx_rates[self._fx_key(to_c, from_c)] = FXRate(to_c, from_c, Decimal(1) / rate, source=src)

    def get_fx_rate(self, from_c: Currency, to_c: Currency) -> Decimal | None:
        with self._lock:
            fx = self._fx_rates.get(self._fx_key(from_c, to_c))
            return fx.rate if fx else None

    def compute_fx_translation_risk(self) -> Decimal:
        with self._lock:
            base = self._config.base_currency
            total = Decimal(0)
            for pos in self._cash_positions.values():
                if pos.amount == 0 or pos.currency == base:
                    continue
                rate = self.get_fx_rate(pos.currency, base)
                if not rate:
                    continue
                base_val = pos.amount * rate
                vol = self._VOLATILITY.get(pos.currency, Decimal("0.02"))
                total += base_val * vol
            logger.info("FX translation risk: {} {}", base, total)
            return total

    def get_treasury_status(self) -> TreasuryState:
        with self._lock:
            return TreasuryState(
                currency_config=self._config,
                cash_positions=dict(self._cash_positions),
                fx_rates=dict(self._fx_rates),
                base_currency_equity=self._base_equity(),
                total_translation_risk=self.compute_fx_translation_risk(),
                last_updated=datetime.now(timezone.utc),
            )

    def _base_equity(self) -> Decimal:
        base = self._config.base_currency
        total = Decimal(0)
        for pos in self._cash_positions.values():
            if pos.amount == 0:
                continue
            if pos.currency == base:
                total += pos.amount
            elif (rate := self.get_fx_rate(pos.currency, base)):
                total += pos.amount * rate
        return total

    def reserve_cash(self, currency: Currency, amount: Decimal, reason: str = "") -> bool:
        with self._lock:
            if self.get_cash_balance(currency, CashType.AVAILABLE_CASH) < amount:
                return False
            self.record_cash(currency, CashType.AVAILABLE_CASH, -amount, f"Reserve: {reason}")
            self.record_cash(currency, CashType.RESERVED_CASH, amount, f"Reserve: {reason}")
            return True

    def release_reservation(self, currency: Currency, amount: Decimal, reason: str = "") -> bool:
        with self._lock:
            if self.get_cash_balance(currency, CashType.RESERVED_CASH) < amount:
                return False
            self.record_cash(currency, CashType.RESERVED_CASH, -amount, f"Release: {reason}")
            self.record_cash(currency, CashType.AVAILABLE_CASH, amount, f"Release: {reason}")
            return True

    def allocate_emergency_cash(self, currency: Currency, amount: Decimal, reason: str = "") -> bool:
        with self._lock:
            if self.get_cash_balance(currency, CashType.AVAILABLE_CASH) < amount:
                return False
            self.record_cash(currency, CashType.AVAILABLE_CASH, -amount, f"Emergency: {reason}")
            self.record_cash(currency, CashType.EMERGENCY_CASH, amount, f"Emergency: {reason}")
            return True

    def get_cash_summary(self) -> dict[str, dict[str, Decimal]]:
        with self._lock:
            out: dict[str, dict[str, Decimal]] = {}
            for pos in self._cash_positions.values():
                out.setdefault(pos.currency.value, {})[pos.cash_type.value] = pos.amount
            return out


_treasury_engine: TreasuryEngine | None = None
_treasury_lock = threading.Lock()


def get_treasury_engine(config: CurrencyConfig | None = None) -> TreasuryEngine:
    global _treasury_engine
    with _treasury_lock:
        if _treasury_engine is None:
            _treasury_engine = TreasuryEngine(config)
        return _treasury_engine


def reset_treasury_engine() -> None:
    global _treasury_engine
    with _treasury_lock:
        _treasury_engine = None


treasury_engine = get_treasury_engine()