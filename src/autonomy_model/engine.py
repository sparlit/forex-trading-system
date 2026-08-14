"""Autonomy Model skeleton.
Defines authority levels and matrix checks.
"""

from enum import Enum, auto


class AuthorityLevel(Enum):
    L0_OBSERVE = auto()
    L1_ANALYZE = auto()
    L2_RECOMMEND = auto()
    L3_SHADOW = auto()
    L4_LIMITED_EXECUTION = auto()
    L5_CONTROLLED_PRODUCTION = auto()
    L6_FULL_AUTHORIZED_PRODUCTION = auto()
    L7_DEFENSIVE = auto()
    L8_HALTED = auto()
    L9_RECOVERY = auto()

class AutonomyMatrix:
    """Simple matrix mapping levels to required capabilities.
    In a full system this would be data‑driven and configurable.
    """
    def __init__(self):
        self.level_requirements: dict[AuthorityLevel, dict[str, bool]] = {
            AuthorityLevel.L0_OBSERVE: {"legal": True},
            AuthorityLevel.L1_ANALYZE: {"safety_invariant": True},
            AuthorityLevel.L2_RECOMMEND: {"safety_kernel": True},
            AuthorityLevel.L3_SHADOW: {"capital_governance": True},
            AuthorityLevel.L4_LIMITED_EXECUTION: {"hard_portfolio_risk": True},
            AuthorityLevel.L5_CONTROLLED_PRODUCTION: {"independent_risk_verification": True},
            AuthorityLevel.L6_FULL_AUTHORIZED_PRODUCTION: {"trade_admission": True},
            # further levels would add more constraints
        }

    def check(self, level: AuthorityLevel, capabilities: dict[str, bool]) -> bool:
        req = self.level_requirements.get(level, {})
        return all(capabilities.get(k, False) == v for k, v in req.items())
