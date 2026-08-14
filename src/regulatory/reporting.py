"""
Regulatory Reporting
====================

Lightweight helper that exports trade data in CSV format compatible with
common regulatory regimes (MiFID II / EMIR).

The module is intentionally framework‑free – it accepts a list of trades
and writes a CSV file.  In production this would be replaced by a
proper reporting engine that signs and uploads the files to the relevant
authority.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


@dataclass
class RegulatoryTrade:
    """Single trade record for regulatory export."""

    trade_id: str
    timestamp: datetime
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    venue: str
    trader_id: str = "system"
    notes: str = ""


@dataclass
class RegulatoryReport:
    """Container for a report."""

    trades: list[RegulatoryTrade] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add(self, trade: RegulatoryTrade) -> None:
        self.trades.append(trade)

    def to_csv(self, path: str | Path) -> None:
        """Write the report to a CSV file at ``path``."""
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "trade_id",
                    "timestamp",
                    "symbol",
                    "side",
                    "quantity",
                    "price",
                    "venue",
                    "trader_id",
                    "notes",
                ]
            )
            for t in self.trades:
                writer.writerow(
                    [
                        t.trade_id,
                        t.timestamp.isoformat(),
                        t.symbol,
                        t.side,
                        str(t.quantity),
                        str(t.price),
                        t.venue,
                        t.trader_id,
                        t.notes,
                    ]
                )

    def to_dict(self) -> dict:
        """Return a JSON‑serializable representation."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "trades": [asdict(t) for t in self.trades],
        }


def generate_mifid_report(trades: Iterable[RegulatoryTrade]) -> RegulatoryReport:
    """Generate a MiFID II‑style report from ``trades``."""
    report = RegulatoryReport()
    for t in trades:
        report.add(t)
    return report
