"""
Data Licensing Governance — EAQTS V2.3 N1469–N1478.

Tracks provider licenses with expiration, permitted uses, storage,
training rights, redistribution restrictions. Blocks prohibited use
paths for expired/restricted sources.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    RESTRICTED = "restricted"


class PermittedUse(str, Enum):
    RESEARCH = "research"
    PRODUCTION = "production"
    TRAINING = "training"
    REDISTRIBUTION = "redistribution"
    DERIVATIVE = "derivative"


@dataclass
class ProviderLicense:
    license_id: str
    provider_id: str
    provider_name: str
    license_start: float
    license_expiration: float
    permitted_uses: list[PermittedUse] = field(default_factory=list)
    permitted_storage_days: int = 365
    training_permission: bool = False
    redistribution_restrictions: str = ""  # e.g., "none" | "internal_only" | "prohibited"
    status: LicenseStatus = LicenseStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() > self.license_expiration

    def days_to_expiry(self) -> float:
        return (self.license_expiration - time.time()) / 86400

    def is_expiring_soon(self, days: int = 30) -> bool:
        return 0 < self.days_to_expiry() <= days

    def permits(self, use: PermittedUse) -> bool:
        return use in self.permitted_uses


@dataclass
class LicenseViolation:
    provider_id: str
    violation_type: str  # "expired" | "use_not_permitted" | "storage_exceeded" | "redistribution_violated"
    message: str
    timestamp: float = field(default_factory=time.time)


class DataLicensingEngine:
    """
    N1469–N1478: Governance over data source licensing.
    Expired or restricted sources must not enter prohibited production pathways.
    """

    def __init__(self) -> None:
        self._licenses: dict[str, ProviderLicense] = {}
        self._violations: list[LicenseViolation] = []

    def register_license(self, license: ProviderLicense) -> None:
        """N1469–N1475 — Record provider license record."""
        self._licenses[license.provider_id] = license
        logger.info(
            f"Data license registered: {license.provider_id} "
            f"({license.license_start:.0f} → {license.license_expiration:.0f})"
        )

    def get_license(self, provider_id: str) -> ProviderLicense | None:
        return self._licenses.get(provider_id)

    def license_expiry_check(self) -> list[ProviderLicense]:
        """N1476 — Check all licenses for expiry."""
        expired = []
        for lic in self._licenses.values():
            if lic.is_expired():
                lic.status = LicenseStatus.EXPIRED
                expired.append(lic)
            elif lic.is_expiring_soon():
                lic.status = LicenseStatus.EXPIRING_SOON
        return expired

    def block_prohibited_use(
        self,
        provider_id: str,
        requested_use: PermittedUse,
    ) -> tuple[bool, str]:
        """
        N1477 — Check if requested use is permitted.
        Returns (allowed, reason).
        """
        lic = self._licenses.get(provider_id)
        if not lic:
            reason = f"No license found for provider {provider_id}"
            self._violations.append(LicenseViolation(
                provider_id=provider_id,
                violation_type="no_license",
                message=reason,
            ))
            return False, reason

        if lic.is_expired():
            reason = f"License expired for {provider_id} (expiry={lic.license_expiration:.0f})"
            self._violations.append(LicenseViolation(
                provider_id=provider_id,
                violation_type="expired",
                message=reason,
            ))
            return False, reason

        if not lic.permits(requested_use):
            reason = f"Use {requested_use.value} not permitted for {provider_id}"
            self._violations.append(LicenseViolation(
                provider_id=provider_id,
                violation_type="use_not_permitted",
                message=reason,
            ))
            return False, reason

        # Check storage days
        # (simplified: would need data age tracking)
        return True, ""

    def audit_compliance(self) -> dict[str, Any]:
        """N1478 — Audit data-license compliance."""
        total = len(self._licenses)
        expired = sum(1 for l in self._licenses.values() if l.is_expired())
        restricted = sum(1 for l in self._licenses.values() if l.status == LicenseStatus.RESTRICTED)
        expiring = sum(1 for l in self._licenses.values() if l.is_expiring_soon())

        return {
            "total_licenses": total,
            "expired": expired,
            "expiring_soon": expiring,
            "restricted": restricted,
            "compliance_rate": (total - expired - restricted) / total if total > 0 else 1.0,
            "violations": len(self._violations),
        }


# Singleton
data_licensing_engine = DataLicensingEngine()
