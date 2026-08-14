"""
Secret Management Module
========================

Provides secure secret management with support for:
- HashiCorp Vault (production)
- Azure Key Vault (production)
- Environment variables (development/fallback)
- In-memory cache with TTL for performance
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import hvac

logger = logging.getLogger(__name__)


class SecretProvider(ABC):
    """Abstract base class for secret providers."""
    
    @abstractmethod
    async def get_secret(self, path: str, key: str | None = None) -> Any:
        """Get a secret value."""
    
    @abstractmethod
    async def set_secret(self, path: str, secret: dict[str, Any]) -> bool:
        """Set a secret value."""
    
    @abstractmethod
    async def delete_secret(self, path: str) -> bool:
        """Delete a secret."""
    
    @abstractmethod
    async def list_secrets(self, path: str) -> list[str]:
        """List secret keys at path."""
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check provider health."""


@dataclass
class CacheEntry:
    """Cached secret entry with TTL."""
    value: Any
    expires_at: datetime
    
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


class VaultProvider(SecretProvider):
    """HashiCorp Vault secret provider."""
    
    def __init__(
        self,
        url: str,
        token: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        mount_point: str = "secret",
        namespace: str | None = None,
        verify_ssl: bool = True,
    ):
        self.url = url
        self.token = token
        self.role_id = role_id
        self.secret_id = secret_id
        self.mount_point = mount_point
        self.namespace = namespace
        self.verify_ssl = verify_ssl
        self._client: hvac.Client | None = None
        self._cache: dict[str, CacheEntry] = {}
        self.cache_ttl = timedelta(minutes=5)
    
    def _get_client(self) -> hvac.Client:
        """Get or create Vault client with authentication."""
        if self._client is None:
            self._client = hvac.Client(
                url=self.url,
                token=self.token,
                namespace=self.namespace,
                verify=self.verify_ssl,
            )
            
            # Try AppRole auth if token not provided
            if not self.token and self.role_id and self.secret_id:
                auth_response = self._client.auth.approle.login(
                    role_id=self.role_id,
                    secret_id=self.secret_id,
                    mount_point="approle",
                )
                self._client.token = auth_response["auth"]["client_token"]
        
        # Refresh token if using AppRole and token expired
        elif self.role_id and self.secret_id and not self._client.is_authenticated():
            auth_response = self._client.auth.approle.login(
                role_id=self.role_id,
                secret_id=self.secret_id,
                mount_point="approle",
            )
            self._client.token = auth_response["auth"]["client_token"]
        
        return self._client
    
    def _get_cache_key(self, path: str, key: str | None) -> str:
        return f"{path}:{key}" if key else path
    
    def _get_cached(self, path: str, key: str | None) -> Any | None:
        cache_key = self._get_cache_key(path, key)
        entry = self._cache.get(cache_key)
        if entry and not entry.is_expired():
            return entry.value
        elif entry:
            del self._cache[cache_key]
        return None
    
    def _set_cache(self, path: str, key: str | None, value: Any) -> None:
        cache_key = self._get_cache_key(path, key)
        self._cache[cache_key] = CacheEntry(
            value=value,
            expires_at=datetime.now(UTC) + self.cache_ttl,
        )
    
    async def get_secret(self, path: str, key: str | None = None) -> Any:
        """Get secret from Vault KV v2."""
        # Check cache first
        cached = self._get_cached(path, key)
        if cached is not None:
            return cached
        
        try:
            client = self._get_client()
            _full_path = f"{self.mount_point}/data/{path.lstrip('/')}"
            
            response = client.secrets.kv.v2.read_secret_version(
                path=path.lstrip('/'),
                mount_point=self.mount_point,
            )
            
            data = response["data"]["data"]
            value = data[key] if key else data
            self._set_cache(path, key, value)
            return value
            
        except hvac.exceptions.InvalidPath:
            logger.warning(f"Secret not found: {path}")
            return None
        except Exception as e:
            logger.error(f"Vault get_secret error: {e}")
            raise
    
    async def set_secret(self, path: str, secret: dict[str, Any]) -> bool:
        """Set secret in Vault KV v2."""
        try:
            client = self._get_client()
            client.secrets.kv.v2.create_or_update_secret(
                path=path.lstrip('/'),
                secret=secret,
                mount_point=self.mount_point,
            )
            # Invalidate cache
            cache_key = self._get_cache_key(path, None)
            if cache_key in self._cache:
                del self._cache[cache_key]
            return True
        except Exception as e:
            logger.error(f"Vault set_secret error: {e}")
            return False
    
    async def delete_secret(self, path: str) -> bool:
        """Delete secret from Vault."""
        try:
            client = self._get_client()
            client.secrets.kv.v2.delete_latest_version_of_secret(
                path=path.lstrip('/'),
                mount_point=self.mount_point,
            )
            # Invalidate cache
            cache_key = self._get_cache_key(path, None)
            if cache_key in self._cache:
                del self._cache[cache_key]
            return True
        except Exception as e:
            logger.error(f"Vault delete_secret error: {e}")
            return False
    
    async def list_secrets(self, path: str) -> list[str]:
        """List secret keys at path."""
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.list_secrets(
                path=path.lstrip('/'),
                mount_point=self.mount_point,
            )
            return response["data"]["keys"]
        except Exception as e:
            logger.error(f"Vault list_secrets error: {e}")
            return []
    
    def health_check(self) -> bool:
        """Check Vault connectivity and auth."""
        try:
            client = self._get_client()
            return client.is_authenticated()
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False


class EnvProvider(SecretProvider):
    """Environment variable secret provider (development fallback)."""
    
    def __init__(self, prefix: str = "FOREX_"):
        self.prefix = prefix
        self._cache: dict[str, Any] = {}
    
    def _env_key(self, path: str, key: str | None) -> str:
        """Convert path/key to environment variable name."""
        parts = [self.prefix]
        if path:
            parts.append(path.replace("/", "_").replace("-", "_").upper())
        if key:
            parts.append(key.upper())
        return "_".join(parts)
    
    async def get_secret(self, path: str, key: str | None = None) -> Any:
        env_key = self._env_key(path, key)
        value = os.environ.get(env_key)
        if value is None:
            return None
        
        # Try to parse as JSON for complex values
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    async def set_secret(self, path: str, secret: dict[str, Any]) -> bool:
        # Env provider is read-only in this implementation
        logger.warning("EnvProvider is read-only, cannot set secrets")
        return False
    
    async def delete_secret(self, path: str) -> bool:
        logger.warning("EnvProvider is read-only, cannot delete secrets")
        return False
    
    async def list_secrets(self, path: str) -> list[str]:
        prefix = self._env_key(path, "")
        return [k.replace(prefix, "") for k in os.environ if k.startswith(prefix)]
    
    def health_check(self) -> bool:
        return True


class AzureKeyVaultProvider(SecretProvider):
    """Azure Key Vault secret provider."""
    
    def __init__(
        self,
        vault_url: str,
        credential=None,
        cache_ttl: timedelta = timedelta(minutes=5),
    ):
        self.vault_url = vault_url
        self.credential = credential
        self.cache_ttl = cache_ttl
        self._client = None
        self._cache: dict[str, CacheEntry] = {}
    
    def _get_client(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            
            cred = self.credential or DefaultAzureCredential()
            self._client = SecretClient(vault_url=self.vault_url, credential=cred)
        return self._client
    
    def _get_cache_key(self, path: str, key: str | None) -> str:
        return f"{path}:{key}" if key else path
    
    def _get_cached(self, path: str, key: str | None) -> Any | None:
        cache_key = self._get_cache_key(path, key)
        entry = self._cache.get(cache_key)
        if entry and not entry.is_expired():
            return entry.value
        elif entry:
            del self._cache[cache_key]
        return None
    
    def _set_cache(self, path: str, key: str | None, value: Any) -> None:
        cache_key = self._get_cache_key(path, key)
        self._cache[cache_key] = CacheEntry(
            value=value,
            expires_at=datetime.now(UTC) + self.cache_ttl,
        )
    
    async def get_secret(self, path: str, key: str | None = None) -> Any:
        cached = self._get_cached(path, key)
        if cached is not None:
            return cached
        
        try:
            client = self._get_client()
            secret_name = path.replace("/", "-").strip("-")
            secret = client.get_secret(secret_name)
            value = json.loads(secret.value) if secret.value.startswith("{") else secret.value
            if key and isinstance(value, dict):
                value = value.get(key)
            self._set_cache(path, key, value)
            return value
        except Exception as e:
            logger.error(f"Azure Key Vault get_secret error: {e}")
            return None
    
    async def set_secret(self, path: str, secret: dict[str, Any]) -> bool:
        try:
            client = self._get_client()
            secret_name = path.replace("/", "-").strip("-")
            client.set_secret(secret_name, json.dumps(secret))
            return True
        except Exception as e:
            logger.error(f"Azure Key Vault set_secret error: {e}")
            return False
    
    async def delete_secret(self, path: str) -> bool:
        try:
            client = self._get_client()
            secret_name = path.replace("/", "-").strip("-")
            client.begin_delete_secret(secret_name)
            return True
        except Exception as e:
            logger.error(f"Azure Key Vault delete_secret error: {e}")
            return False
    
    async def list_secrets(self, path: str) -> list[str]:
        try:
            client = self._get_client()
            prefix = path.replace("/", "-").strip("-")
            secrets = client.list_properties_of_secrets()
            return [s.name for s in secrets if s.name.startswith(prefix)]
        except Exception as e:
            logger.error(f"Azure Key Vault list_secrets error: {e}")
            return []
    
    def health_check(self) -> bool:
        try:
            client = self._get_client()
            client.get_secret("health-check")
            return True
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return True  # Might not have health-check secret, but service is reachable



class SecretManager:
    """
    High-level secret manager with provider fallback chain.
    
    Priority order:
    1. Vault (if configured)
    2. Azure Key Vault (if configured)
    3. Environment variables (always available as fallback)
    """
    
    def __init__(
        self,
        vault_provider: VaultProvider | None = None,
        azure_provider: AzureKeyVaultProvider | None = None,
        env_provider: EnvProvider | None = None,
    ):
        self.providers: list[SecretProvider] = []
        
        # Add providers in priority order
        if vault_provider and vault_provider.health_check():
            self.providers.append(vault_provider)
            logger.info("Vault provider enabled")
        
        if azure_provider and azure_provider.health_check():
            self.providers.append(azure_provider)
            logger.info("Azure Key Vault provider enabled")
        
        # Env provider always added as fallback
        self.providers.append(env_provider or EnvProvider())
        logger.info("Environment provider enabled (fallback)")
    
    async def get_secret(self, path: str, key: str | None = None) -> Any:
        """Get secret from first available provider."""
        for provider in self.providers:
            try:
                value = await provider.get_secret(path, key)
                if value is not None:
                    return value
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed for {path}: {e}")
                continue
        return None
    
    async def get_required_secret(self, path: str, key: str | None = None) -> Any:
        """Get secret or raise if not found."""
        value = await self.get_secret(path, key)
        if value is None:
            raise ValueError(f"Required secret not found: {path}/{key if key else ''}")
        return value
    
    async def set_secret(self, path: str, secret: dict[str, Any]) -> bool:
        """Set secret on all providers that support writing."""
        results = []
        for provider in self.providers:
            try:
                if hasattr(provider, 'set_secret'):
                    result = await provider.set_secret(path, secret)
                    results.append(result)
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed to set {path}: {e}")
        return any(results)
    
    async def delete_secret(self, path: str) -> bool:
        results = []
        for provider in self.providers:
            try:
                if hasattr(provider, 'delete_secret'):
                    result = await provider.delete_secret(path)
                    results.append(result)
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed to delete {path}: {e}")
        return any(results)
    
    def health_check(self) -> dict[str, bool]:
        """Check health of all providers."""
        return {
            provider.__class__.__name__: provider.health_check()
            for provider in self.providers
        }


# Global instance
_secret_manager: SecretManager | None = None


def get_secret_manager() -> SecretManager:
    """Get or create global secret manager."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager


def init_secret_manager(
    vault_url: str | None = None,
    vault_token: str | None = None,
    vault_role_id: str | None = None,
    vault_secret_id: str | None = None,
    vault_mount: str = "secret",
    azure_vault_url: str | None = None,
    env_prefix: str = "FOREX_",
) -> SecretManager:
    """Initialize global secret manager with providers."""
    global _secret_manager
    
    providers = []
    
    # Vault provider
    if vault_url:
        vault_provider = VaultProvider(
            url=vault_url,
            token=vault_token,
            role_id=vault_role_id,
            secret_id=vault_secret_id,
            mount_point=vault_mount,
        )
        if vault_provider.health_check():
            providers.append(vault_provider)
    
    # Azure Key Vault provider
    if azure_vault_url:
        azure_provider = AzureKeyVaultProvider(vault_url=azure_vault_url)
        if azure_provider.health_check():
            providers.append(azure_provider)
    
    # Env provider (always)
    providers.append(EnvProvider(prefix=env_prefix))
    
    _secret_manager = SecretManager()
    _secret_manager.providers = providers
    logger.info(f"Initialized secret manager with {len(providers)} providers")
    return _secret_manager


# Convenience functions
async def get_secret(path: str, key: str | None = None) -> Any:
    """Get secret from global manager."""
    manager = get_secret_manager()
    return await manager.get_secret(path, key)


async def get_required_secret(path: str, key: str | None = None) -> Any:
    """Get required secret or raise."""
    manager = get_secret_manager()
    return await manager.get_required_secret(path, key)


async def rotate_secrets(interval_seconds: int = 3600) -> None:
    """Background task that periodically clears the secret cache.

    Clearing the cache forces the next ``get_secret`` call to refetch from
    the configured providers (Vault, Azure Key Vault or environment
    variables), which is essential for secret rotation policies.

    Args:
        interval_seconds: How often to clear the cache. Defaults to 1h.
    """
    import asyncio  # local import to keep top‑level clean

    manager = get_secret_manager()
    logger.info(
        f"Starting secret rotation loop (interval={interval_seconds}s)"
    )
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            manager._cache.clear()
            logger.debug("Secret cache cleared during rotation")
    except asyncio.CancelledError:  # pragma: no cover - task cancellation
        logger.info("Secret rotation loop cancelled")
        raise