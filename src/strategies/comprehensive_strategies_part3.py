"""
Elite Autonomous Quantum Trading System - Comprehensive Strategy Suite (Part 3)
Advanced Strategy Implementations: Order Flow, Pairs Trading, HFT, Event-Driven, etc.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from src.data.models import MarketData, Signal, SignalType, Timeframe
from src.strategies.comprehensive_strategies import (
    StrategyCategory,
    StrategyMetadata,
    TradingStyle,
    register_strategy,
)
from src.strategy.base import BaseStrategy, StrategyConfig
from src.strategy.technical.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


# ============================================================
# 7. ICT / SMART MONEY CONCEPTS (SMC)
# ============================================================

@dataclass
class SMCConfig:
    swing_lookback: int = 50
    fvg_lookback: int = 20
    order_block_lookback: int = 50
    liquidity_lookback: int = 100
    breaker_block_lookback: int = 50
    mitigation_threshold: float = 0.5


class ICTSMCStrategy(BaseStrategy):
    """ICT / Smart Money Concepts (SMC) - Order blocks, FVG, Breaker blocks, Liquidity"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.smc_config = SMCConfig(**config.parameters.get("ict_smc", {}))

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M15, Timeframe.H1, Timeframe.H4]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"])

    def _identify_swing_highs_lows(self, highs: np.ndarray, lows: np.ndarray, lookback: int) -> tuple[list[int], list[int]]:
        """Identify swing highs and lows."""
        swing_highs = []
        swing_lows = []

        for i in range(lookback, len(highs) - lookback):
            # Swing high
            if all(highs[i] > highs[i-j] for j in range(1, lookback+1)) and \
               all(highs[i] > highs[i+j] for j in range(1, lookback+1)):
                swing_highs.append(i)

            # Swing low
            if all(lows[i] < lows[i-j] for j in range(1, lookback+1)) and \
               all(lows[i] < lows[i+j] for j in range(1, lookback+1)):
                swing_lows.append(i)

        return swing_highs, swing_lows

    def _identify_fvg(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> list[dict]:
        """Identify Fair Value Gaps (FVG)."""
        fvgs = []

        for i in range(2, len(closes) - 1):
            # Bullish FVG: low[i] > high[i-2]
            if lows[i] > highs[i-2]:
                fvgs.append({
                    "type": "bullish",
                    "index": i,
                    "top": lows[i],
                    "bottom": highs[i-2],
                    "mid": (lows[i] + highs[i-2]) / 2
                })

            # Bearish FVG: high[i] < low[i-2]
            if highs[i] < lows[i-2]:
                fvgs.append({
                    "type": "bearish",
                    "index": i,
                    "top": lows[i-2],
                    "bottom": highs[i],
                    "mid": (lows[i-2] + highs[i]) / 2
                })

        return fvgs

    def _identify_order_blocks(self, highs: np.ndarray, lows: np.ndarray,
                               closes: np.ndarray, volumes: np.ndarray,
                               swing_highs: list[int], swing_lows: list[int]) -> list[dict]:
        """Identify Order Blocks (OB)."""
        order_blocks = []

        # Bullish OB: Last down candle before up move from swing low
        for sl in swing_lows:
            if sl > 10:
                # Look for last bearish candle before move up
                for i in range(sl-1, max(sl-20, 0), -1):
                    if i > 0 and i < len(closes):
                        if closes[i] < closes[i-1]:  # Bearish candle
                            ob = {
                                "type": "bullish",
                                "index": i,
                                "top": max(closes[i], closes[i-1]),
                                "bottom": min(closes[i], closes[i-1]),
                                "volume": volumes[i] if i < len(volumes) else 0
                            }
                            order_blocks.append(ob)
                            break

        # Bearish OB: Last up candle before down move from swing high
        for sh in swing_highs:
            if sh > 10:
                for i in range(sh-1, max(sh-20, 0), -1):
                    if i > 0 and i < len(closes):
                        if closes[i] > closes[i-1]:  # Bullish candle
                            ob = {
                                "type": "bearish",
                                "index": i,
                                "top": max(closes[i], closes[i-1]),
                                "bottom": min(closes[i], closes[i-1]),
                                "volume": volumes[i] if i < len(volumes) else 0
                            }
                            order_blocks.append(ob)
                            break

        return order_blocks

    def _identify_breaker_blocks(self, highs: np.ndarray, lows: np.ndarray,
                                 closes: np.ndarray, swing_highs: list[int],
                                 swing_lows: list[int]) -> list[dict]:
        """Identify Breaker Blocks (failed order blocks)."""
        breaker_blocks = []

        # Simplified: Breaker block = order block that was mitigated then broken
        # This would require tracking historical order blocks and their mitigation

        return breaker_blocks

    def _identify_liquidity(self, highs: np.ndarray, lows: np.ndarray,
                           swing_highs: list[int], swing_lows: list[int]) -> dict[str, list[float]]:
        """Identify Buy-side and Sell-side liquidity."""
        buy_side_liquidity = [highs[i] for i in swing_highs]  # Above swing highs
        sell_side_liquidity = [lows[i] for i in swing_lows]   # Below swing lows

        return {
            "buy_side": buy_side_liquidity,
            "sell_side": sell_side_liquidity
        }

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        for symbol in self.required_symbols:
            bars_h1 = market_data.get_bars(symbol, Timeframe.H1)
            bars_h4 = market_data.get_bars(symbol, Timeframe.H4)

            if not bars_h1 or not bars_h4 or len(bars_h1) < 100 or len(bars_h4) < 50:
                continue

            highs = np.array([b.high for b in bars_h1])
            lows = np.array([b.low for b in bars_h1])
            closes = np.array([b.close for b in bars_h1])

            # Identify market structure
            swing_highs, swing_lows = self._identify_swing_highs_lows(highs, lows, 10)

            if not swing_highs or not swing_lows:
                continue

            # Identify FVGs
            fvgs = self._identify_fvg(highs, lows, closes)

            # Identify Order Blocks
            order_blocks = self._identify_order_blocks(highs, lows, closes,
                                                        np.array([b.volume for b in bars_h1]),
                                                        swing_highs, swing_lows)

            # Identify Liquidity
            liquidity = self._identify_liquidity(highs, lows, swing_highs, swing_lows)

            current_price = closes[-1]

            # Long setup: Price at bullish OB + bullish FVG + liquidity sweep
            bullish_obs = [ob for ob in order_blocks if ob["type"] == "bullish"]
            bullish_fvgs = [fvg for fvg in fvgs if fvg["type"] == "bullish"]

            for ob in bullish_obs:
                ob_top = ob["top"]
                ob_bottom = ob["bottom"]

                # Check if price is at OB
                if abs(current_price - ob_bottom) / current_price < 0.001:
                    # Check for bullish FVG above
                    for fvg in bullish_fvgs:
                        if fvg["bottom"] > current_price:
                            # Check for liquidity sweep (price swept sell-side liquidity)
                            if any(current_price < ls for ls in liquidity.get("sell_side", [])):
                                signal = Signal(
                                    strategy_id=self.strategy_id,
                                    symbol=symbol,
                                    timeframe=Timeframe.H1,
                                    signal_type=SignalType.ENTRY_LONG,
                                    direction="long",
                                    strength=0.8,
                                    entry_price=current_price,
                                    stop_loss=min(order_blocks, key=lambda x: x["bottom"])["bottom"] if order_blocks else closes[-1] * 0.99,
                                    take_profit=max(liquidity.get("buy_side", [closes[-1] * 1.02])),
                                    metadata={
                                        "ob_top": ob_top,
                                        "ob_bottom": ob_bottom,
                                        "fvg": fvg,
                                        "strategy": "ict_smc"
                                    }
                                )
                                return [signal]

        return []


# ============================================================
# 8. ORDER FLOW & VOLUME PROFILE TRADING
# ============================================================

@dataclass
class OrderFlowConfig:
    vp_period: int = 50
    poc_lookback: int = 20
    delta_threshold: float = 1000
    vpoc_threshold: float = 0.7


class OrderFlowVolumeProfileStrategy(BaseStrategy):
    """Order Flow & Volume Profile Trading"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.of_config = OrderFlowConfig(**config.parameters.get("order_flow", {}))

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M1, Timeframe.M5, Timeframe.M15]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"])

    def _calculate_volume_profile(self, highs: np.ndarray, lows: np.ndarray,
                                   closes: np.ndarray, volumes: np.ndarray,
                                   period: int) -> dict:
        """Calculate Volume Profile with POC, VAH, VAL."""
        if len(closes) < period:
            return {}

        recent_highs = highs[-period:]
        recent_lows = lows[-period:]
        recent_closes = closes[-period:]
        recent_volumes = volumes[-period:]

        # Price bins
        price_min = np.min(recent_lows)
        price_max = np.max(recent_highs)
        num_bins = 50
        bin_size = (price_max - price_min) / num_bins

        volume_at_price = np.zeros(num_bins)

        # Distribute volume across price range of each candle
        for i in range(len(recent_closes)):
            candle_high = recent_highs[i]
            candle_low = recent_lows[i]

            start_bin = int((candle_low - price_min) / bin_size)
            end_bin = int((candle_high - price_min) / bin_size)
            start_bin = max(0, start_bin)
            end_bin = min(num_bins - 1, end_bin)

            if end_bin >= start_bin:
                vol_per_bin = recent_volumes[i] / (end_bin - start_bin + 1)
                volume_at_price[start_bin:end_bin+1] += vol_per_bin

        # POC - Price with highest volume
        poc_index = np.argmax(volume_at_price)
        poc_price = price_min + poc_index * bin_size + bin_size / 2

        # Value Area (70% of volume)
        total_vol = np.sum(volume_at_price)
        target_vol = total_vol * 0.7

        # Expand from POC
        va_low_idx = poc_index
        va_high_idx = poc_index
        current_vol = volume_at_price[poc_index]

        while current_vol < target_vol and (va_low_idx > 0 or va_high_idx < num_bins - 1):
            vol_below = volume_at_price[va_low_idx - 1] if va_low_idx > 0 else 0
            vol_above = volume_at_price[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0

            if vol_below >= vol_above and va_low_idx > 0:
                va_low_idx -= 1
                current_vol += volume_at_price[va_low_idx]
            elif va_high_idx < num_bins - 1:
                va_high_idx += 1
                current_vol += volume_at_price[va_high_idx]
            else:
                break

        vah_price = price_min + va_high_idx * bin_size + bin_size / 2
        val_price = price_min + va_low_idx * bin_size + bin_size / 2

        return {
            "poc": poc_price,
            "vah": vah_price,
            "val": val_price,
            "volume_at_price": volume_at_price,
            "price_min": price_min,
            "bin_size": bin_size
        }

    def _calculate_delta(self, highs: np.ndarray, lows: np.ndarray,
                         closes: np.ndarray, volumes: np.ndarray,
                         period: int) -> float:
        """Calculate cumulative delta (buy volume - sell volume)."""
        if len(closes) < period:
            return 0.0

        delta = 0.0
        for i in range(len(closes) - period, len(closes)):
            if i > 0:
                if closes[i] > closes[i-1]:
                    delta += volumes[i]  # Buying volume
                elif closes[i] < closes[i-1]:
                    delta -= volumes[i]  # Selling volume
        return delta

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        for symbol in self.required_symbols:
            bars_m1 = market_data.get_bars(symbol, Timeframe.M1)
            bars_m5 = market_data.get_bars(symbol, Timeframe.M5)

            if not bars_m1 or not bars_m5 or len(bars_m1) < 100 or len(bars_m5) < 50:
                continue

            # M5 data for volume profile
            m5_highs = np.array([b.high for b in bars_m5])
            m5_lows = np.array([b.low for b in bars_m5])
            m5_closes = np.array([b.close for b in bars_m5])
            m5_volumes = np.array([b.volume for b in bars_m5])

            # Volume profile
            vp = self._calculate_volume_profile(m5_highs, m5_lows, m5_closes, m5_volumes,
                                                 self.of_config.vp_period)

            if not vp:
                continue

            # Delta
            delta = self._calculate_delta(m5_highs, m5_lows, m5_closes, m5_volumes, 20)

            _current_price = m5_closes[-1]
            _poc = vp.get("poc", 0)
            vah = vp.get("vah", 0)
            val = vp.get("val", 0)

            # Delta divergence
            price_change = m5_closes[-1] - m5_closes[-2]
            if price_change > 0 and delta < -self.of_config.delta_threshold:
                # Price up, delta down - bearish divergence
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M5,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=0.75,
                    entry_price=m5_closes[-1],
                    stop_loss=m5_closes[-1] * 1.002,
                    take_profit=m5_closes[-1] * 0.99,
                    metadata={
                        "delta": delta,
                        "poc": vp.get("poc"),
                        "vah": vah,
                        "val": val,
                        "strategy": "order_flow_divergence"
                    }
                )
                return [signal]

            elif price_change < 0 and delta > self.of_config.delta_threshold:
                # Price down, delta up - bullish divergence
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    timeframe=Timeframe.M5,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=0.75,
                    entry_price=m5_closes[-1],
                    stop_loss=m5_closes[-1] * 0.998,
                    take_profit=m5_closes[-1] * 1.01,
                    metadata={
                        "delta": delta,
                        "poc": vp.get("poc"),
                        "vah": vah,
                        "val": val,
                        "strategy": "order_flow_divergence"
                    }
                )
                return [signal]

        return []


# ============================================================
# 9. STATISTICAL ARBITRAGE (PAIRS TRADING)
# ============================================================

@dataclass
class PairsTradingConfig:
    lookback_period: int = 252
    entry_zscore: float = 2.0
    exit_zscore: float = 0.5
    stop_zscore: float = 3.0
    min_correlation: float = 0.7
    half_life_min: int = 5
    half_life_max: int = 100
    max_pairs: int = 10


class PairsTradingStrategy(BaseStrategy):
    """Statistical Arbitrage - Pairs Trading"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.pairs_config = PairsTradingConfig(**config.parameters.get("pairs_trading", {}))
        self.pair_data: dict[str, dict] = {}

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.H1, Timeframe.H4, Timeframe.D1]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", [
            "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
            "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY"
        ])

    def _find_cointegrated_pairs(self, market_data: MarketData) -> list[tuple[str, str, float, float]]:
        """Find cointegrated pairs using Engle-Granger test."""
        pairs = []
        symbols = self.required_symbols

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i+1:]:
                # Get daily closes for both symbols
                bars1 = market_data.get_bars(sym1, Timeframe.D1)
                bars2 = market_data.get_bars(sym2, Timeframe.D1)

                if not bars1 or not bars2 or len(bars1) < 100 or len(bars2) < 100:
                    continue

                # Align data by timestamp
                closes1 = np.array([b.close for b in bars1[-252:]])
                closes2 = np.array([b.close for b in bars2[-252:]])

                if len(closes1) != len(closes2):
                    continue

                # Correlation check
                corr = np.corrcoef(closes1, closes2)[0, 1]
                if corr < self.pairs_config.min_correlation:
                    continue

                # Engle-Granger cointegration test (simplified)
                # Regress sym1 on sym2: y = alpha + beta * x + epsilon
                beta = np.cov(closes1, closes2)[0, 1] / np.var(closes2)
                alpha = np.mean(closes1) - beta * np.mean(closes2)
                spread = closes1 - (alpha + beta * closes2)

                # ADF test on spread (simplified - check mean reversion)
                # Half-life calculation
                spread_lag = spread[:-1]
                spread_diff = np.diff(spread)

                if len(spread_lag) > 10 and np.var(spread_lag) > 0:
                    beta_hl = np.cov(spread_lag, spread_diff)[0, 1] / np.var(spread_lag)
                    if 0 < beta_hl < 1:
                        half_life = -np.log(2) / np.log(beta_hl)

                        if self.pairs_config.half_life_min <= half_life <= self.pairs_config.half_life_max:
                            # Calculate z-score
                            zscore = (spread[-1] - np.mean(spread)) / np.std(spread) if np.std(spread) > 0 else 0

                            pairs.append((sym1, sym2, beta, zscore))

        return pairs

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []

        # Find cointegrated pairs
        pairs = self._find_cointegrated_pairs(market_data)

        for sym1, sym2, beta, zscore in pairs[:self.pairs_config.max_pairs]:
            bars1 = market_data.get_bars(sym1, Timeframe.H1)
            bars2 = market_data.get_bars(sym2, Timeframe.H1)

            if not bars1 or not bars2:
                continue

            closes1 = np.array([b.close for b in bars1[-252:]])
            closes2 = np.array([b.close for b in bars2[-252:]])

            if len(closes1) != len(closes2):
                continue

            beta = np.cov(closes1, closes2)[0, 1] / np.var(closes2)
            alpha = np.mean(closes1) - beta * np.mean(closes2)
            spread = closes1 - (alpha + beta * closes2)
            zscore = (spread[-1] - np.mean(spread)) / np.std(spread) if np.std(spread) > 0 else 0

            current_price1 = closes1[-1]
            current_price2 = closes2[-1]

            # Long spread (long sym1, short sym2)
            if zscore <= -self.pairs_config.entry_zscore:
                signals.append(Signal(
                    strategy_id=self.strategy_id,
                    symbol=sym1,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=closes1[-1],
                    stop_loss=closes1[-1] * 0.98,
                    take_profit=closes1[-1] * 1.02,
                    metadata={
                        "pair": f"{sym1}/{sym2}",
                        "beta": beta,
                        "zscore": zscore,
                        "hedge_ratio": beta,
                        "strategy": "pairs_trading"
                    }
                ))

                signals.append(Signal(
                    strategy_id=self.strategy_id,
                    symbol=sym2,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=closes2[-1],
                    stop_loss=closes2[-1] * 1.02,
                    take_profit=closes2[-1] * 0.98,
                    metadata={
                        "pair": f"{sym1}/{sym2}",
                        "beta": beta,
                        "zscore": zscore,
                        "hedge_ratio": beta,
                        "strategy": "pairs_trading"
                    }
                ))

            # Short spread (short sym1, long sym2)
            elif zscore >= self.pairs_config.entry_zscore:
                signals.append(Signal(
                    strategy_id=self.strategy_id,
                    symbol=sym1,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_SHORT,
                    direction="short",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=current_price1,
                    stop_loss=current_price1 * 1.02,
                    take_profit=current_price1 * 0.98,
                    metadata={
                        "pair": f"{sym1}/{sym2}",
                        "beta": beta,
                        "zscore": zscore,
                        "hedge_ratio": beta,
                        "strategy": "pairs_trading"
                    }
                ))

                signals.append(Signal(
                    strategy_id=self.strategy_id,
                    symbol=sym2,
                    timeframe=Timeframe.H1,
                    signal_type=SignalType.ENTRY_LONG,
                    direction="long",
                    strength=min(abs(zscore) / 3, 1.0),
                    entry_price=current_price2,
                    stop_loss=current_price2 * 0.98,
                    take_profit=current_price2 * 1.02,
                    metadata={
                        "pair": f"{sym1}/{sym2}",
                        "beta": beta,
                        "zscore": zscore,
                        "hedge_ratio": beta,
                        "strategy": "pairs_trading"
                    }
                ))

        return signals[:10]


# ============================================================
# 10. HIGH-FREQUENCY MARKET MAKING
# ============================================================

@dataclass
class MarketMakingConfig:
    spread_target_bps: float = 2.0
    max_position: float = 100000
    inventory_limit: float = 50000
    quote_size: float = 10000
    refresh_ms: int = 100
    max_spread_bps: float = 10.0
    adverse_selection_threshold: float = 0.0001


class MarketMakingStrategy(BaseStrategy):
    """High-Frequency Market Making (Order Book Liquidity Provision)"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.mm_config = MarketMakingConfig(**config.parameters.get("market_making", {}))
        self.current_inventory: dict[str, float] = defaultdict(float)

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.TICK, Timeframe.M1]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"])

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        """Generate market making quotes - returns bid/ask signals."""
        for symbol in self.required_symbols:
            # Get order book data
            order_book = market_data.get_order_book(symbol)
            if not order_book:
                continue

            best_bid = order_book.get("best_bid", 0)
            best_ask = order_book.get("best_ask", 0)
            _bid_vol = order_book.get("bid_volume", 0)
            _ask_vol = order_book.get("ask_volume", 0)

            if best_bid <= 0 or best_ask <= 0:
                continue

            mid_price = (best_bid + best_ask) / 2
            spread_bps = (best_ask - best_bid) / mid_price * 10000

            # Skip if spread too wide
            if spread_bps > self.mm_config.max_spread_bps:
                continue

            # Inventory management
            inventory = self.current_inventory.get(symbol, 0)
            inventory_ratio = inventory / self.mm_config.inventory_limit if self.mm_config.inventory_limit > 0 else 0

            # Skew quotes based on inventory
            skew = inventory_ratio * 0.5  # Max 50% skew

            # Calculate fair value with inventory skew
            fair_value = mid_price * (1 - skew)

            # Target spread
            target_spread = mid_price * self.mm_config.spread_target_bps / 10000

            # Calculate bid/ask
            half_spread = target_spread / 2
            bid_price = fair_value - half_spread
            ask_price = fair_value + half_spread

            # Adjust for inventory
            if inventory > self.mm_config.inventory_limit * 0.5:
                # Reduce bid, increase ask
                bid_price *= 0.9995
                ask_price *= 1.0005
            elif inventory < -self.mm_config.inventory_limit * 0.5:
                # Increase bid, reduce ask
                bid_price *= 1.0005
                ask_price *= 0.9995

            # Generate quote signals (these would be sent to execution engine)
            # For signal generation, we return the intended quotes
            signal = Signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                timeframe=Timeframe.TICK,
                signal_type=SignalType.QUOTE,
                direction="market_make",
                strength=0.5,
                entry_price=mid_price,
                stop_loss=0,
                take_profit=0,
                metadata={
                    "bid_price": bid_price,
                    "ask_price": ask_price,
                    "bid_size": self.mm_config.quote_size,
                    "ask_size": self.mm_config.quote_size,
                    "mid_price": mid_price,
                    "spread_bps": spread_bps,
                    "inventory": inventory,
                    "fair_value": fair_value,
                    "strategy": "market_making"
                }
            )
            return [signal]

        return []


# ============================================================
# 11. CENTRAL BANK NEWS STRADDLES
# ============================================================

@dataclass
class NewsStraddleConfig:
    pre_event_minutes: int = 30
    post_event_minutes: int = 60
    straddle_width_pct: float = 0.002
    min_volatility_increase: float = 1.5
    high_impact_only: bool = True


class NewsStraddleStrategy(BaseStrategy):
    """Central Bank News Straddles (Algorithmic Event Trading)"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.news_config = NewsStraddleConfig(**config.parameters.get("news_straddle", {}))
        self.event_calendar: list[dict] = []

    @property
    def required_timeframes(self) -> list:
        return [Timeframe.M5, Timeframe.M15, Timeframe.H1]

    @property
    def required_symbols(self) -> list[str]:
        return self.config.parameters.get("symbols", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "EURGBP"])

    async def _fetch_economic_calendar(self) -> list[dict]:
        """Fetch economic calendar events."""
        # Placeholder - would fetch from economic calendar API
        return [
            {
                "event": "FOMC Rate Decision",
                "currency": "USD",
                "time": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                "impact": "high",
                "forecast": "5.50%",
                "previous": "5.50%"
            }
        ]

    async def generate_signals(self, market_data: MarketData) -> list[Signal]:
        signals = []

        # Fetch upcoming events
        events = await self._fetch_economic_calendar()
        now = datetime.now(UTC)

        for event in events:
            event_time_str = event.get("time")
            if not event_time_str:
                continue

            event_time = datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
            time_to_event = (event_time - now).total_seconds() / 60
            currency = event.get("currency", "")
            impact = event.get("impact", "low")

            if self.news_config.high_impact_only and impact != "high":
                continue

            # Find relevant symbols
            relevant_symbols = [s for s in self.required_symbols if currency in s]

            # Pre-event straddle setup
            if 0 < time_to_event <= self.news_config.pre_event_minutes:
                for symbol in relevant_symbols:
                    bars = market_data.get_bars(symbol, Timeframe.M5)
                    if not bars or len(bars) < 20:
                        continue

                    current_price = bars[-1].close
                    atr = TechnicalIndicators.atr(
                        np.array([b.high for b in market_data.get_bars(symbol, Timeframe.H1)[-20:]]),
                        np.array([b.low for b in market_data.get_bars(symbol, Timeframe.H1)[-20:]]),
                        np.array([b.close for b in market_data.get_bars(symbol, Timeframe.H1)[-20:]]),
                        14
                    )[-1]

                    straddle_width = current_price * self.news_config.straddle_width_pct

                    # Buy stop above / Sell stop below
                    _buy_stop = current_price + straddle_width
                    _sell_stop = current_price - straddle_width

                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe.M5,
                        signal_type=SignalType.ENTRY_LONG,
                        direction="long",
                        strength=0.7,
                        entry_price=current_price + straddle_width / 2,
                        stop_loss=current_price - atr * 1.5,
                        take_profit=current_price + atr * 3,
                        metadata={
                            "event": event.get("event"),
                            "event_time": event_time.isoformat(),
                            "straddle_width": straddle_width,
                            "strategy": "news_straddle_buy"
                        }
                    ))

                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe.M5,
                        signal_type=SignalType.ENTRY_SHORT,
                        direction="short",
                        strength=0.7,
                        entry_price=current_price - straddle_width / 2,
                        stop_loss=current_price + atr * 1.5,
                        take_profit=current_price - atr * 3,
                        metadata={
                            "event": event.get("event"),
                            "event_time": event_time.isoformat(),
                            "straddle_width": straddle_width,
                            "strategy": "news_straddle_sell"
                        }
                    ))

        return signals[:10]


# Register new strategies
register_strategy(StrategyMetadata(
    name="ict_smc",
    category=StrategyCategory.PATTERN,
    trading_style=TradingStyle.SWING_TRADING,
    description="ICT / Smart Money Concepts - Order blocks, FVG, Breaker blocks, Liquidity",
    required_timeframes=[Timeframe.M15, Timeframe.H1, Timeframe.H4],
    required_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
    min_holding_period=timedelta(hours=4),
    max_holding_period=timedelta(days=7),
    typical_win_rate=0.55,
    typical_risk_reward=2.5,
    complexity=5,
    capital_efficiency=0.6,
    slippage_sensitivity=0.4
))

register_strategy(StrategyMetadata(
    name="order_flow",
    category=StrategyCategory.ORDER_FLOW,
    trading_style=TradingStyle.SCALPING,
    description="Order Flow & Volume Profile Trading",
    required_timeframes=[Timeframe.M1, Timeframe.M5, Timeframe.M15],
    required_symbols=["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"],
    min_holding_period=timedelta(minutes=1),
    max_holding_period=timedelta(minutes=30),
    typical_win_rate=0.65,
    typical_risk_reward=1.5,
    complexity=5,
    capital_efficiency=0.7,
    slippage_sensitivity=0.8
))

register_strategy(StrategyMetadata(
    name="pairs_trading",
    category=StrategyCategory.STATISTICAL,
    trading_style=TradingStyle.SWING_TRADING,
    description="Statistical Arbitrage (Pairs Trading) - Cointegration based",
    required_timeframes=[Timeframe.H1, Timeframe.H4, Timeframe.D1],
    required_symbols=["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
                      "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY"],
    min_holding_period=timedelta(hours=4),
    max_holding_period=timedelta(days=14),
    typical_win_rate=0.60,
    typical_risk_reward=2.0,
    complexity=5,
    capital_efficiency=0.8,
    slippage_sensitivity=0.3
))

register_strategy(StrategyMetadata(
    name="market_making",
    category=StrategyCategory.MARKET_MAKING,
    trading_style=TradingStyle.HIGH_FREQUENCY,
    description="High-Frequency Market Making (Order Book Liquidity Provision)",
    required_timeframes=[Timeframe.TICK, Timeframe.M1],
    required_symbols=["EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"],
    min_holding_period=timedelta(seconds=1),
    max_holding_period=timedelta(minutes=5),
    typical_win_rate=0.52,
    typical_risk_reward=0.8,
    complexity=5,
    capital_efficiency=0.9,
    slippage_sensitivity=0.9
))

register_strategy(StrategyMetadata(
    name="news_straddle",
    category=StrategyCategory.EVENT_DRIVEN,
    trading_style=TradingStyle.DAY_TRADING,
    description="Central Bank News Straddles (Algorithmic Event Trading)",
    required_timeframes=[Timeframe.M5, Timeframe.M15, Timeframe.H1],
    required_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "EURGBP"],
    min_holding_period=timedelta(minutes=30),
    max_holding_period=timedelta(hours=4),
    typical_win_rate=0.55,
    typical_risk_reward=2.0,
    complexity=4,
    capital_efficiency=0.7,
    slippage_sensitivity=0.6
))


# Export new strategies
__all__ = [
    "ICTSMCStrategy",
    "MarketMakingStrategy",
    "NewsStraddleStrategy",
    "OrderFlowVolumeProfileStrategy",
    "PairsTradingStrategy",
]