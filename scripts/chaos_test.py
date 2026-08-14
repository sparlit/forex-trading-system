"""
Chaos Engineering Script
========================

Simulates a failure scenario by stopping a Docker service (Redis by
default) and verifies that the system recovers automatically.

This script is intentionally lightweight – it relies on the Docker CLI
being available on the host.  It is intended to be run in CI/CD or
manually as part of a disaster‑recovery drill.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

SERVICES = {
    "redis": "forex-trading-system-redis-1",
    "timescaledb": "forex-trading-system-timescaledb-1",
    "nats": "forex-trading-system-nats-1",
}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def stop_service(name: str) -> None:
    container = SERVICES.get(name, name)
    run(["docker", "stop", container])


def start_service(name: str) -> None:
    container = SERVICES.get(name, name)
    run(["docker", "start", container])


def wait_for_healthy(name: str, timeout: int = 30) -> bool:
    """Poll docker inspect until the service is healthy."""
    container = SERVICES.get(name, name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        proc = run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            check=False,
        )
        status = proc.stdout.strip()
        if status == "healthy":
            return True
        time.sleep(2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaos test for a Docker service")
    parser.add_argument(
        "service", nargs="?", default="redis", help="Service name (redis, timescaledb, nats)"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="How long to wait for recovery"
    )
    args = parser.parse_args()

    print(f"Stopping {args.service}...")
    stop_service(args.service)
    time.sleep(2)

    print("Starting service again...")
    start_service(args.service)

    print(f"Waiting for {args.service} to become healthy...")
    if wait_for_healthy(args.service, args.timeout):
        print(f"✅ {args.service} recovered successfully")
        return 0
    else:
        print(f"❌ {args.service} did NOT recover within {args.timeout}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
