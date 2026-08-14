# EAQTS V2.4 Nano‑Granular Phased TODO Register

This register lists the nano‑granular implementation phases derived from the unified master design (Section 0‑6). Each entry is a standalone, trackable work item.

| Phase | ID | Description | Status |
|-------|----|-------------|--------|
| 0 | `phase0_consolidate` | Consolidate V2.1, V2.2, V2.3 specifications into unified baseline per Section 0. | completed |
| 1 | `phase1_define_identity` | Document system identity, mission, and list of capabilities per Section 1. | completed |
| 2 | `phase2_setup_repo_structure` | Create project directories for planes: control, data, intelligence, strategy, opportunity, safety. | completed |
| 2 | `phase2_impl_event_bus` | Implement Event‑Bus (V2.1 spec) in `src/event_bus` with SQLite store. | completed |
| 2 | `phase2_impl_market_state_engine` | Build Market State Engine skeleton integrating data‑plane feeds. | completed |
| 2 | `phase2_impl_opportunity_engine` | Create Opportunity Engine with BUY/SELL/NO‑TRADE decision API. | completed |
| 3 | `phase3_impl_portfolio_engine` | Develop Portfolio Engine handling allocation, capital governance, risk budgets. | completed |
| 3 | `phase3_impl_risk_engine` | Add Risk Engine implementing hard portfolio‑risk limits and independent risk verification. | completed |
| 3 | `phase3_impl_safety_invariant` | Code Safety Invariant Engine enforcing immutable safety rules. | completed |
| 3 | `phase3_impl_safety_kernel` | Implement Safety Kernel for emergency controls and compliance checks. | completed |
| 4 | `phase4_impl_trade_admission` | Create Trade Admission component respecting authority hierarchy. | completed |
| 4 | `phase4_impl_execution_core` | Develop Execution Core with MT5, FIX, and Broker/API routing. | completed |
| 4 | `phase4_impl_position_manager` | Add Position Manager to track open positions and state changes. | completed |
| 4 | `phase4_impl_exit_engine` | Implement Exit Engine for exit strategies and TCA. | completed |
| 5 | `phase5_impl_learning_governance` | Integrate Learning / Governance pipeline for controlled self‑learning. | completed |
| 5 | `phase5_impl_autonomy_model` | Encode Autonomy Model matrix and authority levels (L0‑L9). | completed |
| 6 | `phase6_testing_framework` | Set up pytest suites covering each engine (unit, integration, performance). | completed |
| 6 | `phase6_ci_cd_pipeline` | Configure GitHub Actions to run lint, typecheck, tests, and build Docker image. | completed |
| 6 | `phase6_documentation` | Generate markdown docs for each plane and API reference. | completed |
| 6 | `phase6_release_governance` | Create release process with version bump, changelog, and safety gate. | completed |

*All items are completed.*