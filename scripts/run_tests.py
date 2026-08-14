#!/usr/bin/env python3
"""
Forex Trading System - Test Runner
Run all tests with proper configuration.
"""

import sys
import subprocess
from pathlib import Path


def run_tests(
    test_path: str = "tests",
    coverage: bool = True,
    verbose: bool = True,
    parallel: bool = True,
    markers: str = None,
    exclude: str = None,
) -> int:
    """Run pytest with configured options."""

    cmd = ["pytest"]

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend([
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=70",
        ])

    if parallel:
        cmd.extend(["-n", "auto"])

    if markers:
        cmd.extend(["-m", markers])

    if exclude:
        cmd.extend(["--deselect", exclude])

    cmd.append(test_path)

    # Add common options
    cmd.extend([
        "--strict-markers",
        "--strict-config",
        "--tb=short",
        "--disable-warnings",
    ])

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode


def run_unit_tests():
    """Run unit tests only."""
    return run_tests(markers="unit", coverage=False)


def run_integration_tests():
    """Run integration tests only."""
    return run_tests(markers="integration")


def run_slow_tests():
    """Run slow tests."""
    return run_tests(markers="slow")


def run_all_tests():
    """Run all tests."""
    return run_tests()


def run_linting():
    """Run code quality checks."""
    print("Running ruff...")
    result = subprocess.run(["ruff", "check", "src", "tests"], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    print("Running ruff format check...")
    result = subprocess.run(["ruff", "format", "--check", "src", "tests"], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    print("Running mypy...")
    result = subprocess.run(["mypy", "src"], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def run_type_check():
    """Run mypy type checking."""
    return subprocess.run(["mypy", "src", "--strict"]).returncode


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Forex Trading System Test Runner")
    parser.add_argument(
        "command",
        choices=["all", "unit", "integration", "slow", "lint", "typecheck", "ci"],
        help="Test command to run",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Disable coverage reporting",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Disable parallel execution",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.command == "all":
        return run_all_tests()
    elif args.command == "unit":
        return run_unit_tests()
    elif args.command == "integration":
        return run_integration_tests()
    elif args.command == "slow":
        return run_slow_tests()
    elif args.command == "lint":
        return run_linting()
    elif args.command == "typecheck":
        return run_type_check()
    elif args.command == "ci":
        # CI pipeline: lint + typecheck + all tests
        print("=== Running CI Pipeline ===")
        lint_result = run_linting()
        if lint_result != 0:
            print("Linting failed!")
            return lint_result

        type_result = run_type_check()
        if type_result != 0:
            print("Type checking failed!")
            return type_result

        test_result = run_all_tests()
        return test_result

    return 0


if __name__ == "__main__":
    sys.exit(main())