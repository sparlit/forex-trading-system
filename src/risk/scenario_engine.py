from __future__ import annotations

"""Scenario and Reverse Stress Engine – V2.2 (Sections 61–63 / EAQTS-3093-3117)
Provides deterministic scenario simulation and reverse stress analysis.
"""

import logging
import uuid
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class ScenarioType(Enum):
    PRICE_SHOCK = auto()
    RATE_SHOCK = auto()
    VOLATILITY_SHOCK = auto()
    LIQUIDITY_SHOCK = auto()
    SPREAD_SHOCK = auto()
    BROKER_OUTAGE = auto()
    DATA_OUTAGE = auto()
    LATENCY = auto()
    MULTI_FACTOR = auto()


@dataclass
class Scenario:
    scenario_id: str
    name: str
    scenario_type: ScenarioType
    parameters: dict[str, Any]
    expected_impact: dict[str, Any]


@dataclass
class ScenarioResult:
    scenario_id: str
    portfolio_impact: dict[str, Any]
    position_impacts: dict[str, Any]
    surviving_positions: list[dict[str, Any]]
    breached_limits: list[str]


class ScenarioEngine:
    """Runs predefined and ad‑hoc scenarios against a set of positions.
    The engine is deliberately simple: it applies the parameter transformations
    directly to position sizes and records simple impact metrics.
    """

    def __init__(self) -> None:
        self.scenarios: list[Scenario] = []
        self._populate_predefined()
        logger.info("ScenarioEngine initialized with %d scenarios", len(self.scenarios))

    def _populate_predefined(self) -> None:
        # Helper to create a scenario dict
        def make(name: str, stype: ScenarioType, params: dict[str, Any], impact: dict[str, Any]) -> Scenario:
            return Scenario(
                scenario_id=str(uuid.uuid4()),
                name=name,
                scenario_type=stype,
                parameters=params,
                expected_impact=impact,
            )
        self.scenarios.extend([
            make(
                "USD +/-3%",
                ScenarioType.PRICE_SHOCK,
                {"symbol": "USD", "pct_change": 0.03},
                {"expected_pnl": "~3% of USD exposure"},
            ),
            make(
                "Rates +/-100bps",
                ScenarioType.RATE_SHOCK,
                {"bps_change": 100},
                {"expected_pnl": "rate sensitive positions affected"},
            ),
            make(
                "Gold +/-8%",
                ScenarioType.PRICE_SHOCK,
                {"symbol": "XAU", "pct_change": 0.08},
                {"expected_pnl": "~8% of gold exposure"},
            ),
            make(
                "Equity -10%",
                ScenarioType.PRICE_SHOCK,
                {"pct_change": -0.10},
                {"expected_pnl": "negative equity PnL"},
            ),
            make(
                "Crypto -30%",
                ScenarioType.PRICE_SHOCK,
                {"pct_change": -0.30},
                {"expected_pnl": "large crypto drawdown"},
            ),
            make(
                "Volatility x2",
                ScenarioType.VOLATILITY_SHOCK,
                {"multiplier": 2.0},
                {"expected_risk": "doubling of vol-based VaR"},
            ),
            make(
                "Spread x5",
                ScenarioType.SPREAD_SHOCK,
                {"multiplier": 5.0},
                {"expected_cost": "higher transaction cost"},
            ),
            make(
                "Liquidity -70%",
                ScenarioType.LIQUIDITY_SHOCK,
                {"multiplier": 0.3},
                {"expected_impact": "reduced fill rates"},
            ),
        ])

    def run_scenario(self, scenario: Scenario, positions: list[dict[str, Any]], portfolio_state: dict[str, Any]) -> ScenarioResult:
        """Apply a single scenario to the supplied positions.
        The implementation is deliberately lightweight: it mutates a copy of the
        positions according to the scenario parameters and records simple metrics.
        """
        logger.debug("Running scenario %s (%s)", scenario.name, scenario.scenario_id)
        # Deep copy positions to avoid side effects
        simulated = [dict(p) for p in positions]
        breached: list[str] = []
        # Simple rule set based on scenario type
        if scenario.scenario_type == ScenarioType.PRICE_SHOCK:
            pct = scenario.parameters.get("pct_change", 0.0)
            for pos in simulated:
                size = pos.get("size", 0.0)
                pos["size"] = size * (1 + pct)
        elif scenario.scenario_type == ScenarioType.VOLATILITY_SHOCK:
            mult = scenario.parameters.get("multiplier", 1.0)
            portfolio_state["volatility_multiplier"] = mult
        elif scenario.scenario_type == ScenarioType.SPREAD_SHOCK:
            mult = scenario.parameters.get("multiplier", 1.0)
            portfolio_state["spread_multiplier"] = mult
        elif scenario.scenario_type == ScenarioType.LIQUIDITY_SHOCK:
            mult = scenario.parameters.get("multiplier", 1.0)
            portfolio_state["liquidity_multiplier"] = mult
        # Additional types could be added similarly
        # Compute simple impact metrics
        total_before = sum(p.get("size", 0.0) for p in positions)
        total_after = sum(p.get("size", 0.0) for p in simulated)
        pnl = total_after - total_before
        portfolio_impact = {"pnl": pnl, "total_before": total_before, "total_after": total_after}
        position_impacts = {p.get("id", str(idx)): {"original": orig.get("size"), "after": sim.get("size")} for idx, (orig, sim) in enumerate(zip(positions, simulated))}
        surviving = [p for p in simulated if p.get("size", 0) != 0]
        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            portfolio_impact=portfolio_impact,
            position_impacts=position_impacts,
            surviving_positions=surviving,
            breached_limits=breached,
        )
        logger.info("Scenario %s completed: PnL %.2f", scenario.name, pnl)
        return result

    def run_all_scenarios(self, positions: list[dict[str, Any]], portfolio_state: dict[str, Any]) -> list[ScenarioResult]:
        results: list[ScenarioResult] = []
        for s in self.scenarios:
            results.append(self.run_scenario(s, positions, portfolio_state.copy()))
        logger.info("Executed %d scenarios", len(results))
        return results

    def compare_scenarios(self, results: list[ScenarioResult]) -> dict[str, Any]:
        """Rank scenarios by absolute PnL impact magnitude.
        Returns a dict mapping scenario_id to a rank (1 = most severe).
        """
        sorted_res = sorted(results, key=lambda r: abs(r.portfolio_impact.get("pnl", 0)), reverse=True)
        ranking = {r.scenario_id: idx + 1 for idx, r in enumerate(sorted_res)}
        logger.debug("Scenario ranking computed")
        return ranking


@dataclass
class FailureObjective:
    objective_id: str
    name: str
    target_metric: str
    threshold: float
    severity: int


class ReverseStressEngine:
    """Searches for minimal stress scenarios that trigger failure objectives.
    The implementation is a simple heuristic: it iterates over predefined
    scenarios and checks whether any combination breaches a given objective.
    """

    def __init__(self) -> None:
        self.objectives: list[FailureObjective] = self.define_failure_objectives()
        logger.info("ReverseStressEngine initialized with %d objectives", len(self.objectives))

    def define_failure_objectives(self) -> list[FailureObjective]:
        # Example objectives – can be extended via config in a real system
        return [
            FailureObjective(
                objective_id="obj-1",
                name="Hard Risk Breach",
                target_metric="var",
                threshold=0.2,
                severity=5,
            ),
            FailureObjective(
                objective_id="obj-2",
                name="Margin Failure",
                target_metric="margin_ratio",
                threshold=0.15,
                severity=4,
            ),
            FailureObjective(
                objective_id="obj-3",
                name="Drawdown Breach",
                target_metric="drawdown",
                threshold=0.25,
                severity=5,
            ),
        ]

    def search_failure_combinations(self, positions: list[dict[str, Any]], portfolio_state: dict[str, Any]) -> list[Scenario]:
        """Brute‑force search over single‑scenario applications that cause any objective breach.
        Returns a list of Scenario objects that trigger a failure.
        """
        engine = ScenarioEngine()
        failing: list[Scenario] = []
        for scen in engine.scenarios:
            result = engine.run_scenario(scen, positions, portfolio_state.copy())
            # Very naive check: if PnL exceeds any threshold (absolute) -> failure
            pnl = result.portfolio_impact.get("pnl", 0.0)
            for obj in self.objectives:
                if obj.target_metric == "pnl" and abs(pnl) > obj.threshold:
                    failing.append(scen)
                    logger.debug("Scenario %s triggers objective %s", scen.name, obj.name)
                    break
        return failing

    def identify_precursor_conditions(self, failure_scenarios: list[Scenario]) -> list[str]:
        """Extract common parameter keys that appear across failure scenarios.
        Returns a list of parameter names that are present in >50% of the failures.
        """
        if not failure_scenarios:
            return []
        freq: dict[str, int] = {}
        total = len(failure_scenarios)
        for scen in failure_scenarios:
            for key in scen.parameters.keys():
                freq[key] = freq.get(key, 0) + 1
        common = [k for k, v in freq.items() if v / total > 0.5]
        logger.debug("Identified precursor conditions: %s", common)
        return common

    def feed_into_risk_budgets(self, failures: list[Scenario], budget_config: dict[str, Any]) -> dict[str, Any]:
        """Adjust budget configuration based on observed failures.
        For each failure scenario, we bump the corresponding risk budget limit
        upward by 10% as a conservative safety margin.
        """
        adjusted = dict(budget_config)
        for scen in failures:
            btype = scen.parameters.get("budget_type")
            if btype and btype in adjusted:
                adjusted[btype] = adjusted[btype] * 1.1
        logger.info("Adjusted risk budgets based on %d failures", len(failures))
        return adjusted
