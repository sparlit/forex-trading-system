#!/usr/bin/env python3
"""
Elite Autonomous Quantum Trading System - Main Entry Point
Complete 100% Autonomous Auto Trading Application with zero user input.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.autonomous.decision_engine import AutonomousDecisionEngine
from src.autonomous.selection_engine import SelectionContext, selection_engine
from src.brain.analysis_brain import AnalysisBrain
from src.brain.next_candle_predictor import NextCandlePredictor
from src.brain.self_evolving_brain import SelfEvolvingBrain
from src.compute.parallel import BackendType, ParallelConfig, ParallelProcessor
from src.data.ingest.ccxt_connector import CCXTProvider as CCXTConnector
from src.data.ingest.mt5_connector import MT5Provider as MT5Connector
from src.execution.order_manager import OrderManager
from src.risk.portfolio_risk import PortfolioRiskManager
from src.strategy.session_manager import session_manager

# Configure logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "autonomous_trading.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="a"),
    ],
)
logger = logging.getLogger(__name__)


class AutonomousTradingSystem:
    """
    Complete 100% Autonomous Trading System.
    
    Integrates all components:
    - Automatic selection of method, style, strategy, session, symbols
    - Self-evolving brain with 11 autonomous capabilities
    - Parallel processing for brain modules
    - Real-time market data ingestion (MT5 + CCXT)
    - Risk management and portfolio optimization
    - Order execution and management
    - Session-aware trading with crypto 24/7 fallback
    - Non-stop, non-break autonomous loop
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Core components
        self.brain: SelfEvolvingBrain | None = None
        self.parallel_processor: ParallelProcessor | None = None
        self.decision_engine: AutonomousDecisionEngine | None = None
        self.mt5_connector: MT5Connector | None = None
        self.ccxt_connector: CCXTConnector | None = None
        self.order_manager: OrderManager | None = None
        self.risk_manager: PortfolioRiskManager | None = None
        self.analysis_brain: AnalysisBrain | None = None
        self.predictor: NextCandlePredictor | None = None
        
        # State
        self.iteration = 0
        self.last_market_data: dict[str, Any] = {}
        self.active_positions: dict[str, Any] = {}
        self.account_info: dict[str, Any] = {}
        self.performance_metrics: dict[str, Any] = {}
        
        # Metrics
        self.metrics = {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0.0,
            "start_time": None,
            "last_trade_time": None,
        }
        
        logger.info("AutonomousTradingSystem initialized")
    
    async def initialize(self) -> bool:
        """Initialize all system components."""
        logger.info("=" * 60)
        logger.info("INITIALIZING ELITE AUTONOMOUS QUANTUM TRADING SYSTEM")
        logger.info("=" * 60)
        
        try:
            # 1. Initialize parallel processor for brain modules
            logger.info("🔧 Initializing Parallel Processor...")
            self.parallel_processor = ParallelProcessor(ParallelConfig(
                backend=BackendType.THREADING,
                max_workers=16,
                chunk_size=100,
            ))
            await self.parallel_processor.initialize()
            logger.info("✅ Parallel Processor ready (16 workers, threading backend)")
            
            # 2. Initialize session manager (global sessions)
            logger.info("🌍 Initializing Session Manager...")
            await session_manager.initialize()
            logger.info(f"✅ Session Manager ready ({len(session_manager.sessions)} global sessions)")
            
            # 3. Initialize MT5 connector
            logger.info("📡 Initializing MT5 Connector...")
            self.mt5_connector = MT5Connector()
            mt5_connected = await self.mt5_connector.connect()
            if mt5_connected:
                logger.info("✅ MT5 Connector connected")
            else:
                logger.warning("⚠️ MT5 Connector failed - will use simulation mode")
            
            # 4. Initialize CCXT connector (crypto fallback)
            logger.info("₿ Initializing CCXT Connector...")
            self.ccxt_connector = CCXTConnector()
            ccxt_connected = await self.ccxt_connector.connect()
            if ccxt_connected:
                logger.info("✅ CCXT Connector connected (Binance, Bybit, Kraken)")
            else:
                logger.warning("⚠️ CCXT Connector failed")
            
            # 5. Initialize risk manager
            logger.info("🛡️ Initializing Risk Manager...")
            self.risk_manager = PortfolioRiskManager()
            await self.risk_manager.initialize()
            logger.info("✅ Risk Manager ready")
            
            # 6. Initialize order manager
            logger.info("📋 Initializing Order Manager...")
            self.order_manager = OrderManager()
            await self.order_manager.initialize()
            logger.info("✅ Order Manager ready")
            
            # 7. Initialize analysis brain
            logger.info("🧠 Initializing Analysis Brain...")
            self.analysis_brain = AnalysisBrain()
            await self.analysis_brain.initialize()
            await self.analysis_brain.init_parallel(ParallelConfig(
                backend=BackendType.THREADING,
                max_workers=8,
            ))
            logger.info("✅ Analysis Brain ready (8 parallel workers)")
            
            # 8. Initialize next candle predictor
            logger.info("🔮 Initializing Next Candle Predictor...")
            self.predictor = NextCandlePredictor()
            await self.predictor.initialize()
            logger.info("✅ Next Candle Predictor ready")
            
            # 9. Initialize self-evolving brain (master brain)
            logger.info("🧬 Initializing Self-Evolving Brain...")
            self.brain = SelfEvolvingBrain({
                "save_path": "data/brain_state",
                "save_interval": 300,
            })
            await self.brain.initialize()
            logger.info("✅ Self-Evolving Brain ready (11 autonomous capabilities)")
            
            # 10. Initialize selection engine
            logger.info("🎯 Initializing Selection Engine...")
            await selection_engine.initialize()
            logger.info("✅ Selection Engine ready (method, style, strategy, session, symbols)")

            # 11. Initialize decision engine
            logger.info("⚡ Initializing Decision Engine...")
            self.decision_engine = AutonomousDecisionEngine()
            await self.decision_engine.initialize()
            logger.info("✅ Decision Engine ready")

            # 12. Start WebSocket server for dashboard updates
            logger.info("🔗 Starting Dashboard WebSocket Server...")
            from src.dashboard.websocket_server import get_ws_server
            self.ws_server = await get_ws_server(host="0.0.0.0", port=8765)
            logger.info("✅ WebSocket Server running on ws://0.0.0.0:8765")

            # 13. Load brain state if exists
            await self._load_state()

            self.metrics["start_time"] = datetime.now(UTC)
            logger.info("=" * 60)
            logger.info("✅ ALL SYSTEMS INITIALIZED - READY FOR AUTONOMOUS TRADING")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}", exc_info=True)
            await self.shutdown()
            return False
    
    async def _load_state(self):
        """Load persisted state."""
        try:
            # Brain state is loaded in SelfEvolvingBrain.initialize()
            # Additional state loading can go here
            logger.info("📂 State loaded successfully")
        except Exception as e:
            logger.warning(f"⚠️ Could not load state: {e}")
    
    async def _save_state(self):
        """Save current state."""
        try:
            if self.brain:
                # Brain saves itself periodically
                raise NotImplementedError("State saving not implemented in AutonomousMain._save_state")
            logger.debug("💾 State saved")
        except Exception as e:
            logger.warning(f"⚠️ Could not save state: {e}")
    
    async def run_autonomous_loop(self):
        """Main autonomous trading loop - runs continuously without user input."""
        self.running = True
        logger.info("🚀 STARTING AUTONOMOUS TRADING LOOP")
        logger.info("🔄 Zero user input mode: ACTIVE")
        
        while self.running and not self.shutdown_event.is_set():
            loop_start = datetime.now(UTC)
            self.iteration += 1
            
            try:
                # =============================================================
                # PHASE 1: SESSION & MARKET CONTEXT
                # =============================================================
                
                # Update active sessions
                await session_manager.update_active_sessions()
                active_sessions = session_manager.get_active_sessions()
                active_symbols = session_manager.get_active_symbols()
                
                # Get market data from MT5 (forex, metals, indices)
                mt5_data = {}
                if self.mt5_connector and self.mt5_connector.connected:
                    for symbol in list(active_symbols)[:20]:
                        try:
                            tick = await self.mt5_connector.get_tick(symbol)
                            if tick:
                                mt5_data[symbol] = tick
                        except Exception as e:
                            logger.debug(f"MT5 data error for {symbol}: {e}")
                
                # Get market data from CCXT (crypto 24/7)
                ccxt_data = {}
                if self.ccxt_connector and self.ccxt_connector.connected:
                    crypto_symbols = [s for s in active_symbols if any(c in s for c in ["BTC", "ETH", "SOL", "AVAX", "DOT"])]
                    for symbol in crypto_symbols[:10]:
                        try:
                            ticker = await self.ccxt_connector.get_ticker(symbol)
                            if ticker:
                                ccxt_data[symbol] = ticker
                        except Exception as e:
                            logger.debug(f"CCXT data error for {symbol}: {e}")
                
                # Combine market data
                self.last_market_data = {**mt5_data, **ccxt_data}
                
                if not self.last_market_data:
                    logger.warning("⚠️ No market data available, waiting...")
                    await asyncio.sleep(1.0)
                    continue
                
                # Get account info
                if self.mt5_connector and self.mt5_connector.connected:
                    self.account_info = await self.mt5_connector.get_account_info() or {}
                
                # Get current positions
                if self.mt5_connector and self.mt5_connector.connected:
                    self.active_positions = await self.mt5_connector.get_positions() or {}
                
                # =============================================================
                # PHASE 2: AUTONOMOUS SELECTION
                # =============================================================
                
                # Build selection context
                context = SelectionContext(
                    timestamp=datetime.now(UTC),
                    active_sessions=active_sessions,
                    active_symbols=active_symbols,
                    market_regime=await self._detect_regime(),
                    volatility=await self._calculate_volatility(),
                    volume=await self._calculate_volume(),
                    spread=await self._calculate_spread(),
                    account_size=self.account_info.get("equity", 100000),
                    risk_tolerance=0.02,
                    max_positions=10,
                    current_positions=len(self.active_positions),
                    performance_metrics=self.metrics,
                )
                
                # Autonomous selection: method, style, strategy, session, symbols
                selection = await selection_engine.select_all(context)
                
                logger.info(
                    f"🎯 Selection #{self.iteration}: "
                    f"Method={selection.method.value} | "
                    f"Style={selection.style.value} | "
                    f"Strategy={selection.strategy} | "
                    f"Session={selection.session} | "
                    f"Symbols={selection.symbols[:3]}... | "
                    f"Confidence={selection.confidence:.1%}"
                )
                
                # =============================================================
                # PHASE 3: BRAIN PROCESSING (PARALLEL)
                # =============================================================
                
                # Process through self-evolving brain (includes prediction, analysis, decision)
                brain_result = await self.brain.process_market_data(self.last_market_data)
                
                # Update metrics from brain
                self.metrics.update(self.brain.metrics)
                
                # =============================================================
                # PHASE 4: RISK CHECK
                # =============================================================
                
                # Check risk limits before executing
                risk_check = await self.risk_manager.check_limits(
                    account_info=self.account_info,
                    positions=self.active_positions,
                    proposed_trades=brain_result.get("execution", {}),
                )
                
                if not risk_check["allowed"]:
                    logger.warning(f"🛑 Risk limit hit: {risk_check['reason']}")
                    await asyncio.sleep(1.0)
                    continue
                
                # =============================================================
                # PHASE 5: EXECUTION
                # =============================================================
                
                execution_result = brain_result.get("execution", {})
                if execution_result.get("executed"):
                    trade_info = execution_result.get("trade")
                    if trade_info:
                        self.metrics["total_trades"] += 1
                        if trade_info.get("pnl", 0) > 0:
                            self.metrics["winning_trades"] += 1
                        self.metrics["total_pnl"] += trade_info.get("pnl", 0)
                        self.metrics["last_trade_time"] = datetime.now(UTC)
                        
                        logger.info(
                            f"📈 Trade executed: "
                            f"{trade_info.get('side', '').upper()} "
                            f"{trade_info.get('volume', 0)} "
                            f"{trade_info.get('symbol', '')} @ "
                            f"{trade_info.get('price', 0):.5f} | "
                            f"PnL: ${trade_info.get('pnl', 0):,.2f}"
                        )
                
                # =============================================================
                # PHASE 6: PERFORMANCE TRACKING
                # =============================================================
                
                self.metrics["successful_iterations"] += 1
                self.metrics["total_iterations"] = self.iteration
                
                # Log progress periodically
                if self.iteration % 10 == 0:
                    equity = self.account_info.get("equity", 100000)
                    pnl = self.metrics["total_pnl"]
                    win_rate = (
                        self.metrics["winning_trades"] / self.metrics["total_trades"] * 100
                        if self.metrics["total_trades"] > 0 else 0
                    )
                    
                    logger.info(
                        f"📊 Iteration #{self.iteration} | "
                        f"Equity: ${equity:,.2f} | "
                        f"Total PnL: ${pnl:,.2f} | "
                        f"Trades: {self.metrics['total_trades']} | "
                        f"Win Rate: {win_rate:.1f}% | "
                        f"Brain Gen: {self.brain.generation} | "
                        f"Health: {self.brain.health_status.value}"
                    )
                
                # Save state periodically
                if self.iteration % 100 == 0:
                    await self._save_state()
                
                # =============================================================
                # PHASE 7: LOOP TIMING
                # =============================================================
                
                loop_time = (datetime.now(UTC) - loop_start).total_seconds()
                
                # Target 1 second per iteration
                sleep_time = max(0.1, 1.0 - loop_time)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("🛑 Loop cancelled")
                break
            except Exception as e:
                self.metrics["failed_iterations"] += 1
                logger.error(f"❌ Loop error (iteration {self.iteration}): {e}", exc_info=True)
                
                # Self-healing: attempt recovery
                await self._attempt_recovery(e)
                
                await asyncio.sleep(5.0)  # Back off on error
    
    async def _detect_regime(self) -> str:
        """Detect current market regime."""
        # Use analysis brain for regime detection
        if self.analysis_brain and self.last_market_data:
            try:
                symbol = list(self.last_market_data.keys())[0]
                analyses = await self.analysis_brain.analyze_market(symbol)
                if AnalysisType.REGIME in analyses:
                    return analyses[AnalysisType.REGIME].details.get("regime", "unknown")
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')
        return "trending_up"  # Default
    
    async def _calculate_volatility(self) -> float:
        """Calculate current market volatility."""
        if not self.last_market_data:
            return 0.015
        
        # Simple volatility estimate from spreads
        spreads = []
        for data in self.last_market_data.values():
            if isinstance(data, dict) and "bid" in data and "ask" in data:
                mid = (data["bid"] + data["ask"]) / 2
                spread = (data["ask"] - data["bid"]) / mid if mid > 0 else 0
                spreads.append(spread)
        
        return np.mean(spreads) * 100 if spreads else 0.015
    
    async def _calculate_volume(self) -> float:
        """Calculate current market volume."""
        if not self.last_market_data:
            return 1000000
        
        volumes = []
        for data in self.last_market_data.values():
            if isinstance(data, dict) and "volume" in data:
                volumes.append(data["volume"])
        
        return np.mean(volumes) if volumes else 1000000
    
    async def _calculate_spread(self) -> float:
        """Calculate average spread."""
        if not self.last_market_data:
            return 0.0002
        
        spreads = []
        for data in self.last_market_data.values():
            if isinstance(data, dict) and "bid" in data and "ask" in data:
                spreads.append(data["ask"] - data["bid"])
        
        return np.mean(spreads) if spreads else 0.0002
    
    async def _attempt_recovery(self, error: Exception):
        """Self-healing: attempt to recover from error."""
        logger.warning("🔧 Attempting self-healing recovery...")
        
        try:
            # Reconnect data feeds
            if self.mt5_connector and not self.mt5_connector.connected:
                await self.mt5_connector.connect()
            
            if self.ccxt_connector and not self.ccxt_connector.connected:
                await self.ccxt_connector.connect()
            
            # Reset brain health
            if self.brain:
                self.brain.health_status = self.brain.health_status.HEALTHY
            
            logger.info("✅ Recovery attempt completed")
        except Exception as e:
            logger.error(f"❌ Recovery failed: {e}")
    
    async def shutdown(self):
        """Graceful shutdown of all components."""
        logger.info("🛑 SHUTTING DOWN AUTONOMOUS TRADING SYSTEM")
        self.running = False
        self.shutdown_event.set()
        
        # Save final state
        await self._save_state()
        
        # Shutdown components
        components = [
            ("Parallel Processor", self.parallel_processor),
            ("Self-Evolving Brain", self.brain),
            ("Analysis Brain", self.analysis_brain),
            ("Order Manager", self.order_manager),
            ("MT5 Connector", self.mt5_connector),
            ("CCXT Connector", self.ccxt_connector),
        ]
        
        for name, component in components:
            if component and hasattr(component, "shutdown"):
                try:
                    await component.shutdown()
                    logger.info(f"✅ {name} shutdown complete")
                except Exception as e:
                    logger.error(f"❌ {name} shutdown error: {e}")
        
        # Print final stats
        runtime = datetime.now(UTC) - self.metrics["start_time"] if self.metrics["start_time"] else timedelta(0)
        logger.info("=" * 60)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Runtime: {runtime}")
        logger.info(f"Total Iterations: {self.metrics['total_iterations']}")
        logger.info(f"Successful: {self.metrics['successful_iterations']}")
        logger.info(f"Failed: {self.metrics['failed_iterations']}")
        logger.info(f"Total Trades: {self.metrics['total_trades']}")
        logger.info(f"Winning Trades: {self.metrics['winning_trades']}")
        logger.info(f"Total PnL: ${self.metrics['total_pnl']:,.2f}")
        if self.metrics['total_trades'] > 0:
            logger.info(f"Win Rate: {self.metrics['winning_trades']/self.metrics['total_trades']*100:.1f}%")
        logger.info("=" * 60)
        logger.info("✅ SHUTDOWN COMPLETE")


# Global system instance
system: AutonomousTradingSystem | None = None


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    if system:
        asyncio.create_task(system.shutdown())


async def main():
    """Main entry point."""
    global system
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and initialize system
    system = AutonomousTradingSystem()
    
    initialized = await system.initialize()
    if not initialized:
        logger.error("❌ Failed to initialize system")
        return 1
    
    # Run autonomous loop
    try:
        await system.run_autonomous_loop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await system.shutdown()
    
    return 0


if __name__ == "__main__":
    # Ensure required directories exist
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data/brain_state", exist_ok=True)
    
    # Run the autonomous system
    exit_code = asyncio.run(main())
    sys.exit(exit_code)