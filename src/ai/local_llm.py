"""
Elite Autonomous Quantum Trading System - Local LLM Integration
Privacy-first financial LLMs (Ollama, FinGPT, FinLlama) with RAG
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    OPENAI_COMPATIBLE = "openai_compatible"
    CUSTOM = "custom"


class ModelType(Enum):
    FINGPT = "fingpt"
    FINLLAMA = "finllama"
    LLAMA2 = "llama2"
    LLAMA3 = "llama3"
    MISTRAL = "mistral"
    MIXTRAL = "mixtral"
    CODELLAMA = "codellama"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    """LLM configuration."""
    provider: LLMProvider = LLMProvider.OLLAMA
    base_url: str = "http://localhost:11434"
    model: str = "fingpt"
    model_type: ModelType = ModelType.FINGPT
    temperature: float = 0.1
    max_tokens: int = 4096
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    timeout: int = 120
    api_key: str = ""
    system_prompt: str = ""
    rag_enabled: bool = True
    rag_top_k: int = 5


@dataclass
class Message:
    """Chat message."""
    role: str  # system, user, assistant
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM response."""
    content: str
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    finish_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class LocalLLMClient:
    """
    Local LLM client for privacy-first financial analysis.
    
    Features:
    - Ollama/LM Studio/OpenAI-compatible API support
    - Financial model specialization (FinGPT, FinLlama)
    - RAG (Retrieval-Augmented Generation) for market data
    - Streaming responses
    - Function calling for trading actions
    - Conversation memory management
    """
    
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self.session: aiohttp.ClientSession | None = None
        self.conversation_history: deque[Message] = deque(maxlen=50)
        self.rag_documents: list[dict[str, Any]] = []
        self.rag_embeddings: dict[str, list[float]] = {}
        
        # Function definitions for trading
        self.functions = [
            {
                "name": "get_market_data",
                "description": "Get current market data for symbol",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Trading symbol (e.g., EURUSD, SPY, BTCUSD)"},
                        "timeframe": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"]}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_technical_indicators",
                "description": "Get technical indicators for symbol",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "indicators": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "analyze_sentiment",
                "description": "Analyze market sentiment for symbol",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_economic_calendar",
                "description": "Get upcoming economic events",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "default": 7},
                        "importance": {"type": "string", "enum": ["high", "medium", "low"]}
                    }
                }
            },
            {
                "name": "execute_trade",
                "description": "Execute a trade order",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "quantity": {"type": "number"},
                        "order_type": {"type": "string", "enum": ["market", "limit", "stop"]},
                        "price": {"type": "number"},
                        "stop_loss": {"type": "number"},
                        "take_profit": {"type": "number"}
                    },
                    "required": ["symbol", "side", "quantity"]
                }
            },
            {
                "name": "get_portfolio",
                "description": "Get current portfolio positions and PnL",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "get_risk_metrics",
                "description": "Get current risk metrics",
                "parameters": {"type": "object", "properties": {}}
            }
        ]
        
        logger.info(f"LocalLLMClient initialized: {self.config.provider.value}/{self.config.model}")
    
    async def initialize(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        
        # Test connection
        try:
            await self._check_connection()
            logger.info(f"LLM connected: {self.config.model}")
        except Exception as e:
            logger.warning(f"LLM connection test failed: {e}")
    
    async def _check_connection(self):
        """Check LLM server connection."""
        if self.config.provider == LLMProvider.OLLAMA:
            async with self.session.get(f"{self.config.base_url}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    logger.info(f"Available models: {models}")
        elif self.config.provider in [LLMProvider.LMSTUDIO, LLMProvider.OPENAI_COMPATIBLE]:
            async with self.session.get(f"{self.config.base_url}/v1/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    logger.info(f"Available models: {models}")
    
    async def chat(
        self,
        messages: list[Message],
        use_rag: bool = True,
        functions: list[dict] | None = None,
        stream: bool = False
    ) -> LLMResponse:
        """Send chat completion request."""
        start_time = datetime.now(UTC)
        
        # Prepare messages
        formatted_messages = []
        
        # Add system prompt
        if self.config.system_prompt:
            formatted_messages.append({"role": "system", "content": self.config.system_prompt})
        
        # Add RAG context if enabled
        if use_rag and self.rag_documents:
            rag_context = self._build_rag_context(messages[-1].content if messages else "")
            if rag_context:
                formatted_messages.append({"role": "system", "content": f"Relevant context:\n{rag_context}"})
        
        # Add conversation history
        for msg in messages[-(self.config.max_tokens // 100):]:  # Approximate token limit
            formatted_messages.append({"role": msg.role, "content": msg.content})
        
        # Prepare request
        payload = {
            "model": self.config.model,
            "messages": formatted_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": stream
        }
        
        if functions:
            payload["functions"] = functions
            payload["function_call"] = "auto"
        elif self.functions:
            payload["functions"] = self.functions
            payload["function_call"] = "auto"
        
        # Send request
        try:
            if self.config.provider == LLMProvider.OLLAMA:
                response = await self._ollama_chat(payload, stream)
            else:
                response = await self._openai_compatible_chat(payload, stream)
            
            latency = (datetime.now(UTC) - start_time).total_seconds() * 1000
            response.latency_ms = latency
            return response
            
        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            return LLMResponse(
                content=f"Error: {e!s}",
                model=self.config.model,
                latency_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
                finish_reason="error"
            )
    
    async def _ollama_chat(self, payload: dict, stream: bool) -> LLMResponse:
        """Ollama API chat."""
        url = f"{self.config.base_url}/api/chat"
        
        # Convert to Ollama format
        ollama_payload = {
            "model": payload["model"],
            "messages": payload["messages"],
            "stream": stream,
            "options": {
                "temperature": payload.get("temperature", 0.1),
                "top_p": payload.get("top_p", 0.9),
                "top_k": self.config.top_k,
                "repeat_penalty": self.config.repeat_penalty,
                "num_predict": payload.get("max_tokens", 4096)
            }
        }
        
        async with self.session.post(url, json=ollama_payload) as resp:
            if resp.status != 200:
                raise Exception(f"Ollama error: {resp.status}")
            
            if stream:
                # Handle streaming
                full_content = ""
                async for line in resp.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                full_content += data["message"]["content"]
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                
                return LLMResponse(
                    content=full_content,
                    model=self.config.model,
                    finish_reason="stop"
                )
            else:
                data = await resp.json()
                return LLMResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=self.config.model,
                    tokens_used=data.get("eval_count", 0),
                    finish_reason=data.get("done_reason", "stop")
                )
    
    async def _openai_compatible_chat(self, payload: dict, stream: bool) -> LLMResponse:
        """OpenAI-compatible API chat."""
        url = f"{self.config.base_url}/v1/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        async with self.session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"API error: {resp.status} - {text}")
            
            data = await resp.json()
            choice = data["choices"][0]
            
            return LLMResponse(
                content=choice["message"]["content"],
                model=data.get("model", self.config.model),
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"function_call": choice["message"].get("function_call")}
            )
    
    def _build_rag_context(self, query: str, max_docs: int = 5) -> str:
        """Build RAG context from relevant documents."""
        if not self.rag_documents:
            return ""
        
        # Simple keyword-based relevance (in production, use embeddings)
        query_words = set(query.lower().split())
        scored_docs = []
        
        for doc in self.rag_documents:
            content = doc.get("content", "").lower()
            score = sum(1 for word in query_words if word in content)
            if score > 0:
                scored_docs.append((score, doc))
        
        # Sort by relevance
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        # Build context
        context_parts = []
        for _, doc in scored_docs[:max_docs]:
            context_parts.append(f"[{doc.get('source', 'unknown')}] {doc.get('content', '')[:500]}")
        
        return "\n\n".join(context_parts)
    
    def add_rag_document(self, content: str, source: str, metadata: dict | None = None):
        """Add document to RAG knowledge base."""
        self.rag_documents.append({
            "content": content,
            "source": source,
            "metadata": metadata or {},
            "added_at": datetime.now(UTC).isoformat()
        })
        # Keep bounded
        if len(self.rag_documents) > 1000:
            self.rag_documents = self.rag_documents[-1000:]
    
    def add_market_data_to_rag(self, symbol: str, data: dict):
        """Add market data to RAG."""
        content = f"Market data for {symbol}: {json.dumps(data, default=str)}"
        self.add_rag_document(content, f"market_data_{symbol}", {"symbol": symbol, "type": "market_data"})
    
    def add_news_to_rag(self, title: str, content: str, source: str, symbols: list[str]):
        """Add news article to RAG."""
        full_content = f"Title: {title}\nContent: {content}\nSymbols: {', '.join(symbols)}"
        self.add_rag_document(full_content, f"news_{source}", {"symbols": symbols, "type": "news"})
    
    async def analyze_market(
        self,
        symbol: str,
        market_data: dict,
        technical_data: dict | None = None,
        news_data: list[dict] | None = None
    ) -> dict[str, Any]:
        """Comprehensive market analysis using LLM."""
        
        # Add data to RAG
        self.add_market_data_to_rag(symbol, market_data)
        if technical_data:
            self.add_rag_document(
                f"Technical indicators for {symbol}: {json.dumps(technical_data, default=str)}",
                f"technical_{symbol}"
            )
        if news_data:
            for article in news_data:
                self.add_news_to_rag(
                    article.get("title", ""),
                    article.get("content", ""),
                    article.get("source", "unknown"),
                    article.get("symbols", [symbol])
                )
        
        # Create analysis prompt
        prompt = f"""
Analyze the following market data for {symbol} and provide:
1. Market regime assessment (trending/ranging/volatile)
2. Key support/resistance levels
3. Trend direction and strength
4. Risk assessment
5. Recommended action (buy/sell/hold) with confidence
6. Suggested position sizing
7. Stop loss and take profit levels

Market Data:
{json.dumps(market_data, default=str, indent=2)}

Technical Data:
{json.dumps(technical_data, default=str, indent=2) if technical_data else "Not available"}

News:
{json.dumps(news_data, default=str, indent=2) if news_data else "Not available"}

Respond in JSON format with the analysis.
"""
        
        messages = [
            Message(role="system", content="You are an expert quantitative trader and market analyst. Provide concise, actionable analysis in JSON format."),
            Message(role="user", content=prompt)
        ]
        
        response = await self.chat(messages, use_rag=True)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"raw_analysis": response.content, "error": "Failed to parse JSON"}
    
    async def generate_trading_plan(
        self,
        account_info: dict,
        risk_tolerance: float,
        available_symbols: list[str],
        current_positions: list[dict]
    ) -> dict[str, Any]:
        """Generate comprehensive trading plan."""
        
        prompt = f"""
Generate a comprehensive trading plan based on:

Account Info:
{json.dumps(account_info, default=str)}

Risk Tolerance: {risk_tolerance * 100}%
Available Symbols: {', '.join(available_symbols)}
Current Positions: {json.dumps(current_positions, default=str)}

Provide:
1. Position sizing rules
2. Risk management parameters
3. Session preferences
4. Strategy allocation
4. Symbol-specific recommendations
5. Entry/exit criteria
6. Portfolio hedging suggestions

Respond in JSON format.
"""
        
        messages = [
            Message(role="system", content="You are a portfolio manager and risk officer. Create detailed, executable trading plans."),
            Message(role="user", content=prompt)
        ]
        
        response = await self.chat(messages)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"raw_plan": response.content, "error": "Failed to parse JSON"}
    
    def get_conversation_history(self) -> list[Message]:
        """Get conversation history."""
        return list(self.conversation_history)
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
    
    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()


class FinancialLLM:
    """
    High-level financial LLM interface with specialized capabilities.
    """
    
    def __init__(self, config: LLMConfig | None = None):
        self.client = LocalLLMClient(config)
        self.analysis_cache: dict[str, tuple[datetime, dict]] = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def initialize(self):
        await self.client.initialize()
    
    async def quick_analysis(self, symbol: str, market_data: dict) -> dict:
        """Quick market analysis."""
        cache_key = f"{symbol}_{hash(str(market_data))}"
        
        if cache_key in self.analysis_cache:
            cached_time, cached_result = self.analysis_cache[cache_key]
            if (datetime.now(UTC) - cached_time).total_seconds() < self.cache_ttl:
                return cached_result
        
        result = await self.client.analyze_market(symbol, market_data)
        self.analysis_cache[cache_key] = (datetime.now(UTC), result)
        return result
    
    async def sentiment_analysis(self, symbol: str, news: list[dict]) -> dict:
        """Analyze sentiment from news."""
        prompt = f"""
Analyze the sentiment of the following news for {symbol}:

News Articles:
{json.dumps(news, default=str, indent=2)}

Provide:
1. Overall sentiment (bullish/bearish/neutral) with confidence
2. Key themes
3. Potential price impact
4. Time horizon of impact

Respond in JSON.
"""
        
        messages = [Message(role="user", content=prompt)]
        response = await self.client.chat(messages)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"sentiment": "neutral", "confidence": 0.5, "raw": response.content}
    
    async def strategy_recommendation(
        self,
        symbol: str,
        regime: str,
        volatility: float,
        account_size: float,
        risk_tolerance: float
    ) -> dict:
        """Get strategy recommendation."""
        prompt = f"""
Recommend optimal trading strategy for:

Symbol: {symbol}
Market Regime: {regime}
Volatility: {volatility:.2%}
Account Size: ${account_size:,.2f}
Risk Tolerance: {risk_tolerance:.2%}

Consider: trend following, mean reversion, breakout, carry trade, volatility strategies.
Provide: strategy name, parameters, expected win rate, risk/reward, confidence.
JSON format.
"""
        
        messages = [Message(role="user", content=prompt)]
        response = await self.client.chat(messages)
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"strategy": "trend_following", "confidence": 0.5, "raw": response.content}
    
    async def close(self):
        await self.client.close()


# Global instance
financial_llm = FinancialLLM()


async def get_financial_llm(config: LLMConfig | None = None) -> FinancialLLM:
    """Get or create global financial LLM."""
    global financial_llm
    if config:
        financial_llm = FinancialLLM(config)
        await financial_llm.initialize()
    return financial_llm