# ELITE AUTONOMOUS QUANTUM TRADING SYSTEM
## EAQTS VERSION 2.4
### UNIFIED MASTER DESIGN, ENGINEERING, TRADING, RISK, CAPITAL, EXECUTION, SECURITY, RESILIENCE, VALIDATION AND AUTONOMOUS EVOLUTION PLAN

**Status:** Unified authoritative master design and implementation baseline  
**Supersedes:** EAQTS Versions 2.1, 2.2 and 2.3 as separate design documents  
**Purpose:** One canonical, non-duplicated and internally consistent specification for the complete EAQTS platform

---

# 0. CONSOLIDATION DIRECTIVE

This document consolidates the three supplied EAQTS specifications:

1. Version 2.1 — foundational architecture, implementation phases, trading/intelligence/dashboard/MT5 design.
2. Version 2.2 — authoritative safety, verification, capital governance, portfolio/risk, execution integrity, learning, resilience and release-gate expansion.
3. Version 2.3 — extended operating-system controls covering execution safety, exits, compliance, treasury, research security, dependency resilience, AI governance and advanced failure handling.

The consolidation rule is:

```text
2.3 CONTROL / SAFETY / OPERATING-SYSTEM ENHANCEMENTS
        +
2.2 GOVERNANCE / VERIFICATION / CAPITAL / RISK FOUNDATION
        +
2.1 IMPLEMENTATION / TRADING / INTELLIGENCE / UI FOUNDATION
        =
EAQTS 2.4 UNIFIED BASELINE
```

Repeated concepts are represented once.

Where earlier documents contained a narrower rule that was later generalized, the later generalized rule is authoritative.

Examples:

- Fixed lot size is replaced by governed sizing.
- Fixed trade-count targets become configurable allocation targets subordinate to hard portfolio risk.
- Probability is a qualification input, never an execution authority.
- Rust/C++ execution is retained as the native low-latency implementation class; Python remains the research/ML/analytics class. Other languages are permitted only where an integration requires them.
- The 2.3 authority chain is canonical.
- The 2.3 production loop is canonical.
- The 2.3 development phases are the canonical implementation sequence.

---

# 1. SYSTEM IDENTITY AND MISSION

EAQTS is an autonomous, multi-asset quantitative trading operating system.

It shall be capable of:

- market discovery;
- real-time and historical data ingestion;
- data validation and reasonableness checking;
- point-in-time reconstruction;
- market-state construction;
- multi-timeframe analysis;
- technical analysis;
- price-action analysis;
- market-structure analysis;
- order-flow and microstructure analysis where supported;
- liquidity analysis;
- sentiment analysis;
- macro analysis;
- fundamental analysis;
- regime detection;
- strategy discovery;
- strategy selection;
- strategy portfolio construction;
- prediction;
- probability calibration;
- model-risk assessment;
- opportunity ranking;
- no-trade and abstention decisions;
- portfolio optimization;
- capital allocation;
- risk allocation;
- execution routing;
- order validation;
- execution;
- position management;
- exit management;
- reconciliation;
- accounting;
- transaction-cost analysis;
- decision-quality analysis;
- counterfactual analysis;
- memory and case management;
- controlled learning;
- model and strategy governance;
- self-diagnostics;
- safe self-healing;
- disaster recovery;
- adversarial testing;
- controlled autonomous evolution;
- complete provenance and auditability.

The system must be able to determine:

```text
WHEN TO TRADE
WHEN NOT TO TRADE
WHEN TO DEFER
WHEN TO ABSTAIN
WHAT TO TRADE
WHERE TO TRADE
WHICH STRATEGY TO USE
WHICH MODEL EVIDENCE TO TRUST
HOW MUCH CAPITAL TO USE
HOW MUCH RISK TO USE
HOW TO EXECUTE
HOW TO MANAGE THE POSITION
WHEN THE THESIS HAS FAILED
WHEN TO EXIT
WHEN TO REPLACE AN EXISTING POSITION
WHETHER CAPITAL IS BETTER DEPLOYED ELSEWHERE
WHETHER THE SYSTEM ITSELF IS SAFE ENOUGH TO CONTINUE
```

---

# 2. NON-PERFECT SYSTEM PRINCIPLE

EAQTS does not assume perfect prediction, perfect data, perfect liquidity, perfect infrastructure or perfect execution.

The engineering objective is:

```text
CONTROLLED
+
TESTABLE
+
DETERMINISTIC
+
REPRODUCIBLE
+
INDEPENDENTLY VERIFIED
+
FAIL-SAFE
+
RECOVERABLE
+
AUDITABLE
+
EMPIRICALLY VALIDATED
```

The system optimizes for bounded failure rather than assumed perfection.

Immutable principles:

```text
FAIL TOWARD LESS RISK.

UNKNOWN ≠ NORMAL.

DISAGREEMENT = RISK.

ABSTENTION IS VALID.

NO TRADE IS VALID.

DEFERRED ACTION IS VALID.

PREDICTION ≠ PERMISSION.

STRATEGY ≠ PERMISSION.

OPTIMIZATION ≠ PERMISSION.

RISK APPROVAL ≠ FINAL EXECUTION AUTHORITY.

ONLY TRADE ADMISSION CAN AUTHORIZE EXECUTION.

EXIT MANAGEMENT IS AS IMPORTANT AS ENTRY GENERATION.

AUTONOMY DECREASES WHEN CERTAINTY DECREASES.

COMPLEXITY MUST CREATE MEASURABLE VALUE.
```

---

# 3. SYSTEM CONSTITUTION

The canonical authority hierarchy is:

```text
LEVEL 0
LEGAL / REGULATORY / JURISDICTION / EXCHANGE / BROKER
        ↓
LEVEL 1
SAFETY INVARIANTS
        ↓
LEVEL 2
SAFETY KERNEL
        ↓
LEVEL 3
CAPITAL GOVERNANCE
        ↓
LEVEL 4
HARD PORTFOLIO RISK
        ↓
LEVEL 5
INDEPENDENT RISK VERIFICATION
        ↓
LEVEL 6
TRADE ADMISSION
        ↓
LEVEL 7
EXECUTION CONSTRAINTS
        ↓
LEVEL 8
POSITION / EXIT CONSTRAINTS
        ↓
LEVEL 9
STRATEGY CONSTRAINTS
        ↓
LEVEL 10
MODEL / AI RECOMMENDATIONS
        ↓
LEVEL 11
RESEARCH / OPTIMIZATION PROPOSALS
```

No lower level may override a higher level.

No AI model, reinforcement-learning process, optimizer, strategy, research agent or autonomous evolution process may modify or bypass:

- legal restrictions;
- jurisdiction restrictions;
- exchange restrictions;
- broker restrictions;
- hard capital limits;
- hard portfolio-risk limits;
- Safety Invariants;
- Safety Kernel rules;
- emergency controls;
- security controls;
- execution-integrity controls.

---

# 4. AUTONOMY MODEL

Autonomy is authority constrained by system capability and state.

```text
AUTONOMY AUTHORITY
=
VALIDATED CAPABILITY
×
SYSTEM CONFIDENCE
×
CAPITAL CAPACITY
×
RISK CAPACITY
×
SAFETY STATE
×
COMPLIANCE PERMISSION
×
GOVERNANCE AUTHORITY
```

A decrease in any critical factor reduces permitted authority.

Autonomy levels shall include, at minimum:

```text
L0 OBSERVE
L1 ANALYZE
L2 RECOMMEND
L3 SHADOW
L4 LIMITED EXECUTION
L5 CONTROLLED PRODUCTION
L6 FULL AUTHORIZED PRODUCTION
L7 DEFENSIVE
L8 HALTED
L9 RECOVERY
```

The exact authority attached to each level is controlled by the Authority Matrix.

---

# 5. MASTER ARCHITECTURE

```text
                         ┌─────────────────────────────────┐
                         │ CONTROL / GOVERNANCE PLANE      │
                         │ Policy / Authority / Config     │
                         │ Security / Deployment / Audit   │
                         └───────────────┬─────────────────┘
                                         │
                         ┌───────────────▼─────────────────┐
                         │ ORCHESTRATOR / EVENT FABRIC     │
                         └───────────────┬─────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌────────────────┐              ┌────────────────────┐             ┌────────────────┐
│ RESEARCH PLANE │              │ INTELLIGENCE PLANE │             │ DATA PLANE     │
│ Research       │              │ Analysis           │             │ Market         │
│ Backtesting    │              │ Regime             │             │ News           │
│ Experiments    │              │ Prediction         │             │ Macro          │
│ Feature R&D    │              │ Model Risk         │             │ Fundamentals   │
└───────┬────────┘              └──────────┬─────────┘             │ Alternative    │
        │                                  │                       └───────┬────────┘
        └──────────────────────────────────┼───────────────────────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ MARKET STATE ENGINE      │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ OPPORTUNITY ENGINE        │
                              │ BUY / SELL / NO TRADE    │
                              │ DEFER / ABSTAIN / INVALID │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ PORTFOLIO ENGINE          │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ CAPITAL GOVERNANCE        │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ RISK ENGINE               │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ SAFETY INVARIANT ENGINE   │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ SAFETY KERNEL             │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ TRADE ADMISSION           │
                              └────────────┬─────────────┘
                                           │
                          ┌────────────────┴────────────────┐
                          ▼                                 ▼
                ┌──────────────────┐              ┌────────────────────┐
                │ EXECUTION CORE   │              │ INDEPENDENT RISK   │
                │ Routing / Orders │              │ VERIFIER           │
                └────────┬─────────┘              └────────────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
             MT5        FIX       Broker/API
              │          │          │
              └──────────┼──────────┘
                         ▼
                ┌──────────────────┐
                │ EXECUTION         │
                │ VERIFIER          │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ POSITION MANAGER │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ EXIT ENGINE      │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ RECONCILIATION   │
                └────────┬─────────┘
                         ▼
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
      LEDGER           MEMORY             TCA
        │                │                 │
        └────────────────┼─────────────────┘
                         ▼
                DECISION QUALITY
                         ▼
             LEARNING / GOVERNANCE
                         ▼
              SHADOW / CHALLENGER
                         ▼
                    CANARY
                         ▼
                   PRODUCTION
```

---

# 6. ARCHITECTURAL PLANES

## 6.1 Control and Governance Plane

Owns:

- orchestration;
- policy;
- authority;
- configuration;
- versioning;
- deployment;
- scheduling;
- resource governance;
- lifecycle;
- rollback;
- capability registry;
- dependency graph;
- release governance;
- compliance governance.

## 6.2 Data Plane

Owns:

- real-time feeds;
- historical feeds;
- alternative data;
- point-in-time data;
- normalization;
- quality;
- confidence;
- lineage;
- source reconciliation;
- provider failover;
- data licensing;
- symbol master;
- global clock;
- market calendar.

## 6.3 Intelligence Plane

Owns:

- features;
- technical analysis;
- price action;
- market structure;
- order flow;
- liquidity;
- sentiment;
- macro;
- fundamentals;
- regime;
- prediction;
- calibration;
- model comparison;
- model risk;
- abstention.

## 6.4 Strategy Plane

Owns:

- strategy framework;
- strategy universe;
- eligibility;
- trading license;
- lifecycle;
- portfolio weighting;
- conflict resolution;
- MTF resolution;
- parameter robustness;
- regime robustness;
- capacity;
- edge decay;
- quarantine.

## 6.5 Opportunity / Portfolio / Capital / Risk Plane

Owns:

- opportunity queue;
- expected net value;
- liquidity-adjusted scoring;
- opportunity competition;
- portfolio optimization;
- capital budgets;
- risk budgets;
- reservations;
- marginal risk;
- incremental risk;
- factor risk;
- correlation risk;
- tail risk;
- scenario analysis;
- reverse stress;
- uncertainty budgets;
- treasury;
- collateral.

## 6.6 Safety and Verification Plane

Independent from prediction and research.

Owns:

- Safety Invariants;
- Safety Kernel;
- formal state verification;
- independent risk verification;
- Trade Admission;
- safe-by-disagreement;
- emergency halt;
- kill switch;
- configuration integrity;
- execution-integrity verification.

## 6.7 Execution Plane

Owns:

- TradingIntent;
- pre-trade validation;
- rate governance;
- fat-finger protection;
- self-trade prevention;
- routing;
- order management;
- broker state;
- exchange state;
- execution;
- execution verification;
- position management;
- reconciliation;
- TCA.

## 6.8 Learning and Governance Plane

Owns:

- Case Library;
- rejected-trade intelligence;
- counterfactuals;
- decision quality;
- luck-vs-skill;
- cost-of-inaction;
- experiment registry;
- model registry;
- strategy registry;
- champion/challenger;
- canary;
- rollback;
- controlled evolution.

## 6.9 Operations and Resilience Plane

Owns:

- observability;
- resource governance;
- self-healing;
- incident management;
- runbooks;
- flight recorder;
- disaster recovery;
- active/standby;
- split-brain protection;
- chaos engineering;
- dependency isolation;
- backpressure;
- retry budgets;
- data shedding.

---

# 7. ORCHESTRATOR AND EVENT FABRIC

The Orchestrator shall:

- schedule agents;
- enforce dependencies;
- correlate events;
- manage state;
- manage deadlines;
- prioritize workloads;
- detect conflicts;
- manage candidate models;
- manage candidate strategies;
- prevent duplicate execution;
- prevent split-brain;
- trigger recovery;
- maintain observability;
- enforce capability dependencies.

The Orchestrator is not the sole holder of financial truth.

All major components communicate using versioned events.

Required event families include:

```text
MarketTickReceived
CandleClosed
MarketDataUpdated
SessionChanged
MarketCalendarChanged
SymbolUniverseChanged
FeatureVectorUpdated
MarketStateChanged
RegimeChanged
PredictionCreated
PredictionCalibrated
PredictionAbstained
PredictionDisagreementDetected
StrategyEvaluated
StrategySelected
StrategyDegraded
StrategyQuarantined
OpportunityCreated
OpportunityDeferred
OpportunityExpired
RiskBudgetReserved
RiskBudgetReleased
RiskApproved
RiskRejected
SafetyInvariantViolation
TradingIntentCreated
TradingIntentExpired
TradeAdmissionApproved
TradeAdmissionRejected
OrderValidated
OrderSubmitted
OrderAccepted
OrderRejected
OrderPartiallyFilled
OrderFilled
OrderCancelled
PositionOpened
PositionModified
PositionClosed
TradeCompleted
ReconciliationMismatch
RiskVerificationMismatch
ExecutionVerificationMismatch
AccountingMismatch
ModelUpdated
ModelDegraded
ModelDriftDetected
ChangeProposalCreated
DeploymentStarted
DeploymentCompleted
RollbackStarted
RollbackCompleted
SystemFault
RecoveryStarted
RecoveryCompleted
ChaosExperimentStarted
ChaosExperimentCompleted
SecurityEvent
ConfigurationChanged
AuthorityChanged
CapitalBudgetChanged
CapabilityDegraded
CapabilityRestored
```

Every event shall contain:

- unique event ID;
- timestamp;
- source;
- schema version;
- correlation ID;
- causation ID where applicable;
- payload;
- integrity metadata.

---

# 8. EVENT SOURCING, DECISION SNAPSHOTS AND PROVENANCE

Immutable event records shall be maintained for:

- orders;
- executions;
- positions;
- portfolio changes;
- risk decisions;
- safety decisions;
- capital reservations;
- configuration changes;
- strategy state changes;
- model deployments;
- autonomous changes;
- security events;
- incidents.

Every trading decision receives an immutable `DecisionSnapshotID`.

The snapshot shall include:

- market state;
- market-data state;
- feature state;
- model versions;
- strategy versions;
- risk configuration;
- capital state;
- portfolio state;
- broker state;
- execution state;
- data-provider state;
- safety state;
- system version;
- configuration version;
- dependency versions.

Canonical provenance:

```text
SOURCE
→ RAW DATA
→ VALIDATION
→ NORMALIZATION
→ TRANSFORMATION
→ FEATURE
→ MARKET STATE
→ MODEL
→ PREDICTION
→ STRATEGY
→ OPPORTUNITY
→ PORTFOLIO
→ CAPITAL
→ RISK
→ SAFETY
→ DECISION
→ INTENT
→ ORDER
→ EXECUTION
→ POSITION
→ EXIT
→ OUTCOME
→ LEARNING
```

---

# 9. TIME, CALENDAR AND POINT-IN-TIME DATA

All time-sensitive subsystems use a centralized Global Clock Service.

Support:

- UTC;
- broker time;
- exchange time;
- session boundaries;
- candle boundaries;
- economic events;
- monotonic execution timing;
- latency measurement.

Market Calendar Service handles:

- holidays;
- closures;
- early closes;
- maintenance;
- DST;
- special sessions;
- reopenings.

Historical data must preserve:

```text
EVENT TIME
PUBLICATION TIME
AVAILABILITY TIME
```

No model may consume information that was unavailable at the historical decision time.

Mandatory point-in-time treatment applies to:

- market data;
- news;
- economic releases;
- fundamentals;
- analyst information;
- corporate actions;
- alternative data;
- sentiment.

---

# 10. DATA PLANE

## 10.1 Symbol Master

Maintain one authoritative instrument database containing:

- canonical symbol;
- broker symbol;
- exchange;
- asset class;
- currency;
- contract size;
- tick size;
- tick value;
- minimum volume;
- maximum volume;
- volume step;
- margin;
- leverage;
- stop-distance rules;
- freeze levels;
- sessions;
- holidays;
- order types;
- execution rules.

## 10.2 Data Quality

Measure:

- freshness;
- completeness;
- continuity;
- consistency;
- latency;
- anomaly rate;
- source reliability;
- distribution stability.

Produce:

- Data Quality Score;
- Data Confidence Score.

## 10.3 Data Confidence Propagation

```text
FEED CONFIDENCE
→ FEATURE CONFIDENCE
→ MARKET STATE CONFIDENCE
→ PREDICTION CONFIDENCE
→ STRATEGY CONFIDENCE
→ PORTFOLIO CONFIDENCE
→ SYSTEM DECISION CONFIDENCE
```

Downstream confidence cannot exceed critical dependency reliability.

## 10.4 Market-Data Reasonableness

Validate:

- bid;
- ask;
- spread;
- continuity;
- jumps;
- timestamp;
- sequence;
- duplicates;
- ordering;
- crossed markets;
- inverted markets;
- zero/impossible values;
- volume anomalies;
- reference-price deviation;
- venue divergence.

States:

```text
VALID
SUSPECT
INVALID
QUARANTINED
```

Critical suspect/invalid data reduces capability or blocks execution.

## 10.5 Reference Price

Where supported:

```text
PRIMARY FEED
+
SECONDARY FEED
+
BROKER PRICE
+
CROSS-VENUE DATA
→ REFERENCE PRICE
```

Generate a Price Deviation Score and block orders outside configured reasonableness boundaries.

## 10.6 Provider Failover

```text
PRIMARY
→ SECONDARY
→ TERTIARY
→ SAFE MODE
```

Provider selection considers:

- timestamp;
- reliability;
- consistency;
- cross-source agreement;
- historical behavior;
- licensing;
- latency.

Newest is not automatically correct.

---

# 11. MARKET STATE AND INTELLIGENCE

## 11.1 Canonical Market State Vector

All intelligence components consume one normalized state representation.

Include:

- symbol;
- asset class;
- session;
- regime;
- trend;
- momentum;
- volatility;
- liquidity;
- spread;
- order flow;
- sentiment;
- macro;
- fundamentals;
- correlation;
- factor exposure;
- funding;
- basis;
- market depth;
- news state;
- execution state;
- data confidence;
- system confidence.

## 11.2 Regime Engine

Detect:

- trend;
- range;
- breakout;
- high volatility;
- low volatility;
- crisis;
- transition;
- liquidity stress;
- event-driven regimes.

Maintain:

- regime probability;
- confidence;
- persistence;
- regime-change events;
- regime-specific strategy effectiveness.

## 11.3 Research Brain

Research:

- strategies;
- models;
- features;
- data;
- technology;
- markets;
- public/academic material;
- experiments.

Research creates Change Proposals, never direct production modifications.

## 11.4 Analyst Brain

Analyze:

- charts;
- price action;
- technicals;
- market structure;
- order flow;
- liquidity;
- multi-timeframe structure;
- volatility;
- correlation;
- factors;
- intermarket relationships;
- macro;
- fundamentals;
- sentiment.

All outputs require provenance.

## 11.5 Prediction Brain

Permitted outputs:

```text
PREDICT
ABSTAIN
INVALID
```

Produce, where supported:

- directional probability;
- expected movement;
- expected range;
- expected volatility;
- uncertainty;
- confidence;
- disagreement score;
- forecast distributions.

Prediction quality and trading quality remain separate.

## 11.6 Calibration and Evidence

Measure:

- accuracy;
- precision;
- recall;
- F1;
- Brier score;
- calibration error;
- reliability;
- false positives;
- false negatives;
- expected value;
- post-cost profitability.

Eligibility considers:

```text
Probability
+
Calibration
+
Sample Size
+
Historical Reliability
+
Current-Regime Reliability
+
Expected Value
+
Data Confidence
+
Model Agreement
```

A default directional threshold may remain above 60% validated probability where appropriate, but it is configurable and never sufficient by itself.

---

# 12. MODEL RISK, DISAGREEMENT AND DRIFT

Each model receives:

- model-risk score;
- complexity score;
- data-dependency score;
- instability score;
- overfitting risk;
- drift risk;
- sensitivity score;
- operational-risk score;
- explainability metadata.

Detect:

- source shift;
- feature shift;
- market-state shift;
- regime shift;
- prediction shift;
- calibration drift;
- performance drift.

Actions:

```text
MONITOR
→ REDUCE
→ SUSPEND
→ RETRAIN
→ ROLLBACK
```

High disagreement among critical models reduces authority.

Unanimous AI agreement cannot bypass safety or Trade Admission.

---

# 13. STRATEGY SYSTEM

## 13.1 Strategy Eligibility

Every strategy declares:

- asset class;
- symbol universe;
- session;
- timeframe;
- regime;
- volatility conditions;
- liquidity requirements;
- spread limits;
- expected value;
- probability requirements;
- execution requirements;
- minimum history;
- minimum sample size;
- current and historical performance;
- portfolio compatibility;
- required and optional data;
- maximum data age;
- fallback behavior.

## 13.2 Strategy Trading License

A strategy may execute only when its license is valid.

The license binds:

- strategy version;
- permitted assets;
- permitted sessions;
- permitted regimes;
- risk authority;
- model dependencies;
- data dependencies;
- execution capabilities;
- lifecycle state.

## 13.3 Lifecycle

```text
RESEARCH
→ EXPERIMENTAL
→ BACKTEST
→ WALK-FORWARD
→ OOS
→ SHADOW
→ PAPER
→ DEMO
→ LIMITED_PRODUCTION
→ PRODUCTION
→ DEGRADED
→ SUSPENDED
→ RETIRED
```

## 13.4 Robustness

Evaluate:

- parameter fragility;
- regime robustness;
- capacity;
- market impact;
- edge decay;
- execution sensitivity;
- data dependency concentration.

## 13.5 Strategy Risk Multipliers

Example policy:

```text
CHAMPION       = 1.00
HEALTHY        = 0.75
DEGRADED       = 0.40
QUARANTINED    = 0.00
SUSPENDED      = 0.00
```

These multipliers reduce available authority without changing hard limits.

## 13.6 Strategy Universe

Support validated families including:

- trend following;
- moving-average systems;
- Donchian;
- MACD;
- RSI;
- Bollinger;
- stochastic;
- Ichimoku;
- Triple Screen;
- Supertrend/HMA;
- Heikin-Ashi/CMO;
- VWAP;
- ADX;
- linear regression;
- Williams %R;
- CCI;
- Keltner;
- Elder Impulse;
- Coppock;
- COG;
- RVI;
- Ultimate Oscillator;
- CMF;
- DPO;
- TSI;
- MFI;
- Aroon;
- ICT/SMC;
- order-flow;
- volume-profile;
- statistical arbitrage;
- other strategies only after governance and validation.

No strategy family is production-authorized merely because it exists in the registry.

---

# 14. MULTI-TIMEFRAME ENGINE

Canonical interpretation:

```text
HIGHER TIMEFRAME
→ REGIME / CONTEXT

MIDDLE TIMEFRAME
→ SETUP

LOWER TIMEFRAME
→ ENTRY / EXECUTION
```

Supported dashboard and analytical timeframes:

```text
M1
M5
M15
M30
H1
H4
D1
W1
MN
```

Strategies may use different mappings only when validated.

---

# 15. OPPORTUNITY ENGINE

Every candidate enters a global Opportunity Queue.

Opportunity record includes:

- symbol;
- direction;
- strategy;
- style;
- timeframe;
- probability;
- expected net value;
- risk;
- liquidity;
- spread;
- execution score;
- expiration;
- portfolio effect;
- data confidence;
- model confidence;
- capacity;
- path risk.

Every opportunity supports:

```text
BUY
SELL
NO TRADE
DEFER
ABSTAIN
INVALID
```

## 15.1 Expected Net Value

```text
Expected Net Value
=
Expected Gross Edge
-
Spread
-
Commission
-
Expected Slippage
-
Financing
-
Estimated Market Impact
```

Trade only when the result remains positive and risk-adjusted.

## 15.2 Liquidity-Adjusted Opportunity Score

Opportunity scoring shall account for:

```text
EXPECTED EDGE
/
EXPECTED TOTAL COST
/
LIQUIDITY RISK
```

Probability alone is insufficient.

## 15.3 Capital Opportunity Cost

For significant positions:

```text
CURRENT CAPITAL USE
vs
EXPECTED CAPITAL USE OF BEST FEASIBLE ALTERNATIVE
```

The system may recommend:

```text
HOLD
REDUCE
CLOSE
REPLACE
```

---

# 16. TRADING INTENT

Every executable candidate becomes one canonical `TradingIntent`.

Required fields include:

- intent ID;
- symbol;
- direction;
- strategy;
- style;
- timeframe;
- probability;
- expected value;
- regime;
- entry;
- stop;
- target;
- position size;
- risk;
- capital allocation;
- model versions;
- strategy version;
- feature version;
- Decision Snapshot ID;
- creation time;
- expiration time.

All downstream components consume the same intent.

An intent expires when:

- market conditions move materially;
- spread changes;
- volatility changes;
- strategy becomes invalid;
- session changes;
- data becomes stale;
- execution conditions exceed tolerance;
- its time-to-live expires.

Before submission:

```text
DATA FRESHNESS
+
DECISION AGE
+
INTENT AGE
+
EXECUTION LATENCY
```

must remain valid.

---

# 17. PORTFOLIO ENGINE

Portfolio decisions optimize combinations, not isolated trades.

Consider:

- expected value;
- covariance;
- correlation;
- marginal risk;
- incremental risk;
- concentration;
- factor exposure;
- liquidity;
- drawdown;
- path risk;
- uncertainty;
- capacity;
- capital opportunity cost.

Supported optimization families include:

- Markowitz;
- Black-Litterman;
- Risk Parity;
- Hierarchical Risk Parity;
- volatility targeting;
- VaR;
- Expected Shortfall;
- CVaR.

No optimizer may override Capital Governance or hard risk.

---

# 18. CAPITAL GOVERNANCE AND TREASURY

Capital buckets:

```text
TOTAL CAPITAL
├── RESERVE CAPITAL
├── SAFETY CAPITAL
├── OPERATING CAPITAL
└── DEPLOYABLE TRADING CAPITAL
    ├── FOREX
    ├── METALS
    ├── EQUITIES
    ├── FUTURES
    ├── CRYPTO
    └── OPTIONS
```

Capital governance controls:

- strategy capital;
- asset-class capital;
- broker capital;
- venue capital;
- emergency liquidity;
- reserves;
- deployment limits.

Treasury services cover:

- cash;
- currency translation;
- funding;
- financing;
- collateral;
- reservations;
- multi-currency exposure.

---

# 19. RISK ARCHITECTURE

Risk budgets exist for:

- portfolio;
- asset class;
- symbol;
- strategy;
- direction;
- correlation;
- factor;
- liquidity;
- event;
- overnight;
- execution.

Reservation lifecycle:

```text
AVAILABLE
→ RESERVED
→ COMMITTED
→ RELEASED
```

Reservations must be visible across concurrent agents.

## 19.1 Hard Risk

Control:

- exposure;
- leverage;
- margin;
- portfolio risk;
- symbol risk;
- strategy risk;
- factor risk;
- asset-class risk;
- correlation;
- liquidity;
- drawdown;
- overnight;
- weekend;
- gap;
- event;
- execution;
- counterparty risk.

## 19.2 Loss Limits

Support:

```text
TRADE
5-MINUTE
HOURLY
SESSION
DAILY
WEEKLY
MONTHLY
ROLLING-N-DAY
```

and dimensions:

```text
STRATEGY
SYMBOL
ASSET CLASS
BROKER
MODEL
PORTFOLIO
```

## 19.3 Loss Velocity

Measure:

- loss rate;
- acceleration;
- drawdown acceleration;
- consecutive-loss velocity;
- execution-loss velocity;
- strategy-loss velocity.

Rapid degradation can restrict risk before hard limits are reached.

## 19.4 Liquidity Stress

Detect:

- spread expansion;
- depth deterioration;
- slippage;
- volume anomalies;
- volatility shocks;
- execution degradation;
- market-impact increase.

Produce a Liquidity Stress State.

## 19.5 Tail Risk

Model:

- gaps;
- flash crashes;
- liquidity holes;
- spread explosions;
- execution discontinuity;
- jumps;
- weekend gaps;
- event shocks;
- correlated liquidation;
- venue outages.

## 19.6 Scenarios and Reverse Stress

Scenario engine supports individual and combined shocks such as:

- currency shocks;
- rate shocks;
- commodity shocks;
- equity shocks;
- crypto shocks;
- volatility multiplication;
- spread multiplication;
- liquidity collapse;
- broker outage;
- data outage;
- execution latency multiplication.

Reverse stress identifies conditions that could cause:

- hard-risk breach;
- margin failure;
- unacceptable drawdown;
- leverage breach;
- execution failure;
- reconciliation failure;
- recovery failure.

## 19.7 Drawdown Recovery

```text
NORMAL
→ DRAWDOWN
→ DEFENSIVE
→ RECOVERY
→ REVALIDATION
→ GRADUAL RISK RESTORATION
```

Risk must not return immediately after major drawdown.

Risk hysteresis prevents rapid state oscillation.

---

# 20. SAFETY INVARIANTS

Safety Invariants are deterministic system truths.

Examples:

```text
INV-001 Portfolio risk ≤ hard ceiling
INV-002 Exposure ≤ maximum permitted exposure
INV-003 Leverage ≤ maximum permitted leverage
INV-004 Every live order has valid ownership
INV-005 Every live position has authoritative state
INV-006 Every executable intent has a valid Decision Snapshot
INV-007 Stale intents cannot execute
INV-008 Every production model is registered
INV-009 Every production strategy is registered
INV-010 Every production deployment has rollback artifacts
INV-011 AI cannot modify immutable safety controls
INV-012 Research cannot directly mutate production
INV-013 Broker positions can be reconciled
INV-014 Executed trades have complete provenance
```

Additional invariants shall cover:

- valid prices;
- valid stops;
- margin sufficiency;
- rate limits;
- order ownership;
- self-trade prevention;
- configuration integrity;
- execution authority;
- broker state;
- account state;
- exchange state;
- reconciliation;
- compliance.

---

# 21. SAFETY KERNEL

The Safety Kernel is deterministic, minimal, independently testable and protected from AI self-modification.

It enforces:

- hard risk;
- hard exposure;
- leverage;
- margin;
- invalid-order rejection;
- stale-data rejection;
- stale-intent rejection;
- emergency controls;
- security controls;
- execution-integrity controls;
- authority boundaries;
- fail-safe behavior.

The Safety Kernel shall never depend on an LLM being available.

---

# 22. FORMAL STATE VERIFICATION AND SAFE-BY-DISAGREEMENT

Critical state domains:

- market;
- broker;
- exchange;
- account;
- portfolio;
- positions;
- orders;
- data;
- model;
- configuration;
- safety;
- reconciliation;
- execution.

State:

```text
NORMAL
UNKNOWN
INFORMATION_DEGRADED
RESTRICTED
DEFENSIVE
HALTED
RECOVERY
```

If critical independent systems disagree:

```text
DISAGREEMENT
→ FREEZE NEW RISK
→ PRESERVE EVIDENCE
→ INDEPENDENT VERIFICATION
→ RECONCILE
→ SAFETY RECHECK
→ RESUME GRADUALLY
```

---

# 23. TRADE ADMISSION CONTROLLER

Trade Admission is the only final authorization boundary.

Admission requires all applicable conditions:

```text
LEGAL / JURISDICTION
+
EXCHANGE / BROKER
+
DATA VALIDITY
+
CAPABILITY
+
MODEL ELIGIBILITY
+
STRATEGY LICENSE
+
EXPECTED NET VALUE
+
LIQUIDITY
+
CAPACITY
+
CAPITAL
+
RISK
+
SAFETY
+
INDEPENDENT RISK VERIFICATION
+
FRESH INTENT
+
RATE LIMITS
+
ORDER VALIDATION
+
COMPLIANCE
=
TRADE ADMISSION
```

No Trade Admission means no execution.

---

# 24. EXECUTION SAFETY

## 24.1 Order and Message Rate Governance

Independent limits for:

- orders/second;
- cancellations/second;
- modifications/second;
- messages/second;
- executions/minute;
- strategy messages;
- symbol messages;
- venue messages;
- account messages.

States:

```text
NORMAL
→ ELEVATED
→ THROTTLED
→ RESTRICTED
→ HALTED
```

## 24.2 Fat-Finger Protection

Validate:

- maximum order size;
- maximum notional;
- price deviation;
- position increase;
- stop distance;
- price movement;
- order value.

Apply at:

```text
STRATEGY
→ SYMBOL
→ ACCOUNT
→ BROKER
→ PORTFOLIO
→ SYSTEM
```

## 24.3 Self-Trade Prevention

Detect conflicting EAQTS orders across:

- strategy;
- account;
- venue;
- symbol;
- side;
- type;
- price;
- timing.

Actions:

```text
BLOCK
NET
ROUTE DIFFERENTLY
DEFER
```

## 24.4 Cancel-on-Disconnect

```text
CONNECTION LOST
→ FREEZE NEW ORDERS
→ CANCEL ELIGIBLE OUTSTANDING ORDERS
→ RECONCILE
→ VERIFY ACTUAL POSITIONS
→ DEFENSIVE / RECOVERY
```

Never assume a disconnected order did not execute.

---

# 25. EXECUTION CORE AND VENUE MANAGEMENT

The Universal Trading Interface abstracts:

```text
MT5
FIX
BROKER/API
```

Venue scoring considers:

- latency;
- spread;
- slippage;
- fill rate;
- rejection rate;
- fees;
- liquidity;
- reliability;
- execution quality;
- counterparty risk;
- settlement risk;
- venue risk.

Execution toxicity measures:

- adverse selection;
- fill quality;
- spread;
- latency;
- post-fill price movement;
- liquidity conditions.

A profitable venue is not automatically a safe venue.

---

# 26. MT5 ARCHITECTURE

MT5 support includes:

- market data;
- account state;
- orders;
- positions;
- execution;
- EA telemetry;
- HUD;
- dashboard synchronization.

Canonical structure:

```text
UNIVERSAL TRADING INTERFACE
        │
   ┌────┼────┐
   ▼    ▼    ▼
  MT5  FIX  BROKER/API
```

The MT5 EA is an adapter/telemetry/execution bridge, not the holder of the complete trading brain.

EA responsibilities:

- live telemetry;
- market information;
- execution bridge where required;
- synchronization;
- HUD.

Broker constraints are mandatory:

- volume rules;
- contract size;
- tick size/value;
- margin;
- leverage;
- stop distance;
- freeze level;
- execution mode;
- trading hours.

---

# 27. POSITION MANAGEMENT

Every live position has a Position Integrity Contract:

- broker identity;
- internal identity;
- strategy owner;
- model owner;
- thesis;
- risk allocation;
- capital allocation;
- stop policy;
- exit policy;
- Decision Snapshot;
- current state.

Supported operations:

- open;
- modify;
- trailing stop;
- trailing target where supported;
- partial close;
- pyramiding;
- emergency close;
- reconciliation.

## 27.1 Pyramiding

Additional entries require, where applicable:

- existing position validity;
- thesis validity;
- strategy validity;
- probability validity;
- positive expected net value;
- acceptable liquidity;
- acceptable execution cost;
- remaining capital;
- remaining risk budget.

Pyramiding may increase trade count but can never breach hard portfolio risk.

## 27.2 Sizing

Sizing is governed rather than fixed.

Methods may include:

- risk-based;
- volatility-based;
- expected-value-based;
- liquidity-based;
- portfolio-based;
- drawdown-based.

Kelly, if used, must be constrained by:

- fractional Kelly;
- estimation error;
- confidence;
- liquidity;
- drawdown;
- portfolio caps.

Unconstrained Kelly is prohibited.

Any earlier fixed lot-size target is therefore treated only as a configurable test/default parameter, never as a global production sizing rule.

---

# 28. EXIT-CENTRIC DESIGN

Every position follows:

```text
ENTRY
→ THESIS
→ MANAGEMENT
→ REASSESSMENT
→ EXIT
→ POST-EXIT ANALYSIS
```

## 28.1 Position Thesis Engine

The thesis is continuously evaluated against:

- original evidence;
- current evidence;
- regime;
- model state;
- liquidity;
- execution;
- portfolio state;
- new information.

## 28.2 Continuous Reassessment

Reevaluate open positions on:

- tick/candle updates as appropriate;
- regime changes;
- model changes;
- liquidity changes;
- event changes;
- portfolio changes;
- new opportunities;
- risk changes;
- thesis changes.

## 28.3 Position Timeout

A position can be exited when:

- thesis has not progressed within expected time;
- opportunity half-life expires;
- capital opportunity cost becomes unfavorable;
- risk-adjusted alternatives dominate;
- strategy conditions expire.

## 28.4 Opportunity Competition

Open positions compete for scarce capital and risk capacity.

Possible outcomes:

```text
HOLD
REDUCE
CLOSE
REPLACE
```

## 28.5 Portfolio Emergency Exit

Portfolio-level exit authority can be triggered by:

- catastrophic risk;
- liquidity collapse;
- broker/exchange failure;
- systemic reconciliation failure;
- hard capital breach;
- severe market-wide circuit conditions.

---

# 29. MARKET, SESSION AND EVENT INTELLIGENCE

Session engine shall support applicable sessions including:

- Wellington;
- Sydney;
- Tokyo;
- Hong Kong;
- Singapore;
- Frankfurt;
- London;
- Zurich;
- New York;
- US pre-market;
- US core;
- US after-hours;
- CME;
- ICE;
- crypto 24/7.

Session state affects:

- volatility;
- liquidity;
- spread;
- strategy eligibility;
- sizing;
- execution;
- risk.

Market Event Firewall monitors:

- central-bank events;
- NFP;
- CPI;
- major economic releases;
- earnings;
- exchange outages;
- extraordinary volatility;
- major geopolitical events.

Event state is strategy-specific:

```text
OPPORTUNITY
ELEVATED RISK
NO TRADE
```

Event trading is not universally prohibited.

---

# 30. ASSET-CLASS EXTENSIONS

Specialized risk and operating modules shall support, where technically and legally available:

- Forex;
- metals;
- equities;
- futures;
- crypto;
- options.

## 30.1 Futures

Support:

- contract metadata;
- expiration;
- roll schedule;
- roll cost;
- liquidity migration;
- continuous-series mapping.

## 30.2 Options

Support:

- option chain;
- Delta;
- Gamma;
- Vega;
- Theta;
- implied volatility;
- volatility surface;
- term structure;
- exercise/assignment;
- options-specific risk.

## 30.3 Crypto

Account for:

- venue risk;
- custody/operational risk;
- funding;
- 24/7 operation;
- on-chain data where lawful;
- exchange outages;
- liquidation behavior.

## 30.4 Corporate Actions

Handle:

- splits;
- dividends;
- mergers;
- symbol changes;
- delistings;
- other supported corporate actions.

---

# 31. FINANCING, TREASURY AND COLLATERAL

Rollover/financing intelligence models:

- swap;
- funding;
- carry;
- overnight financing;
- triple-swap periods;
- borrow;
- funding-rate changes.

Treasury manages:

- multi-currency cash;
- currency translation;
- funding;
- financing;
- collateral;
- reserves;
- capital reservations.

---

# 32. FINANCIAL LEDGER AND ACCOUNTING

Maintain immutable ledgers for:

```text
TRADING
ACCOUNTING
CASH
FEES
FUNDING
TAX REPORTING
```

Maintain an independent Shadow Ledger.

Differences produce `AccountingMismatch`.

PnL attribution includes:

- strategy;
- model;
- symbol;
- asset class;
- session;
- regime;
- direction;
- entry;
- exit;
- spread;
- slippage;
- commission;
- financing;
- execution.

Financial truth must be independently reconcilable.

---

# 33. RECONCILIATION

Continuously reconcile:

```text
MARKET DATA
VS
BROKER DATA

INTERNAL ORDERS
VS
BROKER ORDERS

INTERNAL POSITIONS
VS
BROKER POSITIONS

INTERNAL PORTFOLIO
VS
BROKER PORTFOLIO

MT5 STATE
VS
BROKER STATE

PRIMARY LEDGER
VS
SHADOW LEDGER
```

Detect:

- missing fills;
- phantom positions;
- orphan orders;
- quantity mismatch;
- stop mismatch;
- target mismatch;
- state divergence;
- accounting mismatch.

No unresolved critical reconciliation mismatch permits new risk.

---

# 34. MEMORY, CASES AND DECISION QUALITY

Memory domains:

- short-term;
- long-term;
- strategy;
- symbol;
- regime;
- failure;
- successful cases;
- rejected cases;
- research.

Never store:

- passwords;
- API keys;
- private credentials;
- authentication secrets.

## 34.1 Case Library

Every executed and rejected opportunity becomes a structured case containing:

- market state;
- Decision Snapshot;
- TradingIntent;
- strategy;
- prediction;
- probability;
- risk;
- execution;
- outcome;
- MFE;
- MAE;
- costs;
- exit;
- counterfactuals;
- decision-quality metrics.

## 34.2 Rejected Trade Intelligence

Measure:

- over-rejection;
- under-rejection;
- rejection quality.

## 34.3 Counterfactual Engine

Evaluate:

- alternative entry;
- alternative strategy;
- alternative size;
- alternative venue;
- delayed entry;
- no trade;
- portfolio alternative.

Counterfactual results cannot directly mutate live decisions.

## 34.4 Decision Quality

Evaluate:

```text
Prediction Quality
+
Timing Quality
+
Strategy Quality
+
Risk Quality
+
Portfolio Quality
+
Execution Quality
+
Information Quality
```

A profitable trade can be a bad decision.

A losing trade can be a good decision.

## 34.5 Luck vs Skill

Separate:

- prediction skill;
- strategy skill;
- execution skill;
- risk skill;
- randomness;
- unexpected events;
- path effects.

## 34.6 Cost of Inaction

For rejected opportunities:

```text
REJECTED
→ ACTUAL OUTCOME
→ OPPORTUNITY COST
```

For accepted opportunities:

```text
SELECTED TRADE
vs
BEST FEASIBLE ALTERNATIVE
```

---

# 35. RESEARCH, DATA AND AI SECURITY

## 35.1 Evidence Firewall

Research follows:

```text
CLAIM
→ SOURCE
→ SOURCE QUALITY
→ EVIDENCE CHECK
→ CROSS-CHECK
→ CONFIDENCE
→ STRUCTURED FACT
```

Unverified LLM output cannot become unrestricted trading data.

Source hierarchy:

```text
PRIMARY OFFICIAL
↓
REGULATED / EXCHANGE
↓
VERIFIED INSTITUTIONAL
↓
PEER-REVIEWED
↓
REPUTABLE SECONDARY
↓
UNVERIFIED
```

## 35.2 Crawler Governance

Respect:

- source terms;
- rate limits;
- licensing;
- attribution;
- duplicate detection;
- malicious content;
- prompt injection;
- poisoned documents;
- malicious files.

## 35.3 Research Sandbox

Research agents are isolated from:

- production credentials;
- production filesystem;
- production database;
- broker access;
- execution systems.

External content is:

```text
DATA, NOT INSTRUCTIONS
```

## 35.4 Agent Identity

Every autonomous agent has:

- identity;
- purpose;
- capabilities;
- permissions;
- resource limits;
- audit trail.

Agent communication is authenticated and authorized.

## 35.5 Deadlock

If agents cannot resolve a critical disagreement within the allowed time:

```text
ABSTAIN
→ DEFER
→ NO TRADE
```

No endless autonomous debate.

---

# 36. SECURITY

Required controls:

- startup authentication;
- MFA;
- RBAC;
- privileged re-authentication;
- encrypted credential storage;
- credential isolation;
- audit logging;
- configuration integrity;
- artifact signing;
- dependency scanning;
- vulnerability scanning;
- supply-chain verification;
- secure update pipeline;
- agent identity;
- research firewall;
- prompt-injection defense;
- AI evidence firewall.

AI memory must never contain production secrets.

---

# 37. CONFIGURATION GOVERNANCE

Configuration changes are transactional.

Every change records:

- version;
- author/agent identity;
- reason;
- affected components;
- old state;
- new state;
- validation;
- signature;
- timestamp.

Support:

```text
PROPOSE
→ VALIDATE
→ SNAPSHOT
→ APPLY TRANSACTIONALLY
→ VERIFY
→ COMMIT
```

Failure:

```text
ROLLBACK
→ VERIFY
→ AUDIT
```

No unsafe partial configuration is accepted.

---

# 38. DEPENDENCY GOVERNANCE

Every dependency has:

- purpose;
- version;
- license;
- security status;
- maintenance status;
- performance;
- alternatives;
- production/research classification.

Classify libraries:

```text
CORE
OPTIONAL PRODUCTION
RESEARCH
REJECTED
```

Requested libraries are not forced into production merely because they were requested.

---

# 39. SYSTEMIC DEPENDENCY RISK

Maintain a dependency graph covering:

```text
DATA
→ FEATURES
→ MODELS
→ STRATEGIES
→ PORTFOLIO
→ EXECUTION
→ ACCOUNT
```

and:

```text
BROKER
NETWORK
DATABASE
CREDENTIALS
CLOCK
COMPUTE
```

Track:

- data dependency concentration;
- model dependency concentration;
- infrastructure dependency concentration.

A common dependency failure must reduce the authority of all affected downstream capabilities.

---

# 40. RESILIENCE ARCHITECTURE

## 40.1 Broker and Exchange State

Broker states:

```text
CONNECTED
DEGRADED
HIGH_LATENCY
ORDER_RESTRICTED
READ_ONLY
DISCONNECTED
RECOVERING
RECONCILING
QUARANTINED
UNKNOWN
```

Exchange states:

```text
OPEN
PRE_OPEN
AUCTION
HALTED
LIMITED
CLOSED
MAINTENANCE
REOPENING
UNKNOWN
```

Account states:

```text
NORMAL
MARGIN_WARNING
MARGIN_RESTRICTED
MARGIN_CRITICAL
TRADING_RESTRICTED
LIQUIDATION_RISK
HALTED
RECOVERY
UNKNOWN
```

## 40.2 Active / Standby

Critical services may use:

```text
ACTIVE
↓
STANDBY
↓
FAILOVER
```

Candidates:

- Execution Core;
- broker connectivity;
- portfolio state;
- risk verifier;
- orchestration;
- databases.

## 40.3 Split-Brain Protection

Only one execution authority may be active for an execution domain.

Use:

- leases;
- leadership state;
- fencing;
- duplicate-submit prevention;
- authority epochs.

## 40.4 Dependency Controls

Implement:

- dependency circuit breakers;
- bulkheads;
- retry budgets;
- backpressure;
- priority-aware data shedding.

## 40.5 Resource Governor

Monitor:

- CPU;
- RAM;
- GPU;
- disk;
- network;
- queues;
- latency.

Priority:

```text
SAFETY
→ EXECUTION
→ MARKET DATA
→ RISK
→ RECONCILIATION
→ ANALYSIS
→ PREDICTION
→ DASHBOARD
→ RESEARCH
→ BACKGROUND TRAINING
```

Background work must never starve critical controls.

---

# 41. SELF-HEALING AND FAILURE BEHAVIOR

Safety state machine:

```text
NORMAL
→ CAUTION
→ RESTRICTED
→ DEFENSIVE
→ HALTED
→ RECOVERY
```

Master failure behavior:

```text
FAILURE
→ REDUCE AUTHORITY
→ REDUCE EXPOSURE
→ PRESERVE STATE
→ CANCEL / PROTECT
→ RECONCILE
→ RECOVER
→ VERIFY
→ RESTORE AUTHORITY GRADUALLY
```

Never:

```text
FAILURE
→ INCREASE RISK
```

Severe unresolved failures force DEFENSIVE or HALTED state.

The independent kill switch must operate independently of AI health.

---

# 42. CHAOS ENGINEERING

Inject controlled failures including:

- network outage;
- API outage;
- broker rejection;
- broker disconnection;
- process failure;
- database outage;
- stale data;
- malformed data;
- delayed messages;
- high latency;
- session transitions;
- hardware failure;
- OS failure;
- network partition;
- clock failure;
- dependency failure;
- configuration corruption;
- partial service failure;
- split-brain attempts.

Every experiment must verify:

- containment;
- state preservation;
- risk reduction;
- reconciliation;
- recovery;
- verification;
- safe resumption.

---

# 43. DIGITAL TWIN

The Digital Twin shall reproduce, where supported:

- market data;
- spread;
- liquidity;
- slippage;
- latency;
- partial fills;
- broker behavior;
- order rejection;
- failures;
- risk states;
- session transitions.

It must operate without production credentials.

Use it for:

- architecture changes;
- strategy validation;
- model validation;
- execution testing;
- chaos testing;
- recovery testing.

---

# 44. VALIDATION AND RESEARCH REALISM

## 44.1 Backtesting

Support:

- tick-level;
- event-driven;
- realistic spread;
- commissions;
- financing;
- slippage;
- latency;
- partial fills;
- market impact;
- portfolio interaction.

## 44.2 Backtest Realism Score

Score whether a backtest realistically represents:

- execution;
- spread;
- latency;
- liquidity;
- financing;
- market impact;
- partial fills;
- broker behavior;
- data availability.

## 44.3 Overfitting

Detect:

- parameter fragility;
- multiple-testing bias;
- data leakage;
- selection bias;
- excessive optimization;
- unstable regime dependence.

## 44.4 Validation Pipeline

Every production candidate passes:

```text
RESEARCH
→ BACKTEST
→ VALIDATION
→ WALK-FORWARD
→ OUT-OF-SAMPLE
→ STRESS
→ MONTE CARLO
→ REVERSE STRESS
→ DIGITAL TWIN
→ SHADOW
→ DEMO
→ CANARY
→ PRODUCTION
```

---

# 45. REALITY GAP AND STRUCTURAL BREAKS

Measure:

```text
BACKTEST
vs
SIMULATION
vs
SHADOW
vs
DEMO
vs
LIVE
```

Track divergence in:

- slippage;
- latency;
- fill rate;
- rejection;
- spread;
- market impact;
- PnL distribution;
- drawdown;
- strategy behavior.

Detect structural breaks before waiting for complete edge failure.

Causality and correlation must be explicitly tagged in research.

Research contamination controls must prevent future information from entering historical experiments.

---

# 46. AUTONOMOUS EVOLUTION

No autonomous improvement may directly modify production.

Every change produces a Change Proposal containing:

- Change Proposal ID;
- reason;
- affected modules;
- expected benefit;
- expected risk;
- evidence;
- tests;
- benchmark;
- rollback plan;
- dependency impact.

Canonical change loop:

```text
OBSERVE
→ HYPOTHESIS
→ PROPOSAL
→ SIMULATION
→ VALIDATION
→ STRESS
→ SHADOW
→ CHALLENGER
→ CANARY
→ GOVERNANCE
→ PRODUCTION
```

Production changes require:

```text
AUTHORIZE
→ BUILD
→ VERIFY
→ SIGN
→ TEST
→ SIMULATE
→ SNAPSHOT
→ SHADOW
→ CANARY
→ MONITOR
→ PROMOTE
or
→ ROLLBACK
```

Champion/Challenger:

```text
CHAMPION
│
├── PRODUCTION
│
CHALLENGERS
├── SHADOW
├── PAPER
└── VALIDATION
```

Rollback restores:

- model;
- strategy;
- configuration;
- feature schema;
- execution compatibility;
- dependency-compatible snapshot.

---

# 47. AI RESOURCE AND BEHAVIOR GOVERNANCE

AI Behavior Audit shall monitor:

- invalid outputs;
- unsupported claims;
- hallucination;
- inconsistent reasoning artifacts;
- policy violations;
- resource abuse;
- repeated failures;
- unsafe tool use;
- unexpected authority requests.

AI Resource Governor limits:

- CPU;
- RAM;
- GPU;
- network;
- task concurrency;
- runtime;
- external calls;
- storage;
- queue consumption.

AI cannot block emergency protection.

---

# 48. TECHNOLOGY ARCHITECTURE

## Python

Use primarily for:

- research;
- quantitative analysis;
- ML;
- backtesting;
- simulation;
- analytics;
- experiment management;
- high-level orchestration where latency permits.

## Rust / Native Layer

Use primarily for:

- execution;
- low-latency processing;
- safety-critical deterministic services;
- high-throughput native processing;
- concurrency-sensitive components.

C++ may be used only where justified by an external SDK, existing native dependency or measured performance requirement.

## Go

Use where justified for:

- APIs;
- data gateways;
- concurrency-oriented services.

## Java/C#

Use only where justified for:

- FIX;
- enterprise integration;
- required vendor infrastructure.

The implementation should minimize unnecessary language fragmentation.

---

# 49. CONCURRENCY AND PERFORMANCE

Use workload-appropriate:

- multiprocessing;
- asynchronous I/O;
- native compiled execution;
- vectorization;
- GPU acceleration;
- multithreading for suitable I/O;
- native extensions.

Do not force a fixed worker count.

Benchmark workload-specific concurrency.

Performance priority:

```text
CORRECTNESS
→ SAFETY
→ DETERMINISM
→ RELIABILITY
→ LATENCY
→ THROUGHPUT
→ RESOURCE EFFICIENCY
```

Correctness is never traded for speed.

---

# 50. DATA AND STORAGE ARCHITECTURE

Purpose-specific storage may include:

- PostgreSQL;
- TimescaleDB;
- QuestDB;
- ClickHouse;
- DuckDB;
- Redis;
- Parquet;
- vector databases.

The final production stack is selected through:

- measured workload requirements;
- reliability;
- operational simplicity;
- licensing;
- security;
- backup/recovery;
- query requirements.

No technology is mandatory merely because it appears in the candidate list.

---

# 51. DASHBOARD AND TERMINAL

The interface shall be:

- real-time;
- responsive;
- interactive;
- searchable;
- filterable;
- resizable;
- keyboard-driven;
- modular.

Functional concepts:

- global command bar;
- autocomplete;
- aliases;
- command history;
- keyboard navigation;
- tiled workspace;
- modular panels;
- portfolio analytics;
- market data;
- research;
- macro;
- news;
- risk;
- execution.

The design may be Bloomberg-inspired functionally but must not copy proprietary implementation or private data.

## 51.1 Command System

Format:

```text
[TICKER] [MODULE] [FUNCTION]
```

Examples:

```text
EURUSD CHART
EURUSD RISK
EURUSD NEWS
BTCUSD ANALYSIS
PORT RISK
MARKET SCAN
```

## 51.2 Global Status

Always display:

- system;
- market;
- risk;
- capital;
- AI;
- execution;
- data;
- broker;
- session;
- security;
- safety;
- readiness.

## 51.3 Global Alert Rail

Show:

- critical;
- safety;
- risk;
- capital;
- execution;
- data;
- model;
- security;
- reconciliation;
- incident alerts.

## 51.4 Required Operational Views

At minimum:

```text
MAIN
MARKET
NEWS
CHART
SESSIONS
ECONOMICS
INGESTION
FEATURES
STRATEGIES
RISK
ORDERS
LOGS
MONITOR
SECURITY
SAFETY
PORTFOLIO
WATCHLIST
SYMBOLS
AI
RESEARCH / CRAWLER
TRADEBOOK
HELP
SENTIMENT
PREDICTION
```

## 51.5 Order Views

- Order Book;
- Trade Book;
- Spread/Multi-Leg;
- Trigger Orders.

## 51.6 Portfolio Views

- Position Book;
- Holdings;
- Funds;
- Risk Budget;
- Capital Allocation;
- Factor Exposure;
- Scenario Analysis.

## 51.7 Market Views

- Exchange Messages;
- Market Movers;
- Scanners;
- Fundamentals;
- Corporate Actions;
- Liquidity;
- Microstructure.

## 51.8 Brain Map

Visualize:

```text
DATA
→ INTELLIGENCE
→ STRATEGIES
→ OPPORTUNITIES
→ PORTFOLIO
→ CAPITAL
→ RISK
→ SAFETY
→ ADMISSION
→ EXECUTION
→ POSITION
→ EXIT
→ LEARNING
```

## 51.9 Decision Inspector

Must show why a trade was:

- created;
- selected;
- admitted;
- rejected;
- deferred;
- exited.

## 51.10 Why-Not-Trade

Show explicit blocking reasons such as:

- insufficient evidence;
- low confidence;
- poor calibration;
- negative expected value;
- high cost;
- high spread;
- low liquidity;
- high tail risk;
- concentration;
- capital unavailable;
- risk unavailable;
- safety restriction;
- compliance restriction;
- stale data;
- unknown state;
- verifier disagreement.

---

# 52. CHARTING

Support:

- symbol selector;
- timeframe selector;
- zoom;
- pan;
- scale;
- crosshair;
- tooltips;
- indicators;
- overlays;
- volume;
- VWAP;
- volume profile;
- support/resistance;
- trade markers;
- session markers;
- order markers.

Timeframes:

```text
M1
M5
M15
M30
H1
H4
D1
W1
MN
```

Chart validation must verify:

- candle boundaries;
- timestamps;
- timeframe mapping;
- zoom;
- pan;
- scale;
- hover;
- live updates;
- historical data;
- trade markers.

---

# 53. OBSERVABILITY

Monitor:

- CPU;
- RAM;
- GPU;
- disk;
- network;
- queue depth;
- API health;
- broker health;
- database health;
- model health;
- strategy health;
- execution;
- latency;
- data quality;
- capital;
- risk;
- safety;
- reconciliation.

Maintain a Production Flight Recorder.

Every critical event must be replayable.

---

# 54. OPERATING CONSOLE AND HELP SYSTEM

Operating console exposes:

- events;
- logs;
- warnings;
- errors;
- execution;
- risk;
- model status;
- system health.

Help system includes:

- architecture;
- workflows;
- strategies;
- dashboard;
- commands;
- security;
- configuration;
- troubleshooting;
- emergency procedures;
- recovery;
- FAQ;
- operational handbook.

---

# 55. DATABASE AND FINANCIAL TRUTH

Financial truth shall not depend on the Orchestrator.

The ledger, reconciliation system and independent accounting path maintain authoritative financial state.

No dashboard display may become financial truth merely because it renders a value.

---

# 56. ZERO-TOLERANCE ENGINEERING STANDARD

Production implementation shall contain:

```text
ZERO STUBS
ZERO PLACEHOLDERS
ZERO DUMMY PRODUCTION MODULES
ZERO FAKE INTEGRATIONS
ZERO EMPTY PRODUCTION FUNCTIONS
ZERO UNRESOLVED CRITICAL TODOs
ZERO UNSIGNED PRODUCTION ARTIFACTS
ZERO UNVERIFIED CRITICAL CHANGES
```

Every claimed feature requires implementation evidence.

---

# 57. TODO / REMEDIATION REGISTER

Every defect/task must contain:

```text
ID
SEVERITY
CATEGORY
COMPONENT
DESCRIPTION
ROOT CAUSE
DEPENDENCY
SOLUTION
STATUS
TEST STATUS
VERIFICATION
REGRESSION STATUS
VERSION
TIMESTAMP
EVIDENCE
```

Task state:

```text
OPEN
→ IN_PROGRESS
→ IMPLEMENTED
→ TESTING
→ VERIFIED
→ REGRESSION
→ COMPLETED
```

Critical defects cannot be closed without regression evidence.

---

# 58. MASTER DEFECT LOOP

For every defect:

```text
DETECT
→ REPRODUCE
→ CONTAIN
→ CLASSIFY
→ ROOT CAUSE
→ FIX
→ UNIT TEST
→ INTEGRATION TEST
→ NEGATIVE TEST
→ REGRESSION
→ INDEPENDENT VERIFICATION
→ DOCUMENT
→ CLOSE
```

No batching of known critical defects merely for convenience.

---

# 59. MASTER PRODUCTION TRADING LOOP

```text
OBSERVE
→ INGEST
→ REASONABLENESS CHECK
→ VALIDATE
→ RECONSTRUCT
→ BUILD MARKET STATE
→ VERIFY CAPABILITY
→ ANALYZE
→ PREDICT / ABSTAIN
→ CALIBRATE
→ MODEL RISK
→ GENERATE OPPORTUNITIES
→ SCORE
→ EXPECTED VALUE
→ LIQUIDITY
→ CAPACITY
→ PATH RISK
→ OPTIMIZE PORTFOLIO
→ CHECK CAPITAL
→ RESERVE
→ CREATE INTENT
→ VALIDATE FRESHNESS
→ CHECK RATE LIMITS
→ CHECK COMPLIANCE
→ RISK
→ SAFETY INVARIANTS
→ SAFETY KERNEL
→ INDEPENDENT RISK VERIFICATION
→ TRADE ADMISSION
→ EXECUTE
→ EXECUTION VERIFICATION
→ POSITION MANAGEMENT
→ EXIT MANAGEMENT
→ RECONCILIATION
→ ACCOUNTING
→ TCA
→ DECISION QUALITY
→ COUNTERFACTUAL
→ LEARNING
→ GOVERNANCE
→ REPEAT
```

---

# 60. COMPLETE NO-TRADE STATES

Valid no-trade states include:

```text
NO OPPORTUNITY
LOW CONFIDENCE
LOW CALIBRATION
NEGATIVE EXPECTED VALUE
HIGH COST
HIGH SPREAD
LOW LIQUIDITY
HIGH TAIL RISK
EXCESS CONCENTRATION
HIGH UNCERTAINTY
DEGRADED MODEL
DEGRADED STRATEGY
INSUFFICIENT DATA
STALE DATA
BROKER RESTRICTED
ACCOUNT RESTRICTED
CAPITAL UNAVAILABLE
RISK UNAVAILABLE
SAFETY RESTRICTED
COMPLIANCE RESTRICTED
VERIFIER DISAGREEMENT
UNKNOWN
```

Remaining flat is a valid successful outcome.

---

# 61. MASTER DISAGREEMENT PROTOCOL

When critical components disagree:

```text
DISAGREEMENT
→ FREEZE NEW RISK
→ PRESERVE EVIDENCE
→ INDEPENDENT VERIFICATION
→ RECONCILIATION
→ STATE RESTORATION
→ SAFETY RECHECK
→ GRADUAL RESUME
```

If disagreement cannot be resolved safely:

```text
NO TRADE
```

---

# 62. MASTER FAILURE PRINCIPLE

```text
UNKNOWN
→ LESS AUTHORITY

DEGRADED
→ LESS AUTHORITY

DISAGREEMENT
→ LESS AUTHORITY

FAILURE
→ LESS AUTHORITY

RECOVERY
→ VERIFIED AUTHORITY RESTORATION
```

The system must never infer that an unverified recovery is normal.

---

# 63. RELEASE GATES

Production deployment requires all mandatory gates:

- Architecture;
- Data Integrity;
- Point-in-Time;
- Security;
- Capital;
- Risk;
- Safety Invariant;
- Safety Kernel;
- Independent Risk Verification;
- Execution;
- Independent Execution Verification;
- Reconciliation;
- Accounting;
- Backtest;
- Walk-Forward;
- Out-of-Sample;
- Monte Carlo;
- Scenario;
- Reverse Stress;
- Digital Twin;
- Chaos;
- Shadow;
- Demo;
- Canary;
- Rollback;
- Observability;
- Documentation;
- Zero-Stub;
- Final Independent Audit.

No gate may be silently waived.

---

# 64. COMPLETE SYSTEM READINESS

Production readiness is:

```text
MIN(
DATA READINESS,
MODEL READINESS,
STRATEGY READINESS,
PORTFOLIO READINESS,
CAPITAL READINESS,
RISK READINESS,
SAFETY READINESS,
EXECUTION READINESS,
BROKER READINESS,
SECURITY READINESS,
RESOURCE READINESS,
RECOVERY READINESS,
COMPLIANCE READINESS,
ACCOUNTING READINESS
)
```

The weakest critical dimension controls permission to trade.

---

# 65. DEVELOPMENT ROADMAP

## Phase 0 — Forensic Audit

Deliver:

- repository inventory;
- architecture map;
- dependency map;
- code-quality audit;
- security audit;
- zero-stub audit;
- capability matrix;
- gap register;
- remediation register.

Exit criteria: complete evidence-backed baseline.

## Phase 1 — Foundation

Implement:

- repository boundaries;
- contracts;
- build system;
- versioning;
- authority model;
- configuration model;
- core schemas.

## Phase 2 — Event and Time Infrastructure

Implement:

- Event Bus;
- Event Sourcing;
- Clock;
- Calendar;
- correlation/causation;
- deterministic replay.

## Phase 3 — Data

Implement:

- provider adapters;
- Symbol Master;
- quality;
- confidence;
- point-in-time storage;
- lineage;
- reasonableness;
- reference pricing;
- failover;
- licensing governance.

## Phase 4 — Intelligence

Implement:

- Market State;
- feature pipeline;
- regime;
- Analyst Brain;
- Prediction Brain;
- calibration;
- model risk;
- disagreement;
- distribution shift;
- abstention.

## Phase 5 — Strategy

Implement:

- strategy framework;
- strategy registry;
- trading licenses;
- lifecycle;
- eligibility;
- MTF resolver;
- robustness;
- capacity;
- edge decay;
- quarantine.

## Phase 6 — Opportunity and Portfolio

Implement:

- Opportunity Queue;
- Expected Net Value;
- liquidity-adjusted scoring;
- portfolio optimizer;
- factor risk;
- path risk;
- opportunity competition.

## Phase 7 — Capital and Treasury

Implement:

- capital buckets;
- reservations;
- treasury;
- currency management;
- financing;
- funding;
- collateral.

## Phase 8 — Risk

Implement:

- risk budgets;
- hard limits;
- marginal/incremental risk;
- liquidity stress;
- tail risk;
- loss limits;
- loss velocity;
- scenario engine;
- reverse stress;
- drawdown recovery;
- risk hysteresis;
- uncertainty budgets.

## Phase 9 — Safety and Verification

Implement:

- Safety Invariants;
- Safety Kernel;
- formal state verification;
- independent risk verifier;
- Trade Admission;
- safe-by-disagreement;
- kill switch.

## Phase 10 — Execution

Implement:

- TradingIntent;
- pre-trade validator;
- rate governance;
- fat-finger;
- self-trade prevention;
- cancel-on-disconnect;
- Execution Core;
- MT5;
- FIX/API;
- broker/exchange states;
- venue scoring;
- execution toxicity;
- execution verifier.

## Phase 11 — Position and Exit

Implement:

- Position Manager;
- Position Integrity Contract;
- Thesis Engine;
- Exit Engine;
- timeout;
- opportunity competition;
- emergency exits;
- continuous reassessment.

## Phase 12 — Reconciliation and Accounting

Implement:

- execution reconciliation;
- broker reconciliation;
- portfolio reconciliation;
- immutable ledger;
- shadow ledger;
- PnL;
- funding;
- financing;
- collateral;
- currency translation.

## Phase 13 — Learning and Governance

Implement:

- Case Library;
- rejected-trade intelligence;
- counterfactuals;
- Decision Quality;
- luck-vs-skill;
- cost-of-inaction;
- experiment registry;
- model/strategy registries;
- champion/challenger;
- rollback.

## Phase 14 — Digital Twin and Validation

Implement:

- realistic backtesting;
- realism scoring;
- overfitting controls;
- walk-forward;
- OOS;
- Monte Carlo;
- scenarios;
- reverse stress;
- Digital Twin;
- Reality Gap.

## Phase 15 — Security and Agent Safety

Implement:

- authentication;
- MFA;
- RBAC;
- artifact signing;
- supply-chain security;
- dependency scanning;
- research firewall;
- sandboxing;
- prompt-injection defense;
- AI evidence firewall;
- agent identity.

## Phase 16 — Resilience

Implement:

- self-healing;
- incident management;
- runbooks;
- Flight Recorder;
- active/standby;
- split-brain protection;
- DR;
- hardware/OS/network/clock failure tests;
- dependency circuit breakers;
- bulkheads;
- retry budgets;
- backpressure;
- data shedding.

## Phase 17 — Terminal and Dashboard

Implement:

- terminal;
- command system;
- Brain Map;
- Decision Inspector;
- Why-Not-Trade;
- Autonomy Monitor;
- readiness;
- risk;
- capital;
- execution;
- market;
- research;
- charting;
- alerts;
- help system.

## Phase 18 — Production Deployment

```text
LIMITED PRODUCTION
→ CANARY
→ CONTROLLED PRODUCTION
→ FULL AUTHORIZED PRODUCTION
```

## Phase 19 — Continuous Evolution

Continuous:

- audit;
- security testing;
- model drift monitoring;
- strategy edge monitoring;
- dependency monitoring;
- research;
- controlled experimentation;
- shadow testing;
- canary;
- rollback;
- re-audit.

---

# 66. TESTING STRATEGY

Every component requires, as applicable:

```text
UNIT TEST
INTEGRATION TEST
CONTRACT TEST
PROPERTY TEST
NEGATIVE TEST
FAULT-INJECTION TEST
CONCURRENCY TEST
PERFORMANCE TEST
SECURITY TEST
REPLAY TEST
REGRESSION TEST
INDEPENDENT VERIFICATION
```

Every trading path requires:

- normal case;
- rejection case;
- stale-data case;
- stale-intent case;
- malformed-data case;
- broker-failure case;
- duplicate-message case;
- duplicate-order case;
- timeout case;
- partial-fill case;
- reconciliation mismatch;
- verifier disagreement;
- emergency halt;
- recovery.

---

# 67. ACCEPTANCE MATRIX

## Architecture

- [ ] Multi-plane architecture operational.
- [ ] Orchestrator operational.
- [ ] Event fabric operational.
- [ ] Event sourcing operational.
- [ ] Authority hierarchy enforced.
- [ ] Capability Registry operational.
- [ ] Dependency Graph operational.
- [ ] Formal state verification operational.
- [ ] Independent verification operational.

## Data

- [ ] Unified ingestion.
- [ ] Market-data reasonableness.
- [ ] Reference price.
- [ ] Data quality.
- [ ] Data confidence.
- [ ] Point-in-time.
- [ ] Lineage.
- [ ] Provider failover.
- [ ] Licensing governance.
- [ ] Symbol Master.
- [ ] Global Clock.
- [ ] Market Calendar.
- [ ] Distribution-shift detection.

## Intelligence

- [ ] Market State.
- [ ] Regime.
- [ ] Research Brain.
- [ ] Analyst Brain.
- [ ] Prediction Brain.
- [ ] Abstention.
- [ ] Calibration.
- [ ] Disagreement.
- [ ] Model Risk.
- [ ] Model drift.
- [ ] Structural-break detection.
- [ ] Forecast distributions.

## Strategy

- [ ] Strategy registry.
- [ ] Eligibility.
- [ ] Trading License.
- [ ] Lifecycle.
- [ ] MTF resolver.
- [ ] Portfolio weighting.
- [ ] Conflict resolution.
- [ ] Robustness.
- [ ] Capacity.
- [ ] Edge decay.
- [ ] Quarantine.
- [ ] Risk multipliers.

## Portfolio / Capital / Risk

- [ ] Portfolio optimizer.
- [ ] Capital Governance.
- [ ] Risk budgets.
- [ ] Risk reservations.
- [ ] Marginal risk.
- [ ] Incremental risk.
- [ ] Factor risk.
- [ ] Correlation regimes.
- [ ] Crisis correlation.
- [ ] Liquidity stress.
- [ ] Scenario engine.
- [ ] Reverse stress.
- [ ] Tail risk.
- [ ] Loss limits.
- [ ] Loss velocity.
- [ ] Drawdown recovery.
- [ ] Risk hysteresis.
- [ ] Uncertainty budget.
- [ ] Dependency concentration.

## Safety

- [ ] Safety Invariants.
- [ ] Safety Kernel.
- [ ] Unknown state.
- [ ] Information-Degraded state.
- [ ] Independent Risk Verifier.
- [ ] Trade Admission.
- [ ] Safe-by-disagreement.
- [ ] Independent Kill Switch.

## Execution

- [ ] TradingIntent.
- [ ] Intent expiration.
- [ ] Pre-trade validation.
- [ ] Rate governance.
- [ ] Fat-finger protection.
- [ ] Self-trade prevention.
- [ ] Cancel-on-disconnect.
- [ ] Execution Core.
- [ ] MT5.
- [ ] FIX/API.
- [ ] Broker state.
- [ ] Exchange state.
- [ ] Venue scoring.
- [ ] Execution toxicity.
- [ ] Execution circuit breaker.
- [ ] Execution Verifier.

## Position / Exit

- [ ] Position Manager.
- [ ] Position Integrity Contract.
- [ ] Thesis Engine.
- [ ] Continuous reassessment.
- [ ] Exit Engine.
- [ ] Timeout.
- [ ] Opportunity competition.
- [ ] Portfolio emergency exits.
- [ ] Exit attribution.

## Financial

- [ ] Immutable ledger.
- [ ] Shadow accounting.
- [ ] PnL attribution.
- [ ] Funding.
- [ ] Financing.
- [ ] Currency translation.
- [ ] Collateral accounting.
- [ ] Reconciliation.

## Learning / Governance

- [ ] Case Library.
- [ ] Rejected-trade intelligence.
- [ ] Counterfactual Engine.
- [ ] Decision Quality.
- [ ] Luck-vs-Skill.
- [ ] Cost-of-Inaction.
- [ ] Experiment Registry.
- [ ] Multiple-hypothesis control.
- [ ] Model Registry.
- [ ] Strategy Registry.
- [ ] Champion/Challenger.
- [ ] Canary.
- [ ] Change Proposal.
- [ ] Production Snapshot.
- [ ] Rollback.

## Security

- [ ] Authentication.
- [ ] MFA.
- [ ] RBAC.
- [ ] Credential security.
- [ ] Supply-chain security.
- [ ] Artifact signing.
- [ ] Research firewall.
- [ ] Agent sandbox.
- [ ] Prompt-injection defense.
- [ ] AI evidence firewall.
- [ ] Agent identity.
- [ ] Vulnerability scanning.

## Resilience

- [ ] Self-healing.
- [ ] Incident management.
- [ ] Runbooks.
- [ ] Flight Recorder.
- [ ] Active/Standby.
- [ ] Split-brain protection.
- [ ] Disaster Recovery.
- [ ] Hardware failure testing.
- [ ] OS failure testing.
- [ ] Network partition testing.
- [ ] Clock failure testing.
- [ ] Dependency circuit breakers.
- [ ] Bulkheads.
- [ ] Retry budgets.
- [ ] Backpressure.
- [ ] Data shedding.

## Validation

- [ ] Backtesting.
- [ ] Backtest realism.
- [ ] Overfitting detection.
- [ ] Walk-forward.
- [ ] OOS.
- [ ] Monte Carlo.
- [ ] Digital Twin.
- [ ] Reality Gap.
- [ ] Scenario.
- [ ] Reverse Stress.
- [ ] Adversarial testing.
- [ ] Chaos testing.
- [ ] Independent audit.

## Code Quality

- [ ] Zero stubs.
- [ ] Zero placeholders.
- [ ] Zero dummy production implementations.
- [ ] Zero fake integrations.
- [ ] Zero critical unresolved defects.
- [ ] Complete regression tests.
- [ ] Reproducible builds.
- [ ] Signed production artifacts.

---

# 68. NON-NEGOTIABLE IMPLEMENTATION RULES

The implementing Agentic AI shall never:

- bypass Safety Invariants;
- bypass Safety Kernel;
- bypass hard risk;
- bypass Capital Governance;
- execute stale decisions;
- execute invalid TradingIntent;
- execute without Trade Admission;
- submit unvalidated orders;
- permit duplicate execution;
- permit split-brain execution;
- treat UNKNOWN as NORMAL;
- use future information;
- promote solely on in-sample performance;
- equate prediction accuracy with profitability;
- modify production directly from research;
- store credentials in AI memory;
- expose private chain-of-thought;
- suppress reconciliation mismatches;
- ignore verifier disagreement;
- resume automatically after unresolved catastrophic failure;
- close tasks without evidence;
- close critical defects without regression;
- deploy unsigned production artifacts;
- sacrifice correctness for speed.

---

# 69. MASTER ENGINEERING CYCLE

```text
INSPECT
→ RESEARCH
→ ARCHITECT
→ IMPLEMENT
→ TEST
→ MEASURE
→ VERIFY
→ STRESS
→ REVERSE STRESS
→ FIX
→ REGRESS
→ DOCUMENT
→ AUDIT
→ DEPLOY
→ MONITOR
→ RECONCILE
→ LEARN
→ GOVERN
→ RE-AUDIT
```

This cycle continues throughout the system lifecycle.

---

# 70. FINAL UNIFIED GOVERNING CONTROL CHAIN

```text
LEGAL / REGULATORY / JURISDICTION
        ↓
EXCHANGE / BROKER
        ↓
SAFETY INVARIANTS
        ↓
SAFETY KERNEL
        ↓
CAPITAL GOVERNANCE
        ↓
HARD RISK
        ↓
INDEPENDENT RISK VERIFIER
        ↓
TRADE ADMISSION
        ↓
RATE / FAT-FINGER / SELF-TRADE CONTROLS
        ↓
EXECUTION CORE
        ↓
EXECUTION VERIFIER
        ↓
POSITION MANAGER
        ↓
EXIT ENGINE
        ↓
RECONCILIATION
        ↓
ACCOUNTING
        ↓
LEARNING
        ↓
GOVERNANCE
        ↓
CONTROLLED EVOLUTION
```

---

# 71. FINAL UNIFIED OBJECTIVE

The completed EAQTS shall behave as:

> **A safety-controlled, independently verified, capital-governed, execution-aware, exit-centric, resilient and autonomous quantitative trading operating system capable of continuously observing markets, validating information, evaluating opportunities, deciding when not to trade, allocating capital and risk, executing safely, managing and exiting positions, reconciling external reality, maintaining financial truth, evaluating decision quality, learning under governance, surviving component failures, and improving through controlled evolution without bypassing immutable legal, safety, capital, risk, security, execution or governance controls.**

The system must be:

```text
AUTONOMOUS
but not unrestricted.

INTELLIGENT
but not blindly trusted.

ADAPTIVE
but not self-authorizing.

FAST
but never at the expense of correctness.

SELF-HEALING
but not self-modifying without governance.

SELF-IMPROVING
but not self-overriding.

PROFIT-SEEKING
but capital-preserving first.

COMPLEX
only where measurable value justifies complexity.
```

# 72. CANONICAL DESIGN DECISIONS

The following decisions remove ambiguity between the supplied versions:

1. **Version 2.4 is the single authoritative design.**
2. **Version 2.3 controls the final safety, execution, resilience, compliance and autonomous-operating requirements.**
3. **Version 2.2 supplies the complete verification, capital, risk, governance, learning and release-control foundation.**
4. **Version 2.1 supplies the foundational implementation structure, strategy/intelligence/dashboard/MT5 concepts and development discipline where not superseded.**
5. **Trade Admission is the only final execution authorization.**
6. **Independent Risk Verification is mandatory before new risk.**
7. **Independent Execution Verification is mandatory after execution.**
8. **Exit intelligence is first-class, not an afterthought.**
9. **No-trade, abstention, defer and invalid are first-class outcomes.**
10. **Probability thresholds are configurable evidence gates, never absolute execution authority.**
11. **Position sizing is governed; no fixed lot size overrides risk, liquidity, margin or broker constraints.**
12. **Trade-count targets are allocation preferences only; hard portfolio risk is always superior.**
13. **Python is the primary research/ML/analytics environment.**
14. **Rust is the preferred native execution/safety implementation; C++ is allowed only where technically justified.**
15. **MT5 is an execution/data adapter and terminal integration, not the sole system brain.**
16. **Research is isolated from production.**
17. **Autonomous changes require proposals, evidence, simulation, validation, shadowing, challenge, canary and governance.**
18. **Unknown, disagreement and degraded states reduce authority.**
19. **Failure always moves the system toward less risk.**
20. **Complexity must produce measurable value.**
21. **Zero stubs, placeholders, fake integrations and unresolved critical defects are release blockers.**
22. **Production readiness is controlled by the weakest critical readiness dimension.**
23. **All financial state must be independently reconcilable.**
24. **Every trading decision must be reconstructable from immutable provenance.**
25. **The system must continuously re-audit itself after implementation and deployment.**

---

# 73. DOCUMENT STATUS

**EAQTS Version 2.4 — Unified Master Design and Implementation Plan**

This document is the canonical consolidated baseline for subsequent:

- architecture work;
- repository implementation;
- module design;
- code generation;
- testing;
- verification;
- dashboards;
- MT5 integration;
- deployment;
- operations;
- security;
- autonomous evolution;
- nano-granular implementation TODO decomposition.

No separate 2.1/2.2/2.3 requirement should be implemented independently after adoption of this baseline unless explicitly introduced as a Version 2.4+ change proposal.
