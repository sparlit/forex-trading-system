"""
symbol_master.py
----------------
Authoritative instrument database (Symbol Master) per V2.1 Section 15.

The Symbol Master is the one authoritative source of instrument metadata.
Every subsystem (risk, execution, analysis) must query the Symbol Master
to obtain contract specifications, trading hours, and constraints.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Instrument:
    """Canonical instrument definition (Section 15)."""

    canonical_symbol: str
    broker_symbol: str
    exchange: str
    asset_class: str
    currency: str
    contract_size: float
    tick_size: float
    tick_value: float
    min_volume: float
    max_volume: float
    volume_step: float
    margin_requirement: float
    leverage: float
    stop_distance_rule: float
    freeze_level: float
    trading_hours: list[dict]
    holidays: list[str]
    order_types: list[str]
    execution_rules: dict
    display_name: str = ""
    is_active: bool = True
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Instrument:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SymbolMaster:
    """Authoritative instrument registry.

    All subsystems must obtain instrument specs from this registry.
    It loads its data from a JSON file (with a built-in default set for
    common forex, metal, and crypto instruments so the system works
    out-of-the-box without external configuration).
    """

    DEFAULT_INSTRUMENTS: list[dict] = [
        {"canonical_symbol": "EURUSD", "broker_symbol": "EURUSD", "exchange": "FX", "asset_class": "FOREX",
         "currency": "USD", "contract_size": 100000.0, "tick_size": 0.00001, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "Euro / US Dollar"},
        {"canonical_symbol": "GBPUSD", "broker_symbol": "GBPUSD", "exchange": "FX", "asset_class": "FOREX",
         "currency": "USD", "contract_size": 100000.0, "tick_size": 0.00001, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "GBP / US Dollar"},
        {"canonical_symbol": "USDJPY", "broker_symbol": "USDJPY", "exchange": "FX", "asset_class": "FOREX",
         "currency": "JPY", "contract_size": 100000.0, "tick_size": 0.001, "tick_value": 100.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "USD / Japanese Yen"},
        {"canonical_symbol": "AUDUSD", "broker_symbol": "AUDUSD", "exchange": "FX", "asset_class": "FOREX",
         "currency": "USD", "contract_size": 100000.0, "tick_size": 0.00001, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "AUD / US Dollar"},
        {"canonical_symbol": "NZDUSD", "broker_symbol": "NZDUSD", "exchange": "FX", "asset_class": "FOREX",
         "currency": "USD", "contract_size": 100000.0, "tick_size": 0.00001, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "NZD / US Dollar"},
        {"canonical_symbol": "USDCAD", "broker_symbol": "USDCAD", "exchange": "FX", "asset_class": "FOREX",
         "currency": "CAD", "contract_size": 100000.0, "tick_size": 0.00001, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "USD / Canadian Dollar"},
        {"canonical_symbol": "XAUUSD", "broker_symbol": "XAUUSD", "exchange": "METAL", "asset_class": "METAL",
         "currency": "USD", "contract_size": 100.0, "tick_size": 0.01, "tick_value": 1.0,
         "min_volume": 0.01, "max_volume": 50.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "Gold / US Dollar"},
        {"canonical_symbol": "XAGUSD", "broker_symbol": "XAGUSD", "exchange": "METAL", "asset_class": "METAL",
         "currency": "USD", "contract_size": 5000.0, "tick_size": 0.001, "tick_value": 5.0,
         "min_volume": 0.01, "max_volume": 50.0, "volume_step": 0.01,
         "margin_requirement": 0.01, "leverage": 100.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+2"}, "display_name": "Silver / US Dollar"},
        {"canonical_symbol": "BTCUSD", "broker_symbol": "BTCUSD", "exchange": "BINANCE", "asset_class": "CRYPTO",
         "currency": "USD", "contract_size": 1.0, "tick_size": 0.01, "tick_value": 1.0,
         "min_volume": 0.001, "max_volume": 1000.0, "volume_step": 0.001,
         "margin_requirement": 0.05, "leverage": 20.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+0"}, "display_name": "Bitcoin / US Dollar"},
        {"canonical_symbol": "ETHUSD", "broker_symbol": "ETHUSD", "exchange": "BINANCE", "asset_class": "CRYPTO",
         "currency": "USD", "contract_size": 1.0, "tick_size": 0.01, "tick_value": 1.0,
         "min_volume": 0.001, "max_volume": 1000.0, "volume_step": 0.001,
         "margin_requirement": 0.05, "leverage": 20.0, "stop_distance_rule": 0.0, "freeze_level": 0.0,
         "trading_hours": [{"start": "00:00", "end": "24:00"}], "holidays": [],
         "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
         "execution_rules": {"filling": "IOC", "settlement": "T+0"}, "display_name": "Ethereum / US Dollar"},
    ]

    def __init__(self, config_path: str | None = None) -> None:
        self._instruments: dict[str, Instrument] = {}
        self._config_path = config_path
        self._load_defaults()
        if config_path:
            self._load_from_file(config_path)
        logger.info(f"SymbolMaster loaded with {len(self._instruments)} instruments")

    def _load_defaults(self) -> None:
        """Load the built-in default instrument set."""
        for d in self.DEFAULT_INSTRUMENTS:
            d["updated_at"] = datetime.now(timezone.utc).isoformat()
            inst = Instrument.from_dict(d)
            self._instruments[inst.canonical_symbol] = inst

    def _load_from_file(self, path: str) -> None:
        """Load additional instruments from a JSON file, overriding defaults."""
        p = Path(path)
        if not p.exists():
            logger.warning(f"SymbolMaster config file not found: {path}")
            return
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for d in data.get("instruments", []):
            d["updated_at"] = datetime.now(timezone.utc).isoformat()
            inst = Instrument.from_dict(d)
            self._instruments[inst.canonical_symbol] = inst
        logger.info(f"Loaded {len(data.get('instruments', []))} instruments from {path}")

    def get(self, canonical_symbol: str) -> Instrument | None:
        """Retrieve instrument by canonical symbol name."""
        return self._instruments.get(canonical_symbol.upper())

    def get_all(self) -> list[Instrument]:
        """Return all registered instruments."""
        return list(self._instruments.values())

    def get_by_asset_class(self, asset_class: str) -> list[Instrument]:
        """Filter instruments by asset class."""
        return [i for i in self._instruments.values() if i.asset_class == asset_class.upper()]

    def get_active_symbols(self) -> list[str]:
        """Return all active canonical symbols."""
        return [sym for sym, i in self._instruments.items() if i.is_active]

    def is_tradable(self, canonical_symbol: str) -> bool:
        """Check if a symbol is tradable."""
        inst = self.get(canonical_symbol)
        return inst is not None and inst.is_active

    def validate_volume(self, canonical_symbol: str, volume: float) -> tuple[bool, str]:
        """Validate volume against instrument constraints."""
        inst = self.get(canonical_symbol)
        if inst is None:
            return False, f"Unknown symbol: {canonical_symbol}"
        if volume < inst.min_volume:
            return False, f"Volume {volume} below minimum {inst.min_volume}"
        if volume > inst.max_volume:
            return False, f"Volume {volume} above maximum {inst.max_volume}"
        if inst.volume_step > 0:
            remainder = round(volume / inst.volume_step, 6)
            if abs(remainder - round(remainder)) > 1e-9:
                return False, f"Volume {volume} not aligned to step {inst.volume_step}"
        return True, ""

    def validate_price(self, canonical_symbol: str, price: float) -> tuple[bool, str]:
        """Validate price against tick size."""
        inst = self.get(canonical_symbol)
        if inst is None:
            return False, f"Unknown symbol: {canonical_symbol}"
        if price <= 0:
            return False, "Price must be positive"
        if inst.tick_size > 0:
            remainder = round(price / inst.tick_size, 8)
            if abs(remainder - round(remainder)) > 1e-10:
                return False, f"Price {price} not aligned to tick size {inst.tick_size}"
        return True, ""

    def validate_stop_distance(self, canonical_symbol: str, distance: float) -> tuple[bool, str]:
        """Validate that stop-loss distance meets minimum requirements."""
        inst = self.get(canonical_symbol)
        if inst is None:
            return False, f"Unknown symbol: {canonical_symbol}"
        if distance < inst.stop_distance_rule:
            return False, (f"Stop distance {distance} less than minimum "
                          f"{inst.stop_distance_rule} for {canonical_symbol}")
        return True, ""

    def is_market_open(self, canonical_symbol: str, now: datetime | None = None) -> bool:
        """Check if the market is open for a given symbol at the given time."""
        inst = self.get(canonical_symbol)
        if inst is None:
            return False
        if now is None:
            now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        if date_str in inst.holidays:
            return False
        if inst.asset_class == "CRYPTO":
            return True
        if inst.asset_class == "FOREX":
            if now.weekday() >= 5:
                return False
            return True
        current_hm = now.strftime("%H:%M")
        for session in inst.trading_hours:
            if session["start"] <= current_hm <= session["end"]:
                return True
        return False

    def register(self, instrument_dict: dict[str, Any]) -> None:
        """Register or update an instrument at runtime."""
        instrument_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        inst = Instrument.from_dict(instrument_dict)
        self._instruments[inst.canonical_symbol] = inst
        logger.info(f"Registered instrument: {inst.canonical_symbol}")

    def to_json(self) -> str:
        """Export all instruments as JSON."""
        return json.dumps([i.to_dict() for i in self._instruments.values()], indent=2)
