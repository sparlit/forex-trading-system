# EAQTS V2.4 Consolidated Design

This document merges the specifications from EAQTS versions 2.1, 2.2, and 2.3 into a single unified reference as described in Section 0 of `EAQTS_V2.4_Unified_Master_Design_and_Implementation_Plan.md`.

* **Version 2.1** – foundational architecture, implementation phases, trading, intelligence, dashboard, MT5 design.
* **Version 2.2** – safety, verification, capital governance, portfolio/risk, execution integrity, learning, resilience, release‑gate expansion.
* **Version 2.3** – operating‑system controls, execution safety, exits, compliance, treasury, research security, dependency resilience, AI governance, advanced failure handling.

The consolidated rule set is:
```
2.3 CONTROL / SAFETY / OPERATING‑SYSTEM ENHANCEMENTS
        +
2.2 GOVERNANCE / VERIFICATION / CAPITAL / RISK FOUNDATION
        +
2.1 IMPLEMENTATION / TRADING / INTELLIGENCE / UI FOUNDATION
        =
EAQTS 2.4 UNIFIED BASELINE
```

All repeated concepts are represented once and later generalized rules override earlier specifics.

*Key updates*:\
- Fixed‑lot sizing replaced by governed sizing.
- Trade‑count targets become configurable allocation targets subordinate to hard portfolio‑risk.
- Probability remains a qualification input, never an execution authority.
- Rust/C++ remains the native low‑latency execution class; Python stays the research/ML/analytics class.

The following sections of this consolidated design are implemented in code:
- **Event Bus** (`src/event_bus`)
- **Market State Engine** (`src/market_state_engine`)
- **Opportunity Engine** (`src/opportunity_engine`)
- **Portfolio Engine** (`src/portfolio_engine`)
- **Risk Engine** (`src/risk_engine`)
- **Safety Invariant Engine** (`src/safety_invariant_engine`)
- **Safety Kernel** (`src/safety_kernel`)
- **Trade Admission** (`src/trade_admission`)
- **Execution Core** (`src/execution_core`)
- **Position Manager** (`src/position_manager`)
- **Exit Engine** (`src/exit_engine`)

Further sections (learning governance, autonomy model, CI/CD, documentation, release process) are defined in their respective modules/files.
