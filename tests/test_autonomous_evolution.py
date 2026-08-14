"""Tests for the autonomous evolution engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.autonomous_evolution.engine import EvolutionEngine


def test_evolution_adaptation_trigger():
    eng = EvolutionEngine(window=3)
    # Record stable performance
    eng.record(1.0)
    eng.record(1.0)
    # Drop performance dramatically
    eng.record(0.5)
    assert eng.should_adapt() is True
    # Subsequent call should be false until another drop
    assert eng.should_adapt() is False
    # Record recovery
    eng.record(1.0)
    assert eng.should_adapt() is False
