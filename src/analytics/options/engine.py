"""
Elite Autonomous Quantum Trading System - Options Analytics Engine
Real-time Option Chain Metrics, Greeks, IV Surfaces, Term Structures
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from scipy.stats import norm

logger = logging.getLogger(__name__)


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


class OptionStyle(Enum):
    EUROPEAN = "european"
    AMERICAN = "american"


@dataclass
class OptionContract:
    """Option contract specification."""
    symbol: str                    # Underlying symbol (e.g., "SPY", "BTCUSD")
    strike: float                  # Strike price
    expiry: datetime               # Expiration date
    option_type: OptionType        # CALL or PUT
    style: OptionStyle = OptionStyle.EUROPEAN
    contract_id: str = ""          # Unique identifier
    
    def __post_init__(self):
        if not self.contract_id:
            self.contract_id = f"{self.symbol}_{self.expiry.strftime('%y%m%d')}_{self.strike}_{self.option_type.value[0].upper()}"


@dataclass
class OptionGreeks:
    """Option Greeks calculation result."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: float = 0.0
    theoretical_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    mid: float = 0.0
    spread: float = 0.0
    volume: int = 0
    open_interest: int = 0


@dataclass
class OptionChainSnapshot:
    """Complete option chain snapshot."""
    underlying: str
    spot_price: float
    timestamp: datetime
    contracts: dict[str, OptionGreeks] = field(default_factory=dict)
    expiries: list[datetime] = field(default_factory=list)
    strikes: list[float] = field(default_factory=list)


@dataclass
class IVSurfacePoint:
    """Implied volatility surface data point."""
    expiry: datetime
    strike: float
    moneyness: float        # strike / spot
    dte: int               # days to expiry
    iv: float              # implied volatility
    delta: float           # delta
    volume: int = 0
    oi: int = 0


class BlackScholesModel:
    """Black-Scholes-Merton option pricing and Greeks."""
    
    @staticmethod
    def price(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        option_type: OptionType,
        dividend_yield: float = 0.0
    ) -> float:
        """Calculate Black-Scholes option price."""
        if time_to_expiry <= 0:
            if option_type == OptionType.CALL:
                return max(spot - strike, 0)
            else:
                return max(strike - spot, 0)
        
        d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
        d2 = d1 - volatility * math.sqrt(time_to_expiry)
        
        if option_type == OptionType.CALL:
            price = spot * math.exp(-dividend_yield * time_to_expiry) * norm.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        else:
            price = strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * math.exp(-dividend_yield * time_to_expiry) * norm.cdf(-d1)
        
        return max(price, 0)
    
    @staticmethod
    def greeks(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        option_type: OptionType,
        dividend_yield: float = 0.0
    ) -> dict[str, float]:
        """Calculate all Greeks."""
        if time_to_expiry <= 0:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}
        
        d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
        d2 = d1 - volatility * math.sqrt(time_to_expiry)
        
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        cdf_d2 = norm.cdf(d2)
        cdf_neg_d1 = norm.cdf(-d1)
        cdf_neg_d2 = norm.cdf(-d2)
        
        # Delta
        if option_type == OptionType.CALL:
            delta = math.exp(-dividend_yield * time_to_expiry) * cdf_d1
        else:
            delta = -math.exp(-dividend_yield * time_to_expiry) * cdf_neg_d1
        
        # Gamma
        gamma = math.exp(-dividend_yield * time_to_expiry) * pdf_d1 / (spot * volatility * math.sqrt(time_to_expiry))
        
        # Theta (per day)
        if option_type == OptionType.CALL:
            theta = (
                -spot * pdf_d1 * volatility * math.exp(-dividend_yield * time_to_expiry) / (2 * math.sqrt(time_to_expiry))
                - risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * cdf_d2
                + dividend_yield * spot * math.exp(-dividend_yield * time_to_expiry) * cdf_d1
            ) / 365
        else:
            theta = (
                -spot * pdf_d1 * volatility * math.exp(-dividend_yield * time_to_expiry) / (2 * math.sqrt(time_to_expiry))
                + risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * cdf_neg_d2
                - dividend_yield * spot * math.exp(-dividend_yield * time_to_expiry) * cdf_neg_d1
            ) / 365
        
        # Vega (per 1% vol change)
        vega = spot * math.exp(-dividend_yield * time_to_expiry) * pdf_d1 * math.sqrt(time_to_expiry) / 100
        
        # Rho (per 1% rate change)
        if option_type == OptionType.CALL:
            rho = strike * time_to_expiry * math.exp(-risk_free_rate * time_to_expiry) * cdf_d2 / 100
        else:
            rho = -strike * time_to_expiry * math.exp(-risk_free_rate * time_to_expiry) * cdf_neg_d2 / 100
        
        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho
        }
    
    @staticmethod
    def implied_volatility(
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: OptionType,
        dividend_yield: float = 0.0,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> float:
        """Calculate implied volatility using Newton-Raphson."""
        if market_price <= 0 or time_to_expiry <= 0:
            return 0.0
        
        # Initial guess using Brenner-Subrahmanyam approximation
        intrinsic = max(spot - strike, 0) if option_type == OptionType.CALL else max(strike - spot, 0)
        if market_price <= intrinsic:
            return 0.001
        
        vol = math.sqrt(2 * math.pi / time_to_expiry) * market_price / spot
        vol = max(0.01, min(vol, 5.0))
        
        for _ in range(max_iterations):
            price = BlackScholesModel.price(spot, strike, time_to_expiry, risk_free_rate, vol, option_type, dividend_yield)
            greeks = BlackScholesModel.greeks(spot, strike, time_to_expiry, risk_free_rate, vol, option_type, dividend_yield)
            vega = greeks["vega"] * 100  # Convert back from per-1%
            
            diff = price - market_price
            if abs(diff) < tolerance:
                return vol
            
            if vega == 0:
                break
            
            vol = vol - diff / vega
            vol = max(0.001, min(vol, 5.0))
        
        return vol


class OptionsAnalyticsEngine:
    """
    Real-time Options Analytics Engine.
    
    Features:
    - Real-time Greeks calculation (Delta, Gamma, Theta, Vega, Rho)
    - Implied volatility surface construction
    - Option chain aggregation and analysis
    - IV skew/smile analysis
    - Term structure analysis
    - Greeks-based risk management
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.risk_free_rate = self.config.get("risk_free_rate", 0.05)
        self.dividend_yield = self.config.get("dividend_yield", 0.0)
        self.update_interval = self.config.get("update_interval", 1.0)  # seconds
        
        # Data storage
        self.option_chains: dict[str, OptionChainSnapshot] = {}
        self.iv_surfaces: dict[str, list[IVSurfacePoint]] = defaultdict(list)
        self.historical_iv: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        
        # Model
        self.model = BlackScholesModel()
        
        # Callbacks
        self.on_chain_update: list[callable] = []
        self.on_iv_surface_update: list[callable] = []
        
        logger.info("OptionsAnalyticsEngine initialized")
    
    async def initialize(self):
        """Initialize the engine."""
        logger.info("Options Analytics Engine ready")
    
    def update_market_data(
        self,
        underlying: str,
        spot_price: float,
        option_data: list[dict[str, Any]],
        timestamp: datetime | None = None
    ) -> OptionChainSnapshot:
        """
        Update option chain with new market data.
        
        Args:
            underlying: Underlying symbol (e.g., "SPY", "BTCUSD")
            spot_price: Current spot price
            option_data: List of option contracts with market data
                Each dict should have: contract_id, strike, expiry, type, bid, ask, volume, oi
            timestamp: Data timestamp
        
        Returns:
            Updated OptionChainSnapshot
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)
        
        chain = OptionChainSnapshot(
            underlying=underlying,
            spot_price=spot_price,
            timestamp=timestamp
        )
        
        strikes_set = set()
        expiries_set = set()
        
        for opt in option_data:
            try:
                contract_id = opt.get("contract_id", "")
                strike = float(opt.get("strike", 0))
                expiry = opt.get("expiry")
                if isinstance(expiry, str):
                    expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
                option_type = OptionType(opt.get("type", "call").lower())
                
                bid = float(opt.get("bid", 0))
                ask = float(opt.get("ask", 0))
                volume = int(opt.get("volume", 0))
                oi = int(opt.get("open_interest", 0))
                
                mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
                spread = ask - bid if ask > bid else 0
                
                # Time to expiry in years
                time_to_expiry = (expiry - timestamp).total_seconds() / (365.25 * 24 * 3600)
                
                # Calculate IV from mid price
                iv = 0.0
                if mid > 0 and time_to_expiry > 0:
                    iv = self.model.implied_volatility(
                        market_price=mid,
                        spot=spot_price,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        risk_free_rate=self.risk_free_rate,
                        option_type=option_type,
                        dividend_yield=self.dividend_yield
                    )
                
                # Calculate Greeks
                greeks_dict = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}
                if iv > 0 and time_to_expiry > 0:
                    greeks_dict = self.model.greeks(
                        spot=spot_price,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        risk_free_rate=self.risk_free_rate,
                        volatility=iv,
                        option_type=option_type,
                        dividend_yield=self.dividend_yield
                    )
                
                # Theoretical price
                theoretical = 0.0
                if iv > 0 and time_to_expiry > 0:
                    theoretical = self.model.price(
                        spot=spot_price,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        risk_free_rate=self.risk_free_rate,
                        volatility=iv,
                        option_type=option_type,
                        dividend_yield=self.dividend_yield
                    )
                
                greeks = OptionGreeks(
                    delta=greeks_dict["delta"],
                    gamma=greeks_dict["gamma"],
                    theta=greeks_dict["theta"],
                    vega=greeks_dict["vega"],
                    rho=greeks_dict["rho"],
                    implied_volatility=iv,
                    theoretical_price=theoretical,
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    spread=spread,
                    volume=volume,
                    open_interest=oi
                )
                
                chain.contracts[contract_id] = greeks
                strikes_set.add(strike)
                expiries_set.add(expiry)
                
                # Add to IV surface
                if iv > 0:
                    moneyness = strike / spot_price if spot_price > 0 else 1.0
                    dte = int(time_to_expiry * 365.25)
                    surface_point = IVSurfacePoint(
                        expiry=expiry,
                        strike=strike,
                        moneyness=moneyness,
                        dte=dte,
                        iv=iv,
                        delta=greeks_dict["delta"],
                        volume=volume,
                        oi=oi
                    )
                    self.iv_surfaces[underlying].append(surface_point)
                
            except Exception as e:
                logger.debug(f"Error processing option {opt}: {e}")
                continue
        
        chain.expiries = sorted(expiries_set)
        chain.strikes = sorted(strikes_set)
        
        # Store chain
        self.option_chains[underlying] = chain
        
        # Trigger callbacks
        for callback in self.on_chain_update:
            try:
                callback(chain)
            except Exception as e:
                logger.error(f"Chain update callback error: {e}")
        
        return chain
    
    def get_chain(self, underlying: str) -> OptionChainSnapshot | None:
        """Get current option chain for underlying."""
        return self.option_chains.get(underlying)
    
    def get_greeks(self, underlying: str, contract_id: str) -> OptionGreeks | None:
        """Get Greeks for specific contract."""
        chain = self.option_chains.get(underlying)
        if chain:
            return chain.contracts.get(contract_id)
        return None
    
    def get_iv_surface(self, underlying: str, max_points: int = 1000) -> list[IVSurfacePoint]:
        """Get implied volatility surface data."""
        points = self.iv_surfaces.get(underlying, [])
        # Return most recent points per expiry/strike
        if len(points) > max_points:
            # Keep latest per unique expiry-strike combo
            seen = {}
            for p in reversed(points):
                key = (p.expiry, p.strike)
                if key not in seen:
                    seen[key] = p
                if len(seen) >= max_points:
                    break
            return list(reversed(list(seen.values())))
        return points
    
    def get_iv_skew(self, underlying: str, expiry: datetime | None = None) -> dict[float, float]:
        """Get IV skew (IV by moneyness) for specific expiry or all."""
        chain = self.option_chains.get(underlying)
        if not chain:
            return {}
        
        skew = {}
        for contract_id, greeks in chain.contracts.items():
            if greeks.implied_volatility > 0:
                # Extract strike from contract_id
                parts = contract_id.split('_')
                if len(parts) >= 3:
                    try:
                        strike = float(parts[2])
                        moneyness = strike / chain.spot_price
                        if expiry is None or abs(greeks.implied_volatility) > 0:
                            skew[moneyness] = greeks.implied_volatility
                    except (ValueError, IndexError):
                        continue
        
        return dict(sorted(skew.items()))
    
    def get_term_structure(self, underlying: str, moneyness: float = 1.0, tolerance: float = 0.05) -> dict[int, float]:
        """Get IV term structure (IV by DTE) for specific moneyness."""
        chain = self.option_chains.get(underlying)
        if not chain:
            return {}
        
        term_structure = {}
        for contract_id, greeks in chain.contracts.items():
            if greeks.implied_volatility > 0:
                parts = contract_id.split('_')
                if len(parts) >= 4:
                    try:
                        strike = float(parts[2])
                        contract_moneyness = strike / chain.spot_price
                        if abs(contract_moneyness - moneyness) <= tolerance:
                            expiry_str = parts[1]
                            expiry = datetime.strptime(expiry_str, '%y%m%d')
                            dte = (expiry - chain.timestamp).days
                            if dte > 0:
                                term_structure[dte] = greeks.implied_volatility
                    except (ValueError, IndexError):
                        continue
        
        return dict(sorted(term_structure.items()))
    
    def calculate_portfolio_greeks(self, positions: list[dict[str, Any]]) -> dict[str, float]:
        """Calculate aggregate Greeks for option portfolio."""
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        total_rho = 0.0
        
        for pos in positions:
            underlying = pos.get("underlying", "")
            contract_id = pos.get("contract_id", "")
            quantity = pos.get("quantity", 0)
            
            greeks = self.get_greeks(underlying, contract_id)
            if greeks:
                total_delta += greeks.delta * quantity
                total_gamma += greeks.gamma * quantity
                total_theta += greeks.theta * quantity
                total_vega += greeks.vega * quantity
                total_rho += greeks.rho * quantity
        
        return {
            "delta": total_delta,
            "gamma": total_gamma,
            "theta": total_theta,
            "vega": total_vega,
            "rho": total_rho
        }
    
    def get_atm_iv(self, underlying: str, expiry: datetime | None = None) -> float:
        """Get at-the-money implied volatility."""
        chain = self.option_chains.get(underlying)
        if not chain:
            return 0.0
        
        atm_iv = 0.0
        min_diff = float('inf')
        
        for contract_id, greeks in chain.contracts.items():
            if greeks.implied_volatility > 0:
                parts = contract_id.split('_')
                if len(parts) >= 3:
                    try:
                        strike = float(parts[2])
                        diff = abs(strike - chain.spot_price)
                        if diff < min_diff:
                            min_diff = diff
                            atm_iv = greeks.implied_volatility
                    except (ValueError, IndexError):
                        continue
        
        return atm_iv
    
    def get_risk_reversals(self, underlying: str, delta: float = 0.25) -> dict[str, float]:
        """Get risk reversal (put IV - call IV) and straddle (avg IV) by delta."""
        chain = self.option_chains.get(underlying)
        if not chain:
            return {}
        
        results = {}
        
        # Group by expiry
        by_expiry = defaultdict(lambda: {"calls": [], "puts": []})
        
        for contract_id, greeks in chain.contracts.items():
            if abs(greeks.delta) > 0.01:  # Has meaningful delta
                parts = contract_id.split('_')
                if len(parts) >= 4:
                    try:
                        expiry_str = parts[1]
                        option_type = parts[3][0].upper()  # C or P
                        expiry = datetime.strptime(expiry_str, '%y%m%d')
                        
                        if option_type == 'C':
                            by_expiry[expiry]["calls"].append((abs(greeks.delta), greeks.implied_volatility))
                        else:
                            by_expiry[expiry]["puts"].append((abs(greeks.delta), greeks.implied_volatility))
                    except (ValueError, IndexError):
                        continue
        
        for expiry, data in by_expiry.items():
            # Find closest to target delta
            call_iv = self._interpolate_delta(data["calls"], delta)
            put_iv = self._interpolate_delta(data["puts"], delta)
            
            if call_iv > 0 and put_iv > 0:
                key = expiry.strftime('%y%m%d')
                results[f"rr_{key}"] = put_iv - call_iv  # Risk reversal
                results[f"straddle_{key}"] = (put_iv + call_iv) / 2  # Straddle
        
        return results
    
    def _interpolate_delta(self, options: list[tuple[float, float]], target_delta: float) -> float:
        """Interpolate IV at target delta."""
        if not options:
            return 0.0
        
        options.sort(key=lambda x: x[0])
        
        # Find closest
        for i, (d, iv) in enumerate(options):
            if d >= target_delta:
                if i == 0:
                    return iv
                # Linear interpolation
                d1, iv1 = options[i-1]
                d2, iv2 = d, iv
                if d2 == d1:
                    return iv1
                return iv1 + (iv2 - iv1) * (target_delta - d1) / (d2 - d1)
        
        return options[-1][1]  # Return highest delta IV


# Global instance
options_engine = OptionsAnalyticsEngine()


async def get_options_engine(config: dict | None = None) -> OptionsAnalyticsEngine:
    """Get or create global options engine."""
    global options_engine
    if config:
        options_engine = OptionsAnalyticsEngine(config)
        await options_engine.initialize()
    return options_engine