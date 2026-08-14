#!/usr/bin/env python3
"""
Forex Trading System - Health Monitor
Run as a cron job or systemd timer for continuous monitoring
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infra.config.settings import settings


class HealthMonitor:
    def __init__(self):
        self.base_url = f"http://{settings.api_host}:{settings.api_port}"
        self.alerts = []

    async def check_api(self, session: aiohttp.ClientSession) -> dict:
        """Check API health endpoint"""
        try:
            async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"status": "healthy", "data": data}
                return {"status": "unhealthy", "code": resp.status}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_database(self, session: aiohttp.ClientSession) -> dict:
        """Check database connectivity via API"""
        try:
            async with session.get(f"{self.base_url}/api/v1/health/db", timeout=5) as resp:
                return {"status": "healthy" if resp.status == 200 else "unhealthy"}
        except Exception:
            return {"status": "error"}

    async def check_redis(self, session: aiohttp.ClientSession) -> dict:
        """Check Redis via API"""
        try:
            async with session.get(f"{self.base_url}/api/v1/health/redis", timeout=5) as resp:
                return {"status": "healthy" if resp.status == 200 else "unhealthy"}
        except Exception:
            return {"status": "error"}

    async def check_mt5_ea(self, session: aiohttp.ClientSession) -> dict:
        """Check MT5 EA connection via EA Bridge"""
        try:
            async with session.get(f"{self.base_url}/api/v1/ea/status", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "status": "healthy" if data.get("connected_eas", 0) > 0 else "warning",
                        "data": data
                    }
                return {"status": "unhealthy"}
        except Exception:
            return {"status": "error"}

    async def check_risk_limits(self, session: aiohttp.ClientSession) -> dict:
        """Check risk limits via API"""
        try:
            async with session.get(f"{self.base_url}/api/v1/risk/metrics", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    alerts = []
                    if data.get("daily_loss_pct", 0) > 0.04:  # 80% of limit
                        alerts.append("Daily loss approaching limit")
                    if data.get("max_drawdown", 0) > 0.08:  # 80% of limit
                        alerts.append("Max drawdown approaching limit")
                    return {"status": "healthy" if not alerts else "warning", "alerts": alerts}
                return {"status": "error"}
        except Exception:
            return {"status": "error"}

    async def run_checks(self) -> dict:
        """Run all health checks"""
        results = {
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {}
        }

        async with aiohttp.ClientSession() as session:
            checks = [
                ("api", self.check_api),
                ("database", self.check_database),
                ("redis", self.check_redis),
                ("mt5_ea", self.check_mt5_ea),
                ("risk_limits", self.check_risk_limits),
            ]

            for name, check_fn in checks:
                try:
                    results["checks"][name] = await check_fn(session)
                except Exception as e:
                    results["checks"][name] = {"status": "error", "error": str(e)}

        # Overall status
        statuses = [c.get("status", "error") for c in results["checks"].values()]
        if all(s == "healthy" for s in statuses):
            results["overall"] = "healthy"
        elif any(s == "error" for s in statuses):
            results["overall"] = "critical"
        elif any(s == "warning" for s in statuses):
            results["overall"] = "degraded"
        else:
            results["overall"] = "unknown"

        return results

    async def send_alert(self, results: dict) -> None:
        """Send alert if system is unhealthy"""
        if results["overall"] in ("critical", "degraded"):
            # In production, integrate with Slack, Discord, PagerDuty, etc.
            alert_msg = f"""
ALERT: Forex Trading System Alert
Status: {results['overall'].upper()}
Time: {results['timestamp']}
Checks: {json.dumps(results['checks'], indent=2)}
"""
            print(f"ALERT: {alert_msg}")
            # TODO: Send to Slack/Discord/Email/PagerDuty


async def main():
    monitor = HealthMonitor()
    results = await monitor.run_checks()

    # Print results
    print(json.dumps(results, indent=2))

    # Send alerts if needed
    await monitor.send_alert(results)

    # Exit with error code if critical
    if results["overall"] == "critical":
        sys.exit(1)
    elif results["overall"] == "degraded":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
