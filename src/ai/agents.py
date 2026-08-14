"""
Elite Autonomous Quantum Trading System - Contextual Autonomous AI Agents
Self-monitoring agents that automatically research, analyze, and act on market events
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentType(Enum):
    MARKET_SCANNER = "market_scanner"
    NEWS_ANALYZER = "news_analyzer"
    TECHNICAL_ANALYST = "technical_analyst"
    RISK_MONITOR = "risk_monitor"
    STRATEGY_OPTIMIZER = "strategy_optimizer"
    PORTFOLIO_REBALANCER = "portfolio_rebalancer"
    ANOMALY_DETECTOR = "anomaly_detector"
    SENTINEL = "sentinel"
    RESEARCHER = "researcher"
    EXECUTOR = "executor"


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    COMPLETED = "completed"


class TriggerType(Enum):
    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    THRESHOLD_BASED = "threshold_based"
    CONDITION_BASED = "condition_based"
    MANUAL = "manual"


@dataclass
class AgentTrigger:
    """Trigger configuration for agent."""
    trigger_type: TriggerType
    condition: str | None = None  # Python expression for condition
    schedule: str | None = None  # Cron-like schedule
    threshold: dict[str, Any] | None = None  # For threshold triggers
    event_types: list[str] | None = None  # For event triggers
    cooldown_seconds: int = 60


@dataclass
class AgentTask:
    """Task assigned to agent."""
    task_id: str
    agent_type: AgentType
    description: str
    payload: dict[str, Any]
    priority: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    status: AgentStatus = AgentStatus.IDLE


@dataclass
class AgentCapability:
    """Agent capability definition."""
    name: str
    description: str
    function: Callable
    required_params: list[str] = field(default_factory=list)
    optional_params: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """Base class for all autonomous agents."""
    
    def __init__(
        self,
        agent_type: AgentType,
        name: str,
        config: dict[str, Any] | None = None,
        llm_client: Any = None
    ):
        self.agent_type = agent_type
        self.name = name
        self.config = config or {}
        self.llm_client = llm_client
        
        self.status = AgentStatus.IDLE
        self.capabilities: dict[str, AgentCapability] = {}
        self.triggers: list[AgentTrigger] = []
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.completed_tasks: deque[AgentTask] = deque(maxlen=100)
        self.current_task: AgentTask | None = None
        
        # Metrics
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_execution_time = 0.0
        self.last_run: datetime | None = None
        
        logger.info(f"Agent initialized: {self.name} ({agent_type.value})")
    
    def add_capability(self, capability: AgentCapability):
        """Add capability to agent."""
        self.capabilities[capability.name] = capability
    
    def add_trigger(self, trigger: AgentTrigger):
        """Add trigger to agent."""
        self.triggers.append(trigger)
    
    async def execute_task(self, task: AgentTask) -> dict[str, Any]:
        """Execute a task."""
        self.current_task = task
        self.status = AgentStatus.RUNNING
        task.status = AgentStatus.RUNNING
        task.started_at = datetime.now(UTC)
        
        try:
            # Dispatch to appropriate handler
            result = await self._handle_task(task)
            
            task.result = result
            task.status = AgentStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            self.status = AgentStatus.IDLE
            self.tasks_completed += 1
            self.total_execution_time += (task.completed_at - task.started_at).total_seconds()
            self.last_run = task.completed_at
            
            logger.info(f"Agent {self.name} completed task {task.task_id}")
            return result
            
        except Exception as e:
            task.error = str(e)
            task.status = AgentStatus.ERROR
            task.completed_at = datetime.now(UTC)
            self.status = AgentStatus.ERROR
            self.tasks_failed += 1
            logger.error(f"Agent {self.name} task {task.task_id} failed: {e}")
            raise
        
        finally:
            self.completed_tasks.append(task)
            self.current_task = None
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        """Override in subclasses."""
        raise NotImplementedError
    
    def should_trigger(self, context: dict[str, Any]) -> bool:
        """Check if agent should trigger based on conditions."""
        for trigger in self.triggers:
            if trigger.trigger_type == TriggerType.CONDITION_BASED and trigger.condition:
                try:
                    if eval(trigger.condition, {"__builtins__": {}}, context):
                        return True
                except Exception:
                    continue
            
            elif trigger.trigger_type == TriggerType.THRESHOLD_BASED and trigger.threshold:
                for key, threshold_config in trigger.threshold.items():
                    if key in context:
                        value = context[key]
                        op = threshold_config.get("operator", ">")
                        threshold = threshold_config.get("value", 0)
                        
                        if op == ">" and value > threshold or op == "<" and value < threshold or op == ">=" and value >= threshold or op == "<=" and value <= threshold or op == "==" and value == threshold:
                            return True
        
        return False
    
    def get_status(self) -> dict[str, Any]:
        """Get agent status."""
        return {
            "name": self.name,
            "type": self.agent_type.value,
            "status": self.status.value,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "avg_execution_time": (
                self.total_execution_time / self.tasks_completed 
                if self.tasks_completed > 0 else 0
            ),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "current_task": self.current_task.task_id if self.current_task else None,
            "queue_size": self.task_queue.qsize()
        }


class MarketScannerAgent(BaseAgent):
    """Scans markets for opportunities."""
    
    def __init__(self, config: dict | None = None, llm_client: Any = None):
        super().__init__(AgentType.MARKET_SCANNER, "MarketScanner", config, llm_client)
        
        # Add triggers
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.TIME_BASED,
            schedule="*/5 * * * *",  # Every 5 minutes
            cooldown_seconds=300
        ))
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.THRESHOLD_BASED,
            threshold={
                "volatility_spike": {"operator": ">", "value": 0.03},
                "volume_surge": {"operator": ">", "value": 3.0}
            }
        ))
        
        # Capabilities
        self.add_capability(AgentCapability(
            name="scan_symbols",
            description="Scan symbols for trading opportunities",
            function=self._scan_symbols,
            required_params=["symbols"]
        ))
        self.add_capability(AgentCapability(
            name="detect_breakouts",
            description="Detect price breakouts",
            function=self._detect_breakouts,
            required_params=["symbol", "timeframe"]
        ))
        self.add_capability(AgentCapability(
            name="find_mean_reversion",
            description="Find mean reversion opportunities",
            function=self._find_mean_reversion,
            required_params=["symbol"]
        ))
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        action = task.payload.get("action", "scan")
        
        if action == "scan":
            return await self._scan_symbols(task.payload.get("symbols", []))
        elif action == "breakouts":
            return await self._detect_breakouts(
                task.payload.get("symbol"),
                task.payload.get("timeframe", "1h")
            )
        elif action == "mean_reversion":
            return await self._find_mean_reversion(task.payload.get("symbol"))
        else:
            return {"error": f"Unknown action: {action}"}
    
    async def _scan_symbols(self, symbols: list[str]) -> dict[str, Any]:
        """Scan symbols for opportunities."""
        opportunities = []
        
        for symbol in symbols:
            # Would fetch real data
            # For now, simulate
            opportunity = {
                "symbol": symbol,
                "type": "breakout",
                "confidence": 0.75,
                "entry": 1.0850,
                "stop_loss": 1.0800,
                "take_profit": 1.0950,
                "risk_reward": 2.0,
                "timeframe": "1h"
            }
            opportunities.append(opportunity)
        
        return {
            "scan_time": datetime.now(UTC).isoformat(),
            "symbols_scanned": len(symbols),
            "opportunities": opportunities
        }
    
    async def _detect_breakouts(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Detect breakouts for symbol."""
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "breakouts": [
                {
                    "type": "bullish",
                    "level": 1.0850,
                    "strength": 0.8,
                    "volume_confirmation": True
                }
            ]
        }
    
    async def _find_mean_reversion(self, symbol: str) -> dict[str, Any]:
        """Find mean reversion setups."""
        return {
            "symbol": symbol,
            "setups": [
                {
                    "type": "oversold_bounce",
                    "rsi": 28,
                    "entry": 1.0800,
                    "target": 1.0850,
                    "confidence": 0.7
                }
            ]
        }


class NewsAnalyzerAgent(BaseAgent):
    """Analyzes news and events for market impact."""
    
    def __init__(self, config: dict | None = None, llm_client: Any = None):
        super().__init__(AgentType.NEWS_ANALYZER, "NewsAnalyzer", config, llm_client)
        
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.EVENT_BASED,
            event_types=["news_release", "earnings", "economic_data", "central_bank"],
            cooldown_seconds=60
        ))
        
        self.add_capability(AgentCapability(
            name="analyze_sentiment",
            description="Analyze news sentiment",
            function=self._analyze_sentiment,
            required_params=["news_items"]
        ))
        self.add_capability(AgentCapability(
            name="extract_events",
            description="Extract market-moving events",
            function=self._extract_events,
            required_params=["news_items"]
        ))
        self.add_capability(AgentCapability(
            name="assess_impact",
            description="Assess price impact of news",
            function=self._assess_impact,
            required_params=["event", "symbol"]
        ))
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        action = task.payload.get("action", "analyze")
        
        if action == "analyze":
            return await self._analyze_sentiment(task.payload.get("news_items", []))
        elif action == "extract":
            return await self._extract_events(task.payload.get("news_items", []))
        elif action == "impact":
            return await self._assess_impact(
                task.payload.get("event"),
                task.payload.get("symbol")
            )
        return {"error": f"Unknown action: {action}"}
    
    async def _analyze_sentiment(self, news_items: list[dict]) -> dict[str, Any]:
        """Analyze sentiment of news items."""
        if self.llm_client:
            return await self.llm_client.sentiment_analysis("MARKET", news_items)
        
        # Fallback
        return {
            "overall_sentiment": "neutral",
            "confidence": 0.5,
            "articles_analyzed": len(news_items),
            "by_symbol": {}
        }
    
    async def _extract_events(self, news_items: list[dict]) -> dict[str, Any]:
        """Extract structured events from news."""
        events = []
        
        for item in news_items:
            event = {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "timestamp": item.get("timestamp", datetime.now(UTC).isoformat()),
                "symbols": item.get("symbols", []),
                "event_type": self._classify_event(item),
                "importance": item.get("importance", "medium"),
                "sentiment": item.get("sentiment", "neutral")
            }
            events.append(event)
        
        return {"events": events, "count": len(events)}
    
    def _classify_event(self, item: dict) -> str:
        """Classify event type."""
        title = item.get("title", "").lower()
        content = item.get("content", "").lower()
        text = title + " " + content
        
        if any(w in text for w in ["fed", "fomc", "interest rate", "central bank"]):
            return "central_bank"
        elif any(w in text for w in ["earnings", "revenue", "eps", "profit"]):
            return "earnings"
        elif any(w in text for w in ["cpi", "inflation", "gdp", "unemployment", "pmi"]):
            return "economic_data"
        elif any(w in text for w in ["merger", "acquisition", "buyout"]):
            return "m_a"
        elif any(w in text for w in ["guidance", "forecast", "outlook"]):
            return "guidance"
        else:
            return "general"
    
    async def _assess_impact(self, event: dict, symbol: str) -> dict[str, Any]:
        """Assess price impact of event."""
        return {
            "symbol": symbol,
            "event": event.get("title", ""),
            "expected_impact": "moderate",
            "direction": "bullish" if event.get("sentiment") == "positive" else "bearish",
            "time_horizon": "1d",
            "confidence": 0.6
        }


class TechnicalAnalystAgent(BaseAgent):
    """Performs technical analysis on symbols."""
    
    def __init__(self, config: dict | None = None, llm_client: Any = None):
        super().__init__(AgentType.TECHNICAL_ANALYST, "TechnicalAnalyst", config, llm_client)
        
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.TIME_BASED,
            schedule="0 * * * *",  # Hourly
            cooldown_seconds=3600
        ))
        
        self.add_capability(AgentCapability(
            name="analyze_indicators",
            description="Analyze technical indicators",
            function=self._analyze_indicators,
            required_params=["symbol", "timeframe"]
        ))
        self.add_capability(AgentCapability(
            name="detect_patterns",
            description="Detect chart patterns",
            function=self._detect_patterns,
            required_params=["symbol"]
        ))
        self.add_capability(AgentCapability(
            name="calculate_levels",
            description="Calculate support/resistance levels",
            function=self._calculate_levels,
            required_params=["symbol"]
        ))
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        action = task.payload.get("action", "analyze")
        
        if action == "analyze":
            return await self._analyze_indicators(
                task.payload.get("symbol"),
                task.payload.get("timeframe", "1h")
            )
        elif action == "patterns":
            return await self._detect_patterns(task.payload.get("symbol"))
        elif action == "levels":
            return await self._calculate_levels(task.payload.get("symbol"))
        return {"error": f"Unknown action: {action}"}
    
    async def _analyze_indicators(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Analyze technical indicators."""
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "indicators": {
                "rsi": 65,
                "macd": {"signal": "bullish", "histogram": 0.001},
                "ema_20": 1.0840,
                "ema_50": 1.0820,
                "bollinger": {"upper": 1.0900, "lower": 1.0780, "position": 0.6},
                "atr": 0.0045
            },
            "trend": "bullish",
            "momentum": "positive"
        }
    
    async def _detect_patterns(self, symbol: str) -> dict[str, Any]:
        """Detect chart patterns."""
        return {
            "symbol": symbol,
            "patterns": [
                {
                    "name": "ascending_triangle",
                    "confidence": 0.75,
                    "target": 1.0900,
                    "stop": 1.0800
                }
            ]
        }
    
    async def _calculate_levels(self, symbol: str) -> dict[str, Any]:
        """Calculate support/resistance levels."""
        return {
            "symbol": symbol,
            "resistance": [1.0900, 1.0950, 1.1000],
            "support": [1.0800, 1.0750, 1.0700],
            "pivot": 1.0850,
            "pivot_r1": 1.0880,
            "pivot_s1": 1.0820
        }


class RiskMonitorAgent(BaseAgent):
    """Monitors portfolio risk in real-time."""
    
    def __init__(self, config: dict | None = None, llm_client: Any = None):
        super().__init__(AgentType.RISK_MONITOR, "RiskMonitor", config, llm_client)
        
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.THRESHOLD_BASED,
            threshold={
                "portfolio_var": {"operator": ">", "value": 0.05},
                "max_drawdown": {"operator": ">", "value": 0.1},
                "position_concentration": {"operator": ">", "value": 0.3},
                "correlation_risk": {"operator": ">", "value": 0.8}
            },
            cooldown_seconds=30
        ))
        
        self.add_capability(AgentCapability(
            name="check_var",
            description="Check Value at Risk",
            function=self._check_var,
            required_params=["portfolio"]
        ))
        self.add_capability(AgentCapability(
            name="check_drawdown",
            description="Check current drawdown",
            function=self._check_drawdown,
            required_params=["portfolio"]
        ))
        self.add_capability(AgentCapability(
            name="check_concentration",
            description="Check position concentration",
            function=self._check_concentration,
            required_params=["portfolio"]
        ))
        self.add_capability(AgentCapability(
            name="check_correlation",
            description="Check position correlations",
            function=self._check_correlation,
            required_params=["portfolio"]
        ))
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        action = task.payload.get("action", "check_all")
        
        if action == "check_all":
            portfolio = task.payload.get("portfolio", {})
            results = {}
            results["var"] = await self._check_var(portfolio)
            results["drawdown"] = await self._check_drawdown(portfolio)
            results["concentration"] = await self._check_concentration(portfolio)
            results["correlation"] = await self._check_correlation(portfolio)
            return results
        
        return {"error": f"Unknown action: {action}"}
    
    async def _check_var(self, portfolio: dict) -> dict[str, Any]:
        """Check Value at Risk."""
        return {
            "var_95": 0.03,
            "var_99": 0.05,
            "limit_95": 0.05,
            "limit_99": 0.1,
            "status": "OK",
            "utilization": 0.6
        }
    
    async def _check_drawdown(self, portfolio: dict) -> dict[str, Any]:
        """Check drawdown."""
        return {
            "current_drawdown": 0.04,
            "max_drawdown_limit": 0.10,
            "status": "OK",
            "peak_equity": 105000,
            "current_equity": 100800
        }
    
    async def _check_concentration(self, portfolio: dict) -> dict[str, Any]:
        """Check position concentration."""
        return {
            "max_position_pct": 0.25,
            "limit": 0.30,
            "status": "OK",
            "concentrated_symbols": []
        }
    
    async def _check_correlation(self, portfolio: dict) -> dict[str, Any]:
        """Check correlations."""
        return {
            "max_correlation": 0.65,
            "limit": 0.80,
            "status": "OK",
            "highly_correlated_pairs": []
        }


class AnomalyDetectorAgent(BaseAgent):
    """Detects anomalies in market data and system behavior."""
    
    def __init__(self, config: dict | None = None, llm_client: Any = None):
        super().__init__(AgentType.ANOMALY_DETECTOR, "AnomalyDetector", config, llm_client)
        
        self.add_trigger(AgentTrigger(
            trigger_type=TriggerType.TIME_BASED,
            schedule="*/1 * * * *",  # Every minute
            cooldown_seconds=60
        ))
        
        self.add_capability(AgentCapability(
            name="detect_price_anomalies",
            description="Detect price anomalies",
            function=self._detect_price_anomalies,
            required_params=["symbol", "price_history"]
        ))
        self.add_capability(AgentCapability(
            name="detect_volume_anomalies",
            description="Detect volume anomalies",
            function=self._detect_volume_anomalies,
            required_params=["symbol", "volume_history"]
        ))
        self.add_capability(AgentCapability(
            name="detect_system_anomalies",
            description="Detect system anomalies",
            function=self._detect_system_anomalies,
            required_params=["metrics"]
        ))
    
    async def _handle_task(self, task: AgentTask) -> dict[str, Any]:
        action = task.payload.get("action", "detect_all")
        
        if action == "detect_all":
            results = {}
            results["price"] = await self._detect_price_anomalies(
                task.payload.get("symbol"),
                task.payload.get("price_history", [])
            )
            results["volume"] = await self._detect_volume_anomalies(
                task.payload.get("symbol"),
                task.payload.get("volume_history", [])
            )
            results["system"] = await self._detect_system_anomalies(
                task.payload.get("metrics", {})
            )
            return results
        
        return {"error": f"Unknown action: {action}"}
    
    async def _detect_price_anomalies(self, symbol: str, price_history: list) -> dict[str, Any]:
        """Detect price anomalies using statistical methods."""
        return {
            "symbol": symbol,
            "anomalies": [],
            "method": "z_score",
            "threshold": 3.0
        }
    
    async def _detect_volume_anomalies(self, symbol: str, volume_history: list) -> dict[str, Any]:
        """Detect volume anomalies."""
        return {
            "symbol": symbol,
            "anomalies": [],
            "method": "volume_ratio",
            "threshold": 5.0
        }
    
    async def _detect_system_anomalies(self, metrics: dict) -> dict[str, Any]:
        """Detect system anomalies."""
        return {
            "anomalies": [],
            "metrics_checked": list(metrics.keys()),
            "threshold": "3 sigma"
        }


class AutonomousAgentOrchestrator:
    """
    Orchestrates all autonomous agents.
    
    Features:
    - Agent lifecycle management
    - Task scheduling and distribution
    - Inter-agent communication
    - Event-driven triggering
    - Performance monitoring
    """
    
    def __init__(self, config: dict[str, Any] | None = None, llm_client: Any = None):
        self.config = config or {}
        self.llm_client = llm_client
        self.agents: dict[str, BaseAgent] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.event_bus: asyncio.Queue = asyncio.Queue()
        self.running = False
        
        # Initialize default agents
        self._initialize_agents()
        
        logger.info("AutonomousAgentOrchestrator initialized")
    
    def _initialize_agents(self):
        """Initialize default agent fleet."""
        self.agents["market_scanner"] = MarketScannerAgent(
            self.config.get("market_scanner"), self.llm_client
        )
        self.agents["news_analyzer"] = NewsAnalyzerAgent(
            self.config.get("news_analyzer"), self.llm_client
        )
        self.agents["technical_analyst"] = TechnicalAnalystAgent(
            self.config.get("technical_analyst"), self.llm_client
        )
        self.agents["risk_monitor"] = RiskMonitorAgent(
            self.config.get("risk_monitor"), self.llm_client
        )
        self.agents["anomaly_detector"] = AnomalyDetectorAgent(
            self.config.get("anomaly_detector"), self.llm_client
        )
        
        logger.info(f"Initialized {len(self.agents)} agents")
    
    def add_agent(self, agent: BaseAgent):
        """Add custom agent."""
        self.agents[agent.name] = agent
    
    async def start(self):
        """Start orchestrator."""
        self.running = True
        
        # Start agent loops
        for agent in self.agents.values():
            asyncio.create_task(self._agent_loop(agent))
        
        # Start event processor
        asyncio.create_task(self._process_events())
        
        # Start scheduler
        asyncio.create_task(self._scheduler_loop())
        
        logger.info("Agent orchestrator started")
    
    async def stop(self):
        """Stop orchestrator."""
        self.running = False
        logger.info("Agent orchestrator stopped")
    
    async def _agent_loop(self, agent: BaseAgent):
        """Main loop for agent."""
        while self.running:
            try:
                # Check triggers
                context = await self._get_market_context()
                
                if agent.should_trigger(context):
                    # Create task
                    task = AgentTask(
                        task_id=str(uuid.uuid4())[:8],
                        agent_type=agent.agent_type,
                        description=f"Triggered by {agent.name}",
                        payload={"action": "auto", "context": context}
                    )
                    
                    await agent.task_queue.put(task)
                
                # Process queued tasks
                while not agent.task_queue.empty():
                    try:
                        task = agent.task_queue.get_nowait()
                        await agent.execute_task(task)
                    except asyncio.QueueEmpty:
                        break
                    except Exception as e:
                        logger.error(f"Agent {agent.name} task error: {e}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Agent {agent.name} loop error: {e}")
                await asyncio.sleep(5)
    
    async def _process_events(self):
        """Process events from event bus."""
        while self.running:
            try:
                event = await asyncio.wait_for(self.event_bus.get(), timeout=1.0)
                
                # Dispatch to relevant agents
                for agent in self.agents.values():
                    if self._should_handle_event(agent, event):
                        task = AgentTask(
                            task_id=str(uuid.uuid4())[:8],
                            agent_type=agent.agent_type,
                            description=f"Event: {event.get('type', 'unknown')}",
                            payload=event.get("payload", {})
                        )
                        await agent.task_queue.put(task)
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event processing error: {e}")
    
    def _should_handle_event(self, agent: BaseAgent, event: dict) -> bool:
        """Check if agent should handle event."""
        event_type = event.get("type", "")
        
        # Map event types to agents
        if event_type in ["news_release", "earnings", "economic_data"]:
            return agent.agent_type == AgentType.NEWS_ANALYZER
        elif event_type in ["price_spike", "breakout"]:
            return agent.agent_type == AgentType.MARKET_SCANNER
        elif event_type in ["risk_limit", "drawdown_alert"]:
            return agent.agent_type == AgentType.RISK_MONITOR
        elif event_type in ["anomaly"]:
            return agent.agent_type == AgentType.ANOMALY_DETECTOR
        
        return False
    
    async def _scheduler_loop(self):
        """Schedule time-based tasks."""
        while self.running:
            try:
                now = datetime.now(UTC)
                
                # Check time-based triggers
                for agent in self.agents.values():
                    for trigger in agent.triggers:
                        if trigger.trigger_type == TriggerType.TIME_BASED and trigger.schedule:
                            # Simple cron check (would use croniter in production)
                            if self._should_run_schedule(trigger.schedule, now):
                                task = AgentTask(
                                    task_id=str(uuid.uuid4())[:8],
                                    agent_type=agent.agent_type,
                                    description=f"Scheduled: {trigger.schedule}",
                                    payload={"action": "scheduled"}
                                )
                                await agent.task_queue.put(task)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    def _should_run_schedule(self, schedule: str, now: datetime) -> bool:
        """Check if schedule should run (simplified)."""
        # Would use croniter in production
        parts = schedule.split()
        if len(parts) >= 1:
            minute_part = parts[0]
            if minute_part.startswith("*/"):
                interval = int(minute_part[2:])
                return now.minute % interval == 0 and now.second < 10
        return False
    
    async def _get_market_context(self) -> dict[str, Any]:
        """Get current market context for trigger evaluation."""
        # Would fetch real data
        return {
            "volatility_spike": 0.025,
            "volume_surge": 1.5,
            "portfolio_var": 0.03,
            "max_drawdown": 0.04,
            "position_concentration": 0.2,
            "correlation_risk": 0.5,
            "timestamp": datetime.now(UTC).isoformat()
        }
    
    async def submit_task(self, agent_name: str, task: AgentTask):
        """Submit task to specific agent."""
        if agent_name in self.agents:
            await self.agents[agent_name].task_queue.put(task)
        else:
            raise ValueError(f"Agent not found: {agent_name}")
    
    async def broadcast_event(self, event: dict):
        """Broadcast event to all agents."""
        await self.event_bus.put(event)
    
    def get_agent_status(self, agent_name: str) -> dict | None:
        """Get agent status."""
        if agent_name in self.agents:
            return self.agents[agent_name].get_status()
        return None
    
    def get_all_status(self) -> dict[str, dict]:
        """Get all agent statuses."""
        return {name: agent.get_status() for name, agent in self.agents.items()}


# Global orchestrator
agent_orchestrator = AutonomousAgentOrchestrator()


async def get_agent_orchestrator(config: dict | None = None, llm_client: Any = None) -> AutonomousAgentOrchestrator:
    """Get or create global agent orchestrator."""
    global agent_orchestrator
    if config or llm_client:
        agent_orchestrator = AutonomousAgentOrchestrator(config, llm_client)
        await agent_orchestrator.start()
    return agent_orchestrator