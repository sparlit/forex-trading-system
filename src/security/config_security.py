"""
Configuration Security & Transactionality — EAQTS V2.3 N1619–N1629.

Critical configurations must pass:
  SCHEMA → POLICY → DEPENDENCY → HASH → SIGN → STAGE → VERIFY → ATOMIC ACTIVATE

Rollback artifacts preserved for every production config change.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger


class ConfigScope(str, Enum):
    RISK = "risk"
    SAFETY = "safety"
    CAPITAL = "capital"
    EXECUTION = "execution"
    BROKER = "broker"
    MODEL = "model"
    STRATEGY = "strategy"


class ConfigAction(str, Enum):
    VALIDATE = "validate"
    STAGE = "stage"
    ACTIVATE = "activate"
    ROLLBACK = "rollback"


@dataclass
class ConfigRecord:
    scope: ConfigScope
    version: str
    content: dict[str, Any]
    hash_sha256: str = ""
    signature: str = ""
    staged_at: float = 0.0
    activated_at: float = 0.0
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ChangeProposal:
    proposal_id: str
    scope: ConfigScope
    new_config: dict[str, Any]
    reason: str = ""
    risk_level: str = "low"  # low / medium / high / critical
    validation_evidence: list[str] = field(default_factory=list)
    rollback_config: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)


class ConfigSecurityEngine:
    """
    N1619–N1629: Secure, transactional configuration lifecycle.

    Every critical config change is a ChangeProposal that must:
    1. Validate schema
    2. Validate policy constraints
    3. Validate dependencies
    4. Hash (SHA-256)
    5. Sign (HMAC)
    6. Stage (write to staging area)
    7. Verify staged config
    8. Atomic activate (swap live config)
    9. Preserve rollback artifact
    """

    def __init__(
        self,
        signing_key: str | None = None,
        config_dir: str | Path = "config/live",
        staging_dir: str | Path = "config/staging",
        rollback_dir: str | Path = "config/rollback",
    ) -> None:
        self.signing_key = signing_key or os.environ.get("EAQTS_CONFIG_KEY", "dev-key-change-me")
        self.config_dir = Path(config_dir)
        self.staging_dir = Path(staging_dir)
        self.rollback_dir = Path(rollback_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.rollback_dir.mkdir(parents=True, exist_ok=True)

        # Schema validators per scope
        self._schema_validators: dict[ConfigScope, Callable[[dict], bool]] = {}
        # Policy validators per scope
        self._policy_validators: dict[ConfigScope, Callable[[dict], tuple[bool, str]]] = {}
        # Dependency validators per scope
        self._dep_validators: dict[ConfigScope, Callable[[dict], tuple[bool, str]]] = {}

    def register_validators(
        self,
        scope: ConfigScope,
        schema: Callable[[dict], bool] | None = None,
        policy: Callable[[dict], tuple[bool, str]] | None = None,
        deps: Callable[[dict], tuple[bool, str]] | None = None,
    ) -> None:
        if schema:
            self._schema_validators[scope] = schema
        if policy:
            self._policy_validators[scope] = policy
        if deps:
            self._dep_validators[scope] = deps

    def _hash(self, content: dict) -> str:
        """N1623 — SHA-256 hash of deterministic JSON."""
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _sign(self, content_hash: str) -> str:
        """N1624 — HMAC-SHA256 signature."""
        return hmac.new(
            self.signing_key.encode(),
            content_hash.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _verify_signature(self, content: dict, signature: str) -> bool:
        expected = self._sign(self._hash(content))
        return hmac.compare_digest(expected, signature)

    def propose(
        self,
        scope: ConfigScope,
        new_config: dict[str, Any],
        reason: str = "",
        risk_level: str = "low",
        rollback_config: dict[str, Any] | None = None,
    ) -> ChangeProposal:
        """N1619–N1622 — Create a signed change proposal."""
        proposal = ChangeProposal(
            proposal_id=f"{scope.value}_{int(time.time())}",
            scope=scope,
            new_config=new_config,
            reason=reason,
            risk_level=risk_level,
            rollback_config=rollback_config,
        )
        # Attach hash and signature to proposal
        proposal.new_config["_meta"] = {
            "hash": self._hash(new_config),
            "signed_at": time.time(),
        }
        proposal.new_config["_meta"]["signature"] = self._sign(proposal.new_config["_meta"]["hash"])
        logger.info(f"Config proposal {proposal.proposal_id} created (risk={risk_level})")
        return proposal

    def validate(self, proposal: ChangeProposal) -> tuple[bool, str]:
        """Run schema → policy → dependency validation."""
        content = {k: v for k, v in proposal.new_config.items() if not k.startswith("_")}

        # Schema
        if proposal.scope in self._schema_validators:
            if not self._schema_validators[proposal.scope](content):
                return False, "schema validation failed"

        # Policy
        if proposal.scope in self._policy_validators:
            ok, msg = self._policy_validators[proposal.scope](content)
            if not ok:
                return False, f"policy: {msg}"

        # Dependencies
        if proposal.scope in self._dep_validators:
            ok, msg = self._dep_validators[proposal.scope](content)
            if not ok:
                return False, f"dependency: {msg}"

        logger.info(f"Proposal {proposal.proposal_id} passed all validations")
        return True, ""

    def stage(self, proposal: ChangeProposal) -> bool:
        """N1625 — Stage configuration (write to staging area)."""
        ok, msg = self.validate(proposal)
        if not ok:
            logger.error(f"Staging failed validation: {msg}")
            return False

        staging_file = self.staging_dir / f"{proposal.proposal_id}.json"
        with open(staging_file, "w") as f:
            json.dump(proposal.new_config, f, indent=2)

        proposal.validation_evidence.append(f"staged at {staging_file}")
        logger.info(f"Proposal {proposal.proposal_id} staged")
        return True

    def verify_staged(self, proposal: ChangeProposal) -> bool:
        """N1626 — Verify staged configuration matches proposal."""
        staging_file = self.staging_dir / f"{proposal.proposal_id}.json"
        if not staging_file.exists():
            logger.error(f"Staged file missing: {staging_file}")
            return False

        with open(staging_file) as f:
            staged = json.load(f)

        # Verify hash matches
        staged_meta = staged.get("_meta", {})
        if not self._verify_signature({k: v for k, v in staged.items() if not k.startswith("_")}, staged_meta.get("signature", "")):
            logger.error(f"Signature verification failed for {proposal.proposal_id}")
            return False

        logger.info(f"Proposal {proposal.proposal_id} verified")
        return True

    def activate(self, proposal: ChangeProposal) -> bool:
        """N1627 — Atomically activate configuration."""
        if not self.verify_staged(proposal):
            return False

        live_file = self.config_dir / f"{proposal.scope.value}.json"
        staging_file = self.staging_dir / f"{proposal.proposal_id}.json"

        # Preserve current as rollback artifact
        if live_file.exists():
            rollback_file = self.rollback_dir / f"{proposal.scope.value}_rollback_{int(time.time())}.json"
            rollback_file.write_text(live_file.read_text())
            proposal.validation_evidence.append(f"rollback saved: {rollback_file}")

        # Atomic swap (POSIX rename is atomic)
        os.replace(staging_file, live_file)

        logger.info(f"Config {proposal.scope.value} ACTIVATED from {proposal.proposal_id}")
        return True

    def rollback(self, scope: ConfigScope, target_version: str | None = None) -> bool:
        """N1628 — Rollback to previous configuration."""
        if target_version:
            rollback_file = self.rollback_dir / f"{scope.value}_rollback_{target_version}.json"
        else:
            # Find most recent rollback
            rollbacks = sorted(self.rollback_dir.glob(f"{scope.value}_rollback_*.json"))
            if not rollbacks:
                logger.error(f"No rollback artifact for {scope.value}")
                return False
            rollback_file = rollbacks[-1]

        live_file = self.config_dir / f"{scope.value}.json"
        if live_file.exists():
            live_file.unlink()
        os.replace(rollback_file, live_file)

        logger.warning(f"Config {scope.value} ROLLED BACK from {rollback_file}")
        return True

    def test_tampering(self) -> bool:
        """N1629 — Verify tampered config is rejected."""
        # Create valid config
        valid = {"threshold": 0.5, "max": 10}
        valid_hash = self._hash(valid)
        valid_sig = self._sign(valid_hash)

        # Tamper
        tampered = {"threshold": 0.5, "max": 999}
        tampered_hash = self._hash(tampered)
        return not hmac.compare_digest(valid_sig, self._sign(tampered_hash))


# Singleton
config_security_engine = ConfigSecurityEngine()
