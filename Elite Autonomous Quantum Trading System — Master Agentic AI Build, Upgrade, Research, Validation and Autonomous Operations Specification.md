# ELITE AUTONOMOUS QUANTUM TRADING SYSTEM
## Master Agentic AI Engineering, Research, Trading, Validation and Autonomous Operations Instruction

### 1. PRIMARY DIRECTIVE

Transform the existing trading application into a **fully autonomous, multi-asset, AI-driven algorithmic trading system** named:

**Elite Autonomous Quantum Trading System**

The system must operate autonomously after startup.

The only mandatory human action is:

**START AUTONOMOUS TRADER**

After startup, the system must independently:

- collect and validate market data;
- detect available markets and active trading sessions;
- select tradable symbols;
- perform technical, quantitative, fundamental, sentiment, macro, order-flow and market-structure analysis;
- select trading styles;
- select trading methods;
- select trading strategies;
- select timeframes;
- generate predictions;
- evaluate probabilities and confidence;
- construct trades;
- calculate position size;
- calculate entry, stop-loss, take-profit, trailing-stop and trailing-target parameters;
- manage open positions;
- monitor execution quality;
- manage portfolio risk;
- learn from outcomes;
- adapt models and parameters;
- detect errors;
- repair recoverable failures;
- continuously evaluate its own decisions;
- update the dashboard;
- maintain complete audit trails.

Do not require the user to manually select individual symbols, strategies, trading styles, sessions, indicators, trades, lot sizes, risk parameters, or execution decisions.

The system is an **autonomous decision-making and execution platform**, not merely a signal generator.

---

# 2. NON-NEGOTIABLE ENGINEERING PRINCIPLES

## 2.1 Zero-incomplete-code requirement

Perform an absolute verification that the entire application contains:

- zero stubs;
- zero placeholders;
- zero dummy implementations;
- zero fake integrations;
- zero simulated implementations masquerading as production implementations;
- zero empty functions;
- zero unimplemented interfaces;
- zero unresolved TODO/FIXME items;
- zero "implement later" sections;
- zero dead modules;
- zero unreachable critical components;
- zero missing dependencies;
- zero broken imports;
- zero undocumented feature gaps.

Every requested feature must either:

1. be fully implemented and tested, or
2. be explicitly recorded as technically impossible/unavailable because of an external limitation, with the exact limitation documented.

Never silently omit a requested capability.

---

## 2.2 Autonomous operation

Once started, the orchestration layer must operate continuously without requiring human intervention for normal operation.

The architecture must support:

- autonomous research;
- autonomous analysis;
- autonomous strategy selection;
- autonomous execution;
- autonomous risk management;
- autonomous monitoring;
- autonomous learning;
- autonomous recovery;
- autonomous optimization.

Human intervention must not be required for routine decisions.

Emergency safety controls may exist, but they must be treated as safety mechanisms rather than normal decision-making.

---

# 3. INITIAL PROJECT AUDIT

Before modifying anything, perform a complete recursive audit of the project.

Inspect:

- every directory;
- every source file;
- every configuration file;
- every dependency;
- every database;
- every model;
- every dashboard component;
- every MT5 component;
- every API integration;
- every data source;
- every execution component;
- every strategy;
- every indicator;
- every test;
- every script;
- every build configuration;
- every deployment configuration.

Build a complete dependency and architecture graph.

Identify:

- missing features;
- missing modules;
- duplicated modules;
- obsolete modules;
- incompatible modules;
- broken modules;
- incomplete features;
- disconnected components;
- performance bottlenecks;
- security weaknesses;
- data-quality problems;
- execution risks;
- architectural weaknesses;
- scalability limitations;
- race conditions;
- concurrency problems;
- memory leaks;
- failed recovery paths;
- incorrect calculations;
- incorrect risk calculations;
- incorrect lot calculations;
- incorrect stop calculations;
- stale data;
- synchronization errors;
- timing errors;
- chart errors;
- dashboard errors;
- MT5 integration problems;
- model failures;
- false-positive signals;
- false-negative signals;
- look-ahead bias;
- data leakage;
- overfitting;
- survivorship bias;
- unrealistic backtest assumptions;
- excessive latency;
- API failures;
- broker failures;
- order rejection conditions;
- session-detection errors.

Produce a machine-readable and human-readable **Granular TODO / Remediation Register**.

The register must contain at minimum:

- ID;
- severity;
- category;
- affected component;
- description;
- root cause;
- dependency;
- proposed solution;
- implementation status;
- test status;
- verification status;
- regression status;
- timestamp;
- responsible subsystem/agent.

---

# 4. AUTONOMOUS REMEDIATION LOOP

Execute the following loop continuously:

```text
SCAN
→ IDENTIFY
→ CLASSIFY
→ PRIORITIZE
→ DESIGN FIX
→ IMPLEMENT
→ TEST
→ VERIFY
→ REGRESSION TEST
→ PERFORMANCE TEST
→ SECURITY TEST
→ UPDATE TODO REGISTER
→ RE-SCAN
```

Fix issues one-by-one while continuously updating the TODO register.

Do not merely report defects.

Where technically possible, detect and repair defects autonomously.

Repeat until the system reaches production-grade stability.

---

# 5. AGENTIC AI ARCHITECTURE

Implement a multi-brain architecture.

At minimum, separate the following autonomous agents:

## 5.1 Research Brain

Responsibilities:

- web research;
- market research;
- strategy research;
- academic research;
- financial-market research;
- alternative-data research;
- technology research;
- competitor/platform research;
- API research;
- library research;
- regulatory research;
- market-structure research.

The Research Brain must continuously identify potentially valuable:

- strategies;
- indicators;
- datasets;
- execution techniques;
- market signals;
- alternative data;
- models;
- analytical methods;
- risk techniques;
- optimization methods.

---

## 5.2 Analyst Brain

Responsibilities:

- market analysis;
- multi-timeframe analysis;
- technical analysis;
- price-action analysis;
- chart-pattern recognition;
- indicator analysis;
- volatility analysis;
- liquidity analysis;
- order-flow analysis;
- market-structure analysis;
- sentiment analysis;
- macro analysis;
- fundamental analysis;
- intermarket analysis;
- correlation analysis;
- regime detection;
- statistical analysis.

---

## 5.3 Prediction Brain

Responsibilities:

- next-candle prediction;
- directional prediction;
- volatility prediction;
- probability estimation;
- expected-return estimation;
- expected-range estimation;
- regime prediction;
- trade-quality prediction.

Use live and historical data.

Do not optimize solely for raw directional accuracy.

Measure:

- accuracy;
- precision;
- recall;
- F1;
- calibration;
- Brier score;
- expected value;
- false-positive rate;
- false-negative rate;
- prediction stability;
- performance by regime;
- performance by symbol;
- performance by timeframe.

The original target of 99% next-candle prediction accuracy must be treated as an **aspirational validation target**, not a guaranteed outcome. The system must never fabricate or inflate performance to claim 99% success.

---

## 5.4 Strategy Brain

Responsibilities:

- evaluate all available strategies;
- score strategies;
- select appropriate strategies;
- combine compatible strategies;
- reject unsuitable strategies;
- dynamically weight strategy votes;
- detect strategy degradation;
- disable deteriorating strategies;
- reactivate strategies after validated recovery.

---

## 5.5 Risk Brain

Responsibilities:

- portfolio risk;
- position sizing;
- exposure;
- leverage;
- drawdown;
- correlation;
- VaR;
- Expected Shortfall;
- stop-loss validation;
- take-profit validation;
- margin;
- liquidity;
- concentration;
- overnight risk;
- news risk;
- execution risk;
- broker risk;
- systemic risk.

The Risk Brain must have veto authority over trade execution.

---

## 5.6 Execution Brain

Responsibilities:

- order generation;
- order routing;
- order-book analysis;
- liquidity analysis;
- execution timing;
- order type selection;
- slippage estimation;
- transaction-cost analysis;
- execution-quality measurement;
- retry handling;
- rejection handling;
- partial-fill handling;
- cancellation;
- modification;
- execution reconciliation.

---

## 5.7 Orchestrator

The Orchestrator must operate between all major brains.

Architecture:

```text
Research Brain
      │
      ▼
Data / Feature Layer
      │
      ▼
Analysis Brain
      │
      ▼
Prediction Brain
      │
      ▼
Strategy Brain
      │
      ▼
Risk Brain
      │
      ▼
Execution Brain
      │
      ▼
Trade / Market Feedback
      │
      ▼
Learning / Evaluation Layer
      │
      └──────────────► Orchestrator
```

The Orchestrator must coordinate all agents while preventing conflicting decisions.

---

# 6. SELF-LEARNING / SELF-IMPROVEMENT

Implement continuous:

- self-learning;
- self-training;
- self-adjustment;
- self-evaluation;
- self-correction;
- self-healing;
- self-fixing;
- self-testing;
- self-optimization;
- self-evolution.

Every completed trade must become structured feedback.

For every trade record:

- market state;
- session;
- symbol;
- strategy;
- style;
- timeframe;
- indicators;
- features;
- predictions;
- probabilities;
- decision rationale;
- entry;
- stop;
- target;
- position size;
- execution conditions;
- slippage;
- spread;
- outcome;
- PnL;
- maximum favorable excursion;
- maximum adverse excursion;
- time in trade;
- exit reason;
- market regime;
- news environment.

Use this information as future training data.

Maintain a continuously growing historical **case library**.

When similar market conditions occur, retrieve relevant prior cases and incorporate them into analysis.

---

# 7. NEXT-CANDLE PREDICTION ENGINE

Implement a dedicated prediction subsystem.

Inputs must include, where available:

- OHLC;
- volume;
- spread;
- tick data;
- order-book data;
- indicators;
- volatility;
- market regime;
- session;
- intermarket relationships;
- macro information;
- news;
- sentiment;
- price action;
- liquidity;
- previous model predictions;
- previous prediction errors.

Generate:

- bullish probability;
- bearish probability;
- neutral probability;
- expected price range;
- confidence;
- uncertainty;
- expected volatility.

After the next candle closes:

1. compare prediction with reality;
2. record prediction error;
3. update performance metrics;
4. identify model weakness;
5. update parameters/model weights where appropriate;
6. store the case;
7. re-evaluate future predictions.

Do not use future data in prediction inputs.

Strictly prevent look-ahead bias.

---

# 8. TRADING STYLES

Implement automatic selection of:

1. Scalping
2. Day Trading
3. Swing Trading
4. Position Trading

The system must dynamically determine which style is appropriate for:

- symbol;
- market;
- timeframe;
- volatility;
- liquidity;
- regime;
- session;
- strategy;
- expected opportunity.

---

# 9. TRADING STRATEGIES

Implement, test, score and dynamically select all relevant requested strategies, including:

### Trend / Momentum

- Trend Following;
- Moving Average Crossover;
- Donchian Breakout;
- MACD Momentum;
- RSI/MACD Confluence;
- Ichimoku;
- Supertrend/HMA;
- Parabolic SAR/ADX;
- Linear Regression Slope;
- Aroon;
- Elder Impulse;
- True Strength Index;
- Williams %R;
- Ultimate Oscillator.

### Mean Reversion / Range

- Bollinger Band Mean Reversion;
- RSI Mean Reversion;
- Stochastic/Pivot Mean Reversion;
- VWAP Reversion;
- Coppock Reversion;
- Center of Gravity;
- RVI divergence;
- CCI-based range strategies.

### Volatility / Breakout

- Bollinger Volatility Breakout;
- Donchian/Turtle Breakout;
- Keltner Channel;
- ATR breakout;
- Volatility contraction/expansion.

### Institutional / Market Structure

- ICT;
- Smart Money Concepts;
- Order Flow;
- Volume Profile;
- Market Structure;
- Liquidity Sweeps;
- Institutional Accumulation/Distribution.

### Quantitative

- Statistical Arbitrage;
- Pairs Trading;
- Triangular Arbitrage;
- Cross-Exchange Arbitrage;
- Correlation Breakdown;
- Market Making;
- Basis Trading;
- Funding Rate Arbitrage.

### Macro / Fundamental

- Carry Trade;
- Central Bank Event Trading;
- Central Bank Liquidity Cycles;
- Macro commodity seasonality;
- FX intervention analysis;
- Yield and rate-cycle analysis;
- Fundamental/yield strategies.

### Crypto

- Funding-rate arbitrage;
- Cash-and-carry;
- Derivatives basis;
- Gamma-related strategies;
- Cross-exchange spreads;
- Liquidation-event strategies.

### Structural / Alternative

- Time-of-Day Structural Arbitrage;
- Intermarket Analysis;
- Sentiment-Based Models;
- Alternative Data Models;
- Whale / block-trade analysis where reliable legal data is available;
- Supply-chain / commodity information models;
- Event-driven models.

Strategies that require unavailable, restricted, proprietary, illegal, non-public, or non-reproducible information must not be faked. Implement lawful and technically supportable alternatives and document the limitation.

---

# 10. AUTOMATIC METHOD / STYLE / STRATEGY / SESSION / SYMBOL SELECTION

Implement an autonomous selection engine.

The engine must automatically determine:

```text
Best Market
→ Best Session
→ Best Symbol
→ Best Trading Style
→ Best Trading Method
→ Best Strategy
→ Best Timeframe
→ Best Entry Model
→ Best Risk Model
→ Best Execution Model
```

Selection must consider:

- probability;
- expected value;
- liquidity;
- volatility;
- spread;
- market regime;
- historical performance;
- current performance;
- correlation;
- transaction costs;
- execution quality;
- news;
- session;
- macro conditions;
- portfolio exposure.

---

# 11. MARKETS AND SESSIONS

Integrate all applicable markets.

At minimum support:

- Forex;
- Crypto;
- Equities;
- ETFs;
- Futures;
- Commodities;
- Metals;
- indices;
- options where market/broker data supports them;
- fixed income analytics where relevant data exists.

Support session detection for:

- Wellington;
- Sydney;
- Tokyo;
- Hong Kong;
- Singapore;
- Frankfurt;
- London;
- Zurich;
- New York;
- global equity sessions;
- US pre-market;
- US core;
- US after-hours;
- CME;
- ICE;
- Crypto 24/7.

Do not hard-code session schedules without accounting for:

- daylight-saving time;
- exchange holidays;
- broker-specific trading hours;
- market pauses;
- special sessions;
- early closes;
- unexpected closures.

Use an exchange/broker calendar where available.

---

# 12. SESSION ENGINE

Continuously detect:

- current active session;
- previous session;
- next session;
- overlapping sessions;
- session transitions;
- session closures;
- session-specific liquidity;
- session-specific volatility.

Display a three-row session timeline:

```text
PREVIOUS / PASSING SESSION
CURRENT ACTIVE SESSION
NEXT / COMING SESSION
```

Show:

- session name;
- start;
- end;
- elapsed time;
- remaining time;
- overlap;
- overlap start;
- overlap end;
- overlap remaining time;
- time-to-next-session.

Update in real time.

When the session changes:

1. recalculate tradable instruments;
2. recalculate liquidity;
3. recalculate strategy suitability;
4. recalculate risk;
5. update dashboard;
6. update watchlists;
7. update active trading universe.

Crypto remains eligible when traditional markets are closed, subject to liquidity and risk rules.

---

# 13. SYMBOL SELECTION

Automatically identify all symbols currently available and tradable.

Rank symbols using:

- liquidity;
- spread;
- volatility;
- opportunity;
- expected return;
- predicted probability;
- execution quality;
- strategy suitability;
- session suitability;
- correlation;
- portfolio exposure;
- risk/reward;
- trading costs.

Do not trade symbols merely because they are technically available.

---

# 14. TRADE PROBABILITY REQUIREMENT

Only execute a trade when the validated estimated probability of success is:

**> 60%**

The probability model must be empirically calibrated.

Do not use arbitrary or fabricated confidence scores.

When multiple symbols have materially equal qualifying probability and the system determines that additional trades improve portfolio-level expected value without violating total risk limits:

- expand the active trade allocation;
- distribute risk proportionally;
- maintain hard portfolio-level risk limits.

Never exceed the absolute portfolio risk ceiling merely because multiple symbols have equal probability.

---

# 15. ACTIVE TRADE LIMIT

Default maximum active trades:

**10**

Baseline allocation:

- Forex: 6;
- Metals: 2;
- Crypto: 2.

The allocation is dynamic.

The Risk Brain may redistribute capacity when justified by:

- expected value;
- liquidity;
- correlation;
- volatility;
- opportunity;
- market conditions.

---

# 16. PYRAMIDING

Initial trade size for a new symbol:

**0.01 lots**

Additional positions may be added only when:

- the existing position(s) for that symbol are profitable;
- all active positions for that symbol are profitable;
- the new position does not violate portfolio risk limits;
- market conditions remain favorable;
- strategy conditions remain valid;
- execution quality remains acceptable.

Use pyramiding only when mathematically justified.

For a qualifying pyramiding symbol, the normal per-symbol active-trade limit may be overridden.

However:

**The portfolio-level maximum risk limit must never be overridden.**

Position size must be recalculated after every addition.

---

# 17. RISK MANAGEMENT

Implement institutional-grade risk controls including:

- dynamic position sizing;
- ATR-based risk;
- volatility-adjusted sizing;
- drawdown control;
- daily loss circuit breaker;
- total portfolio exposure limits;
- per-symbol limits;
- strategy limits;
- correlation limits;
- leverage limits;
- margin limits;
- spread limits;
- liquidity filters;
- news filters;
- overnight protection;
- gap protection;
- execution-failure protection;
- broker-failure protection;
- emergency shutdown logic.

Implement:

- VaR;
- Expected Shortfall;
- stress testing;
- Monte Carlo simulation;
- scenario analysis;
- portfolio optimization;
- correlation matrices;
- regime-aware risk.

Support:

- Kelly;
- Fractional Kelly;
- Quarter-Kelly;
- volatility targeting;
- risk parity;
- Markowitz;
- Black-Litterman.

No sizing model may bypass hard risk controls.

---

# 18. ORDER AND EXECUTION MANAGEMENT

Implement an institutional-style EMS/OMS.

Include:

- market orders;
- limit orders;
- stop orders;
- stop-limit orders where supported;
- conditional orders;
- multi-leg orders;
- spread orders;
- trigger orders;
- order modification;
- cancellation;
- partial fills;
- rejection recovery;
- execution reconciliation.

Implement:

- CLOB/DOM;
- order-book analytics;
- market depth;
- footprint/volume analysis;
- execution routing;
- broker abstraction;
- transaction-cost analysis;
- slippage analysis;
- fill-quality measurement.

Support broker/exchange abstraction so the trading logic is not tightly coupled to a single venue.

---

# 19. MT5 INTEGRATION

Integrate an MT5 Expert Advisor.

The EA must:

- feed live market data;
- feed execution status;
- feed account information;
- feed trade status;
- receive autonomous execution commands where appropriate;
- display real-time HUD information;
- synchronize with the central trading engine;
- maintain heartbeat monitoring.

Preferred architecture:

```text
Trading System
      ↕
Integration / Execution Adapter
      ↕
MT5
      ↕
Broker
```

Where technically supported, use direct broker/API connectivity without requiring the MT5 GUI terminal to remain open.

Do not falsely claim terminal-independent MT5 execution if the underlying broker/API does not support it.

The EA must remain an execution/data/display adapter rather than becoming the primary intelligence layer.

---

# 20. SIMULATION MODE

The development/test environment is a demo account.

Set:

```text
SIMULATION_MODE = False
```

as the default, as explicitly requested.

However, enforce all production-grade risk controls regardless of demo/live status.

Do not interpret a demo account as permission to remove:

- risk checks;
- execution validation;
- reconciliation;
- logging;
- authentication;
- security;
- circuit breakers.

---

# 21. DATA INGESTION ARCHITECTURE

Build a provider-agnostic ingestion layer.

Support:

- REST;
- WebSocket;
- streaming feeds;
- tick data;
- OHLC;
- order book;
- news;
- fundamentals;
- macro;
- sentiment;
- alternative data.

Use:

- normalized schemas;
- timestamps in UTC;
- source identifiers;
- data quality scores;
- deduplication;
- gap detection;
- stale-data detection;
- outlier detection;
- source failover;
- reconciliation.

---

# 22. EXTERNAL DATA SOURCES

Integrate or evaluate:

- ICO Drops;
- DeFiLlama;
- Token Terminal;
- DropsTab;
- Farsight;
- CoinMarketCap;
- DriveWorth;
- Alpaca.

Also evaluate:

- Finazon;
- Twelve Data;
- Alpha Vantage;
- Alpaca;
- CoinMarketCap.

Every integration must have:

- authentication handling;
- rate-limit handling;
- retries;
- timeout handling;
- fallback providers;
- schema validation;
- freshness monitoring;
- source attribution;
- error logging.

---

# 23. WEB / RESEARCH INGESTION

Use lawful web/public data sources for:

- market research;
- strategy research;
- financial research;
- technology research;
- market structure;
- trading-platform capabilities.

Relevant requested sources include:

- The Trade News;
- WeMasterTrade;
- AcquaintSoft;
- Seat11A;
- Investopedia.

Do not blindly copy content.

Extract:

- concepts;
- features;
- workflows;
- design patterns;
- analytical methods;
- architecture ideas.

Do not copy proprietary code, copyrighted databases, trademarks, private information, credentials, or restricted content.

---

# 24. BLOOMBERG-STYLE TERMINAL CAPABILITIES

Create a Bloomberg-inspired professional terminal experience.

Reproduce functional concepts, not proprietary Bloomberg software or proprietary data.

Implement:

- command-driven navigation;
- global command bar;
- autocomplete;
- keyboard-first workflow;
- multi-panel workspace;
- tiled workspace;
- customizable layouts;
- real-time market information;
- macro analytics;
- fixed-income analytics;
- FX analytics;
- portfolio analytics;
- risk analytics;
- execution analytics;
- news;
- economic calendar;
- research;
- alternative data;
- AI-assisted investigation.

Include functional equivalents of:

- DES;
- YAS;
- ECO;
- WFX;
- PORT;
- NEWS;
- EMSX-style routing;
- FIX connectivity;
- RFQ;
- RFM;
- IOI;
- TCA;
- DOM.

---

# 25. TRADING-INNOVATION CAPABILITIES

Implement or evaluate support for:

- OEMS;
- CLOB;
- algorithmic trading;
- FIX;
- TCA;
- DMA;
- conditional orders;
- RFQ;
- RFM;
- IOI;
- portfolio trading;
- periodic auctions;
- ETF analytics;
- VIX analytics;
- dark-pool data where lawfully available;
- all-to-all trading concepts;
- systematic internaliser concepts;
- HFT infrastructure where technically and legally appropriate.

Do not fabricate access to venues that the configured broker or exchange does not provide.

---

# 26. ADVANCED MARKET ANALYTICS

Implement:

- chart analysis;
- indicator analysis;
- multi-timeframe analysis;
- order-flow analysis;
- volume profile;
- VWAP;
- liquidity;
- volatility;
- correlation;
- regime classification;
- market breadth;
- cross-asset relationships;
- macro relationships;
- yield curves;
- options analytics.

---

# 27. OPTIONS ANALYTICS

Where valid data exists, implement:

- option chains;
- implied volatility;
- volatility surface;
- term structure;
- Delta;
- Gamma;
- Vega;
- Theta;
- Rho where appropriate;
- Black-Scholes;
- scenario analysis.

---

# 28. BACKTESTING AND VALIDATION

Implement institutional backtesting.

Support:

- event-driven backtesting;
- tick-level testing;
- realistic spreads;
- slippage;
- commissions;
- financing;
- latency;
- partial fills;
- market impact approximations;
- walk-forward analysis;
- Monte Carlo;
- parameter sensitivity;
- robustness testing;
- out-of-sample testing.

Never optimize exclusively on historical in-sample performance.

Use:

```text
Train
→ Validate
→ Walk Forward
→ Out-of-Sample
→ Stress Test
→ Monte Carlo
→ Paper/Demo
→ Controlled Deployment
```

Prevent:

- look-ahead bias;
- data leakage;
- overfitting;
- survivorship bias;
- selection bias.

---

# 29. PORTFOLIO OPTIMIZATION

Implement:

- Markowitz;
- Sharpe optimization;
- risk parity;
- Black-Litterman;
- volatility targeting;
- correlation-aware allocation;
- drawdown-aware allocation;
- expected-shortfall optimization.

Use portfolio-level optimization rather than treating every trade independently.

---

# 30. MACHINE LEARNING / AI

Support an ensemble containing, where validated and useful:

- PyTorch;
- TensorFlow;
- Keras;
- XGBoost;
- LightGBM;
- CatBoost;
- Prophet;
- Darts;
- statsmodels;
- scikit-learn;
- tsfresh;
- transformers;
- BERT-based models;
- SentenceTransformers;
- NLP models;
- Bayesian models;
- reinforcement learning;
- regime models.

Do not add models merely to increase model count.

Each model must have:

- defined purpose;
- input schema;
- training pipeline;
- validation pipeline;
- performance metrics;
- drift monitoring;
- versioning;
- rollback capability.

---

# 31. CUSTOM LLM

Build a specialized financial AI/LLM layer.

Use:

- market data;
- historical trading data;
- news;
- public research;
- indicators;
- strategy outcomes;
- MT5 tick/history;
- trade journal;
- case library.

The LLM must not directly bypass deterministic risk controls.

The LLM can:

- analyze;
- summarize;
- classify;
- reason over context;
- identify relationships;
- generate hypotheses;
- assist strategy research;
- analyze charts;
- analyze news;
- explain model decisions.

Final execution must remain subject to deterministic validation and risk controls.

---

# 32. AI MEMORY

Implement persistent AI memory.

The memory system must support:

- short-term context;
- long-term knowledge;
- historical cases;
- strategy outcomes;
- symbol-specific behavior;
- market-regime cases;
- failure cases;
- successful cases;
- model-performance history.

Evaluate fast vector/database memory solutions, including the requested Tencent DB Agent memory where technically and legally appropriate.

Never store credentials or secrets in model memory.

---

# 33. MULTIPROCESSING AND HIGH-PERFORMANCE COMPUTING

Use parallel processing aggressively where beneficial.

The system must support:

- multiprocessing;
- process pools;
- vectorization;
- compiled extensions;
- Rust;
- C/C++;
- native numerical libraries;
- GPU acceleration where beneficial.

Use:

- `ProcessPoolExecutor`;
- multiprocessing;
- NumPy;
- Polars;
- CuPy;
- JAX;
- PyTorch;
- compiled Rust/C++ extensions.

Do not assume that maximum processor count is always optimal.

Benchmark:

- 6 workers;
- 12 workers;
- 20 workers;

and dynamically select the most efficient configuration.

Avoid thread oversubscription.

For network I/O, use asynchronous or multithreaded processing where appropriate.

For CPU-heavy work, prefer multiprocessing or native compiled execution.

Evaluate free-threaded CPython where stable and compatible.

---

# 34. LANGUAGE ARCHITECTURE

Use language based on workload.

### Python

Use for:

- research;
- analytics;
- backtesting;
- ML;
- data science;
- orchestration where appropriate.

### Rust / C++

Use for:

- critical execution path;
- high-performance computation;
- low-latency components;
- native extensions;
- high-frequency components.

### Go / Java

Use where appropriate for:

- backend services;
- APIs;
- messaging;
- infrastructure;
- concurrency-heavy services.

Do not introduce multiple languages without a measurable architectural benefit.

---

# 35. DATABASE ARCHITECTURE

Support appropriate databases for:

- time-series market data;
- trade history;
- portfolio data;
- feature storage;
- model metadata;
- audit logs;
- configuration;
- event data.

Evaluate:

- PostgreSQL;
- TimescaleDB;
- QuestDB;
- ClickHouse;
- DuckDB;
- Redis;
- Parquet;
- vector databases.

Use the correct datastore for the workload.

---

# 36. REQUESTED PYTHON LIBRARY ECOSYSTEM

Audit, evaluate and integrate useful functionality from the requested ecosystem, including:

- Airflow
- AkShare
- Altair
- AutoTS
- BeautifulSoup
- BERT
- Bokeh
- Boto3
- ChromaDB
- Click
- CuPy
- Darts
- Dask
- Datatable
- Django
- DuckDB
- EdgarTools
- FAISS
- FastAPI
- Flask
- Folium
- GPIO
- Gensim
- GeoPandas
- GitHub
- Great Expectations
- Hadoop
- JAX
- Kafka
- Kats
- Keras
- Kivy
- Koalas
- LangChain
- LangExtract
- LangGraph
- Lifelines
- LightGBM
- LiteLLM
- LlamaIndex
- Loguru
- Matplotlib
- Modin
- NLTK
- Neo4j
- NetworkX
- NumPy
- Octoparse
- OpenAI SDK
- OpenCV
- Pandera
- Paramiko
- Peewee
- Pinecone
- Pingouin
- Plotly
- Polars
- Polyglot
- Prophet
- PyCryptodome
- PyFolio
- PyMC
- PyScript
- PySerial
- PySpark
- PyStan
- PyTest
- PyTorch
- Pydantic
- Pygal
- Pygame
- PyO3
- QuantLib
- Ray
- RQ
- Rich
- Robyn
- Ruff
- SQLAlchemy
- SciPy / scikit ecosystem
- scikit-learn
- Scrapy
- Seaborn
- Selenium
- SentenceTransformers
- sktime
- Statsmodels
- SymPy
- TA-Lib
- TensorFlow
- TextBlob
- Textual
- TinyDB
- Tkinter
- Transformers
- Typer
- Vaex
- XGBoost
- Arrow
- Backtrader
- CatBoost
- ccxt
- Jupyter
- pandas
- pmdarima
- requests
- spaCy
- Theano
- tsfresh
- yFinance
- Rust via PyO3
- Zipline

For every library requested, perform this process:

```text
VERIFY AVAILABILITY
→ VERIFY COMPATIBILITY
→ VERIFY MAINTENANCE
→ IDENTIFY USE CASE
→ IMPLEMENT AT LEAST ONE MEANINGFUL CAPABILITY
→ TEST
→ BENCHMARK
→ DOCUMENT
```

Do not force an inappropriate library into the critical path merely to satisfy a checklist.

Where a requested library is obsolete, renamed, duplicated, unsupported, proprietary, incompatible, or otherwise unsuitable, record the finding and use the technically appropriate maintained alternative while preserving equivalent functionality.

---

# 37. DASHBOARD

Build a professional responsive Bloomberg-style dashboard.

Every dashboard module must be:

- responsive;
- interactive;
- real-time;
- performant;
- visually distinct;
- keyboard accessible;
- searchable;
- filterable;
- resizable;
- configurable.

Use vibrant but readable color schemes.

---

# 38. REQUIRED DASHBOARD TABS

Implement:

1. MAIN
2. GP
3. WEI
4. NEWS
5. ANR
6. CHART
7. SESS
8. DES
9. YAS
10. ECO
11. EMSX
12. SET
13. ING
14. FEAT
15. STRAT
16. RISK
17. ORD
18. LOG
19. MON
20. SEC
21. SAFE
22. PF
23. WATCH
24. MKT
25. SYM
26. AIC
27. CRAWL
28. TRADEBOOK
29. HELP
30. DEEP MARKET SENTIMENT
31. STOCK MARKET PREDICTOR

---

# 39. ORDER MANAGER SUB-TABS

Under Order Manager include:

- Order Book;
- Trade Book;
- Spread / Multi-Leg Orders;
- Trigger Orders.

---

# 40. PORTFOLIO MANAGER SUB-TABS

Include:

- Position Book;
- Holdings;
- Funds.

---

# 41. MARKET SUB-TABS

Include:

- Exchange Messages;
- Market Movers;
- Scanners;
- Fundamentals;
- Corporate Actions.

---

# 42. REQUIRED DASHBOARD INFORMATION

Display in real time:

- active trades;
- historical trades;
- live PnL;
- realized PnL;
- unrealized PnL;
- exposure;
- margin;
- free margin;
- risk;
- drawdown;
- portfolio allocation;
- symbols;
- indicators;
- active sessions;
- upcoming sessions;
- overlaps;
- model activity;
- agent status;
- brain status;
- background processes;
- CPU;
- memory;
- network;
- API connections;
- database status;
- execution latency;
- broker status;
- market-data status;
- model status;
- errors;
- warnings;
- alerts;
- audit events.

---

# 43. CONSOLE INTEGRATION

Move console/system output into the dashboard.

Provide a bottom-panel operational console containing:

- logs;
- warnings;
- errors;
- system events;
- execution events;
- agent messages;
- model events;
- data-ingestion events.

Allow filtering by:

- severity;
- subsystem;
- agent;
- timestamp;
- symbol;
- trade;
- execution ID.

---

# 44. SESSION DASHBOARD

The session panel must show:

- current session in the center;
- previous/passing session above;
- next/coming session below;
- timeline scale;
- start;
- end;
- remaining time;
- overlaps;
- overlap timing.

Support multiple overlapping sessions without visual collision.

Use dynamically sized text while maintaining readability.

---

# 45. CHARTING SYSTEM

Implement a FOSS charting solution comparable in usability to TradingView.

Provide:

- symbol selection;
- timeframe selection;
- zoom;
- pan;
- horizontal scaling;
- vertical scaling;
- draggable scale;
- crosshair;
- tooltips;
- indicators;
- overlays;
- drawings;
- trendlines;
- support/resistance;
- pivots;
- volume;
- volume profile;
- VWAP;
- session markers;
- trade markers;
- entry;
- exit;
- SL;
- TP;
- trailing levels.

Fix current chart problems, including:

- mouse-hover disorientation;
- incorrect candle alignment;
- incorrect candle timing;
- broken zoom;
- broken scaling;
- incorrect timeframe rendering.

Candle times must correspond exactly to the selected timeframe.

Examples:

- M1
- M5
- M15
- M30
- H1
- H4
- D1
- W1
- MN

---

# 46. LIVE TRADING CHART

Display:

- live market price;
- current candle;
- countdown to candle close;
- spread;
- volume;
- active orders;
- positions;
- strategy signals;
- probability;
- predicted next candle;
- market regime.

---

# 47. MT5 EA HUD

The MT5 EA must use distinguishable colors for:

- symbol;
- ticket;
- order type;
- entry;
- stop;
- target;
- trailing stop;
- trailing target;
- quantity;
- spread;
- session;
- strategy;
- status.

PnL:

- green when profitable;
- red when losing.

---

# 48. AUTHENTICATION AND SECURITY

Require authentication at application startup.

Require authentication and authorization before accessing:

- settings;
- configuration;
- credentials;
- security controls;
- sensitive trading controls.

Implement:

- MFA / 2FA;
- secure credential storage;
- token management;
- secret encryption;
- authorization roles;
- session management;
- audit logging.

Never expose credentials through:

- logs;
- UI;
- model prompts;
- model memory;
- source code;
- dashboards.

---

# 49. BROKER CONFIGURATION

Create a dedicated Broker Configuration module.

Support:

- broker credentials;
- account information;
- server;
- environment;
- trading permissions;
- symbol specifications;
- contract sizes;
- leverage;
- margin rules;
- minimum lot;
- maximum lot;
- lot step;
- spread limits;
- execution mode;
- order types;
- trading sessions.

---

# 50. SYMBOL CONFIGURATION

Create a dedicated symbol configuration module.

Display:

- symbol;
- asset class;
- exchange;
- contract size;
- tick size;
- tick value;
- spread;
- margin;
- minimum volume;
- volume step;
- maximum volume;
- session;
- liquidity;
- volatility;
- strategy compatibility.

---

# 51. DATA INGESTION TAB

Create an ING tab displaying:

- provider status;
- REST connections;
- WebSockets;
- tick rates;
- message rates;
- latency;
- dropped packets;
- stale feeds;
- errors;
- reconnects;
- historical synchronization;
- data quality.

---

# 52. FEATURE STORE

Create a FEAT tab for:

- feature names;
- feature values;
- feature distributions;
- feature importance;
- feature drift;
- normalization;
- missing values;
- feature version;
- model association.

---

# 53. STRATEGY ENGINE

Create STRAT tab displaying:

- active strategies;
- strategy scores;
- votes;
- weights;
- market regime;
- symbol compatibility;
- performance;
- recent outcomes;
- current recommendation;
- strategy activation/deactivation.

---

# 54. RISK MANAGER

Create RISK tab displaying:

- total risk;
- per-symbol risk;
- per-strategy risk;
- portfolio VaR;
- Expected Shortfall;
- drawdown;
- correlation;
- exposure;
- margin;
- circuit-breaker status.

---

# 55. MONITORING / ALERTS

Create MON tab for:

- CPU;
- memory;
- processes;
- threads;
- network;
- API health;
- broker health;
- database health;
- model health;
- latency;
- errors;
- alerts.

Support configurable notifications.

---

# 56. SECURITY / COMPLIANCE

Create SEC tab showing:

- authentication;
- MFA;
- active sessions;
- access events;
- credentials status;
- audit logs;
- security events;
- suspicious activity;
- configuration changes;
- trading authorization.

---

# 57. OVERNIGHT SAFETY

Create SAFE tab for:

- geopolitical risk;
- major news;
- market closure;
- rollover;
- gap risk;
- low-liquidity conditions;
- exchange closure;
- broker maintenance;
- overnight exposure;
- weekend exposure.

---

# 58. WATCHLIST

Create WATCH tab containing:

- all currently eligible symbols;
- heatmap;
- probability;
- volatility;
- liquidity;
- spread;
- regime;
- strategy;
- session;
- expected value;
- active signal.

---

# 59. AI / LLM CONTROL PANEL

Create AIC tab displaying:

- active models;
- model versions;
- model scores;
- training status;
- inference latency;
- feature count;
- learning parameters;
- attention configuration where applicable;
- memory status;
- drift;
- model health;
- fallback model.

---

# 60. WEBSITE CRAWLER / ALTERNATIVE DATA

Create CRAWL tab showing:

- source;
- status;
- last crawl;
- next crawl;
- records;
- errors;
- parsing status;
- sentiment;
- extracted entities;
- source reliability;
- freshness.

---

# 61. STOCK MARKET PREDICTOR

Create a dedicated predictor module.

Analyze:

- OHLC;
- SMA;
- EMA;
- technical indicators;
- sentiment;
- volatility;
- trend;
- macro conditions.

Generate:

- forecast curves;
- directional probabilities;
- expected range;
- confidence;
- uncertainty.

---

# 62. DEEP MARKET SENTIMENT

Create a dedicated sentiment engine.

Analyze:

- news;
- social information;
- macro announcements;
- public filings;
- analyst language;
- market positioning where reliable data exists.

Use:

- BERT;
- Transformers;
- spaCy;
- NLTK;
- TextBlob;
- SentenceTransformers.

Produce:

- sentiment score;
- sentiment direction;
- sentiment confidence;
- entity impact;
- symbol impact;
- sector impact;
- market impact.

---

# 63. KEYBOARD COMMAND SYSTEM

Implement keyboard shortcuts and command navigation for:

```text
MAIN
GP
WEI
NEWS
ANR
CHART
SESS
DES
YAS
ECO
EMSX
SET
ING
FEAT
STRAT
RISK
ORD
LOG
MON
SEC
SAFE
PF
WATCH
MKT
SYM
AIC
CRAWL
TRADEBOOK
HELP
```

Implement:

- global command bar;
- autocomplete;
- keyboard navigation;
- shortcut customization;
- command history.

---

# 64. HELP SYSTEM

Create comprehensive HELP documentation containing:

- system overview;
- architecture;
- trading logic;
- strategies;
- dashboard guide;
- tab guide;
- keyboard shortcuts;
- authentication;
- configuration;
- risk controls;
- execution;
- error messages;
- troubleshooting;
- emergency actions;
- recovery procedures;
- FAQ;
- tutorials;
- operational handbook.

Do not omit relevant operational information.

---

# 65. LOGGING AND AUDIT

Maintain immutable, timestamped logs for:

- data;
- analysis;
- model outputs;
- strategy decisions;
- risk decisions;
- order decisions;
- execution;
- portfolio changes;
- configuration changes;
- authentication;
- system events;
- failures;
- recovery;
- autonomous modifications.

Every autonomous trade must be explainable from the audit trail.

---

# 66. PERFORMANCE ENGINEERING

Continuously profile:

- CPU;
- memory;
- disk;
- GPU;
- network;
- IPC;
- database;
- model inference;
- strategy computation;
- order routing;
- dashboard rendering.

Identify bottlenecks automatically.

Benchmark before and after optimization.

Never sacrifice correctness or risk controls merely for speed.

---

# 67. TESTING REQUIREMENTS

Implement:

- unit tests;
- integration tests;
- system tests;
- regression tests;
- end-to-end tests;
- data-quality tests;
- model tests;
- strategy tests;
- risk tests;
- execution tests;
- concurrency tests;
- stress tests;
- chaos tests;
- recovery tests;
- security tests;
- performance tests.

Test:

- API failure;
- broker failure;
- network failure;
- stale data;
- malformed data;
- missing candles;
- duplicate ticks;
- rejected orders;
- partial fills;
- disconnects;
- database failure;
- process crash;
- model crash;
- dashboard crash;
- corrupted state;
- session changes;
- rapid volatility;
- spread spikes;
- market closure.

---

# 68. CHAOS / RESILIENCE TESTING

Randomly disrupt components during controlled testing.

Examples:

- terminate processes;
- disconnect data feeds;
- corrupt temporary state;
- delay messages;
- simulate missing ticks;
- simulate broker rejection;
- simulate high latency;
- simulate API rate limits;
- simulate database outage.

The system must recover automatically where safe.

Every failure and recovery must be logged.

---

# 69. SELF-HEALING

Implement automated recovery procedures for:

- service crashes;
- connection failures;
- stale data;
- broken subprocesses;
- failed models;
- invalid state;
- temporary API failures;
- database connection failures.

Never automatically resume trading after a severe unresolved risk state.

Escalate to a safety state where necessary.

---

# 70. ZERO-USER-DECISION TRADING LOOP

The autonomous trading loop should conceptually operate as:

```text
MARKET DATA
→ DATA VALIDATION
→ SESSION DETECTION
→ SYMBOL UNIVERSE
→ FEATURE GENERATION
→ MARKET REGIME
→ MULTI-TIMEFRAME ANALYSIS
→ SENTIMENT / MACRO
→ STRATEGY EVALUATION
→ PREDICTION
→ PROBABILITY
→ PORTFOLIO OPTIMIZATION
→ RISK VALIDATION
→ EXECUTION PLANNING
→ ORDER EXECUTION
→ MONITORING
→ POSITION MANAGEMENT
→ EXIT
→ OUTCOME ANALYSIS
→ LEARNING
→ MODEL UPDATE
→ SYSTEM EVALUATION
→ REPEAT
```

---

# 71. TRADE DECISION GATE

Every trade must pass:

```text
Data Valid?
AND
Market Open?
AND
Symbol Tradable?
AND
Liquidity Acceptable?
AND
Spread Acceptable?
AND
Strategy Valid?
AND
Prediction Valid?
AND
Probability > 60%?
AND
Expected Value Positive?
AND
Risk Acceptable?
AND
Portfolio Exposure Acceptable?
AND
Correlation Acceptable?
AND
Margin Acceptable?
AND
Execution Quality Acceptable?
AND
No Safety Block?
```

Only then may the Execution Brain submit an order.

---

# 72. TRADE LIFECYCLE

For every trade:

```text
DISCOVER
→ SCORE
→ SELECT
→ SIZE
→ VALIDATE
→ EXECUTE
→ MONITOR
→ ADJUST
→ SCALE/PYRAMID IF ELIGIBLE
→ EXIT
→ RECONCILE
→ EVALUATE
→ LEARN
```

---

# 73. CASE-BASED LEARNING

Whenever multiple symbols produce similar qualifying signals simultaneously:

- record the event;
- record the selected trades;
- record rejected candidates;
- track relative outcomes;
- store market state;
- compare prediction versus actual outcome;
- store the event as a future case study.

When the same pattern occurs in the future, retrieve comparable historical cases and use them as part of the decision process.

---

# 74. STRATEGY PERFORMANCE GOVERNANCE

Maintain individual performance records for:

- strategy;
- style;
- symbol;
- session;
- timeframe;
- asset class;
- market regime;
- model;
- execution venue.

Calculate:

- win rate;
- expectancy;
- Sharpe;
- Sortino;
- drawdown;
- profit factor;
- average win;
- average loss;
- MFE;
- MAE;
- latency;
- slippage;
- trade frequency;
- stability.

Automatically reduce or suspend strategies when validated degradation exceeds configured thresholds.

---

# 75. VERSIONING

Version:

- application;
- configuration;
- strategy;
- model;
- dataset;
- feature set;
- trading rules;
- risk engine;
- execution engine.

Every live decision must identify the exact versions used.

Maintain a changelog.

Never overwrite historical versions without traceability.

---

# 76. CONFIGURATION GOVERNANCE

All important parameters must be:

- centralized;
- schema-validated;
- versioned;
- auditable;
- testable.

Prevent invalid configuration from reaching execution.

---

# 77. DASHBOARD NAVIGATION

Add a dropdown selector for dashboard tabs.

Also provide keyboard navigation.

Allow:

- tab search;
- favorites;
- recently opened tabs;
- keyboard shortcuts;
- customizable layout.

---

# 78. APPLICATION BRANDING

Rename the application to:

**Elite Autonomous Quantum Trading System**

Create:

- professional application logo;
- application icon;
- compatible desktop assets;
- MT5 branding where appropriate.

Do not use copyrighted third-party branding without authorization.

---

# 79. SECURITY

Implement:

- encrypted secrets;
- secure credential storage;
- MFA;
- RBAC;
- secure API access;
- signed configuration where appropriate;
- audit trails;
- tamper detection;
- dependency scanning;
- vulnerability scanning;
- secure update process.

---

# 80. FOSS / THIRD-PARTY POLICY

Prefer FOSS technologies where possible.

Before adopting any library, service or dataset:

- verify license;
- verify redistribution requirements;
- verify API terms;
- verify commercial-use restrictions;
- verify data-use restrictions;
- verify compatibility;
- document the license.

Do not silently introduce restricted proprietary dependencies.

---

# 81. RESEARCH EXPANSION POLICY

Continuously investigate:

- new strategies;
- new quantitative methods;
- new execution approaches;
- new risk methodologies;
- new ML architectures;
- new data sources;
- new market microstructure research;
- new portfolio techniques;
- new trading-technology architectures.

Do not add features simply because they sound advanced.

Every feature must demonstrate measurable value through:

- accuracy;
- robustness;
- latency;
- risk reduction;
- execution improvement;
- scalability;
- reliability;
- information quality.

---

# 82. ADAPTIVE ARCHITECTURE

The system should be capable of evolving its architecture.

However, autonomous architectural changes must follow:

```text
PROPOSE
→ SIMULATE
→ TEST
→ BENCHMARK
→ VALIDATE
→ APPROVE INTERNALLY
→ DEPLOY
→ MONITOR
→ ROLLBACK IF NECESSARY
```

Never modify a critical execution component directly without validation.

---

# 83. NO FALSE CLAIMS

The system must never claim:

- guaranteed profits;
- guaranteed 99% accuracy;
- guaranteed arbitrage;
- guaranteed zero slippage;
- guaranteed zero latency;
- guaranteed exchange access;
- guaranteed market prediction.

Every performance metric must be derived from measured data.

---

# 84. FINAL VALIDATION REQUIREMENTS

Before declaring the system complete, perform a complete audit.

Verify:

### Architecture

- all modules connected;
- no orphaned modules;
- no circular dependency failures;
- correct process boundaries.

### Trading

- all requested styles;
- all requested strategies;
- automatic selection;
- multi-timeframe analysis;
- session detection;
- symbol selection;
- probability gate;
- pyramiding;
- position sizing.

### Risk

- risk engine;
- drawdown;
- VaR;
- ES;
- correlation;
- margin;
- circuit breakers.

### Execution

- orders;
- modifications;
- cancellations;
- fills;
- rejections;
- slippage;
- reconciliation.

### AI

- prediction;
- analysis;
- learning;
- memory;
- model versioning;
- model evaluation.

### Dashboard

- all tabs;
- all sub-tabs;
- live data;
- charts;
- session timeline;
- live PnL;
- logs;
- monitoring.

### Security

- startup authentication;
- MFA;
- credential protection;
- privileged settings access;
- audit trail.

### Performance

- multiprocessing;
- parallel processing;
- resource usage;
- latency;
- scalability.

### Code Quality

- zero stubs;
- zero placeholders;
- zero dummy code;
- zero unresolved TODOs;
- zero broken modules;
- zero missing integrations.

---

# 85. COMPLETION CRITERIA

Do not declare the project complete simply because the application launches.

The system is complete only when:

1. The entire codebase has been audited.
2. The requested architecture has been implemented.
3. Requested modules have been integrated.
4. Required integrations have been tested.
5. Critical trading paths have been validated.
6. Risk controls have been validated.
7. Execution has been validated.
8. Dashboard functionality has been validated.
9. AI/model functionality has been validated.
10. Self-learning infrastructure has been validated.
11. Self-healing infrastructure has been validated.
12. Performance has been benchmarked.
13. Chaos testing has been completed.
14. Security testing has been completed.
15. Regression testing has passed.
16. No stubs or placeholders remain.
17. Every requested feature has a verified implementation or documented technical limitation.
18. The TODO register contains no unresolved critical items.
19. All major components are versioned.
20. All autonomous decisions are auditable.

---

# 86. REQUIRED AGENTIC EXECUTION BEHAVIOR

Do not merely generate a plan and stop.

The Agentic AI must:

```text
INSPECT
→ RESEARCH
→ ARCHITECT
→ IMPLEMENT
→ TEST
→ MEASURE
→ FIX
→ VERIFY
→ DOCUMENT
→ RE-INSPECT
```

Continue this cycle autonomously.

Whenever an error is discovered:

```text
DETECT
→ IDENTIFY ROOT CAUSE
→ FIX
→ TEST
→ REGRESSION TEST
→ UPDATE DOCUMENTATION
→ UPDATE TODO REGISTER
→ CONTINUE
```

Whenever a feature is proposed:

```text
RESEARCH
→ JUSTIFY
→ DESIGN
→ IMPLEMENT
→ TEST
→ BENCHMARK
→ VALIDATE
→ DOCUMENT
```

Whenever a strategy is proposed:

```text
RESEARCH
→ BACKTEST
→ WALK-FORWARD TEST
→ STRESS TEST
→ MONTE CARLO
→ OUT-OF-SAMPLE TEST
→ LIVE/DEMO VALIDATION
→ PERFORMANCE GOVERNANCE
```

Whenever a model is proposed:

```text
DATA VALIDATION
→ FEATURE ENGINEERING
→ TRAIN
→ VALIDATE
→ CALIBRATE
→ OUT-OF-SAMPLE TEST
→ DRIFT TEST
→ DEPLOY
→ MONITOR
→ ROLLBACK IF NEEDED
```

---

# 87. MASTER OPERATING RULE

The final system must function as an integrated autonomous ecosystem rather than a collection of disconnected features.

The target architecture is:

```text
                    ┌──────────────────────────┐
                    │      AGENTIC AI          │
                    │      ORCHESTRATOR        │
                    └────────────┬─────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
   RESEARCH BRAIN          ANALYST BRAIN        PREDICTION BRAIN
          │                      │                      │
          └──────────────┬───────┴──────────────┬───────┘
                         ▼                      ▼
                 STRATEGY BRAIN            SENTIMENT AI
                         │                      │
                         └──────────┬───────────┘
                                    ▼
                              RISK BRAIN
                                    │
                                    ▼
                           PORTFOLIO MANAGER
                                    │
                                    ▼
                           EXECUTION BRAIN
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
                MT5               BROKERS            EXCHANGES
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                              TRADE FEEDBACK
                                    │
                                    ▼
                       LEARNING / MEMORY / CASES
                                    │
                                    ▼
                              SELF-EVALUATION
                                    │
                                    └──────────────► ORCHESTRATOR
```

The final objective is to create a **robust, autonomous, multi-asset trading operating system** capable of independently researching, analyzing, predicting, selecting, executing, monitoring, learning, optimizing, and governing its own trading activities while maintaining strict risk controls, complete auditability, high performance, and zero incomplete implementation.

Do not stop at the first successful build.

Continue the autonomous:

**SCAN → BUILD → TEST → FIX → VALIDATE → OPTIMIZE → LEARN → REPEAT**

cycle throughout the development and validation lifecycle.