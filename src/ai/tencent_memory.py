"""
TencentDB-backed AI Memory for the Elite Autonomous Quantum Trading System.

Uses TencentDB (via REST API or local vector store fallback) for persistent
agent memory — fastest retrieval for the custom LLM.

Primary:   TencentDB for Redis (vector search + key-value)
Secondary: FAISS local vector index (offline fallback)
Tertiary:  In-memory Python dict (no-deps fallback)

The memory stores:
  - Trading decisions and their outcomes (for self-learning)
  - Market regime observations
  - Strategy performance snapshots per session
  - LLM prompt/response pairs (for RAG retrieval)
  - Chart pattern detections and their accuracy
  - Error logs and self-healing actions

Vector embeddings are 768-dim (compatible with the CustomFinancialLLM
decoder output). Cosine similarity is used for retrieval.

Usage:
    from src.ai.tencent_memory import TencentMemory
    mem = TencentMemory()
    mem.store("EURUSD_breakout_2024_01_15",
              text="EURUSD broke above 1.0900 with strong volume",
              metadata={"decision": "BUY", "outcome": "profit"},
              embedding=np.random.randn(768))
    results = mem.search("EURUSD breakout", top_k=5)
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional TencentDB SDK ──────────────────────────────────────────────
try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.redis.v20180412 import models as tcv_models
    from tencentcloud.redis.v20180412 import redis_client

    _HAS_TENCENT_SDK = True
except ImportError:
    _HAS_TENCENT_SDK = False

# ── Optional FAISS ───────────────────────────────────────────────────────
try:
    import faiss

    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False

# ── Optional requests for TencentDB REST ─────────────────────────────────
try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ── Constants ──────────────────────────────────────────────────────────────

EMBEDDING_DIM = 768
DEFAULT_SIMILARITY_THRESHOLD = 0.75
DEFAULT_TOP_K = 5
MEMORY_TTL_SEC = 30 * 24 * 3600  # 30 days
MEMORY_DIR = os.path.join(
    os.path.expanduser("~"), ".forex_trading_system", "ai_memory"
)


# ── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class MemoryEntry:
    """A single memory entry with vector embedding + metadata."""

    key: str
    text: str
    embedding: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    importance: float = 1.0  # 0-1, used for decay scoring

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "embedding": self.embedding.tolist()
            if isinstance(self.embedding, np.ndarray)
            else self.embedding,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryEntry:
        emb = d.get("embedding", [])
        return cls(
            key=d["key"],
            text=d["text"],
            embedding=np.array(emb, dtype=np.float32),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", time.time()),
            last_accessed=d.get("last_accessed", time.time()),
            access_count=d.get("access_count", 0),
            importance=d.get("importance", 1.0),
        )


@dataclass
class SearchResult:
    """A memory search result."""

    entry: MemoryEntry
    similarity: float
    rank: int


# ── TencentDB Connection ──────────────────────────────────────────────────


class TencentDBConnector:
    """
    Connects to TencentDB for Redis with vector search capabilities.

    TencentDB for Redis supports:
      - Key-value store (fast O(1) retrieval)
      - Redisearch module (vector similarity search)
      - TTL for automatic memory decay
      - Persistence with AOF/RDB

    If TencentDB is not available, falls back to FAISS or in-memory.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        port: int = 6379,
        password: str | None = None,
        secret_id: str | None = None,
        secret_key: str | None = None,
        region: str = "ap-singapore",
    ) -> None:
        self.endpoint = endpoint or os.getenv("TENCENTDB_ENDPOINT", "")
        self.port = port
        self.password = password or os.getenv("TENCENTDB_PASSWORD", "")
        self.secret_id = secret_id or os.getenv("TENCENT_SECRET_ID", "")
        self.secret_key = secret_key or os.getenv("TENCENT_SECRET_KEY", "")
        self.region = region
        self.connected = False
        self._client = None
        self._redis = None

    def connect(self) -> bool:
        """Attempt to connect to TencentDB."""
        # Method 1: Direct Redis connection
        if self.endpoint:
            try:
                import redis

                self._redis = redis.Redis(
                    host=self.endpoint,
                    port=self.port,
                    password=self.password,
                    decode_responses=False,
                    socket_timeout=3,
                    socket_connect_timeout=3,
                )
                self._redis.ping()
                self.connected = True
                logger.info("Connected to TencentDB for Redis at %s", self.endpoint)
                return True
            except ImportError:
                logger.warning("redis-py not installed; falling back")
            except Exception as e:
                logger.warning("TencentDB Redis connection failed: %s", e)

        # Method 2: Tencent Cloud API
        if self.secret_id and self.secret_key and _HAS_TENCENT_SDK:
            try:
                cred = credential.Credential(self.secret_id, self.secret_key)
                cp = ClientProfile()
                self._client = redis_client.RedisClient(cred, self.region, cp)
                # Test with a DescribeInstances call
                req = tcv_models.DescribeInstancesRequest()
                resp = self._client.DescribeInstances(req)
                if resp:
                    self.connected = True
                    logger.info(
                        "Connected to TencentDB via Cloud API (region=%s)",
                        self.region,
                    )
                    return True
            except Exception as e:
                logger.warning("TencentDB API connection failed: %s", e)

        # Method 3: REST API (if endpoint is HTTP)
        if self.endpoint and self.endpoint.startswith("http") and _HAS_REQUESTS:
            try:
                r = _requests.get(f"{self.endpoint}/health", timeout=3)
                if r.status_code == 200:
                    self.connected = True
                    logger.info("Connected to TencentDB REST at %s", self.endpoint)
                    return True
            except Exception as e:
                logger.warning("TencentDB REST connection failed: %s", e)

        logger.info("TencentDB not available; using local fallback")
        self.connected = False
        return False

    def set(self, key: str, value: bytes, ttl: int = MEMORY_TTL_SEC) -> bool:
        """Store a key-value pair with TTL."""
        if self._redis:
            try:
                self._redis.setex(key, ttl, value)
                return True
            except Exception as e:
                logger.warning("Redis set failed: %s", e)
        return False

    def get(self, key: str) -> bytes | None:
        """Retrieve a value by key."""
        if self._redis:
            try:
                return self._redis.get(key)
            except Exception as e:
                logger.warning("Redis get failed: %s", e)
        return None

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if self._redis:
            try:
                self._redis.delete(key)
                return True
            except Exception as e:
                logger.warning("Redis delete failed: %s", e)
            return False

    def keys(self, pattern: str = "*") -> list[str]:
        """List keys matching pattern."""
        if self._redis:
            try:
                return [k.decode() for k in self._redis.keys(pattern)]
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')
        return []

    def close(self) -> None:
        """Close the connection."""
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')
        self.connected = False


# ── FAISS Vector Index (local fallback) ────────────────────────────────────


class FAISSIndex:
    """Local FAISS vector index for similarity search (offline fallback)."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.index_path = os.path.join(MEMORY_DIR, "faiss_index.bin")
        self.meta_path = os.path.join(MEMORY_DIR, "faiss_meta.pkl")

        if _HAS_FAISS:
            # Use Inner Product (cosine similarity with normalized vectors)
            self.index = faiss.IndexFlatIP(dim)
            self._normalize = True
        else:
            self.index = None
            self._normalize = False

        self._keys: list[str] = []
        self._embeddings: list[np.ndarray] = []
        self._load()

    def _normalize_vec(self, vec: np.ndarray) -> np.ndarray:
        """L2-normalize a vector for cosine similarity."""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    def add(self, key: str, embedding: np.ndarray) -> None:
        """Add or update a vector in the index."""
        emb = embedding.astype(np.float32)
        if self._normalize:
            emb = self._normalize_vec(emb)

        # Remove old entry if exists
        if key in self._keys:
            idx = self._keys.index(key)
            self._keys.pop(idx)
            self._embeddings.pop(idx)

        self._keys.append(key)
        self._embeddings.append(emb)

        if self.index is not None:
            # Rebuild index (simple approach for small N)
            if len(self._embeddings) > 0:
                mat = np.vstack(self._embeddings)
                self.index.reset()
                self.index.add(mat)

    def search(
        self, query: np.ndarray, top_k: int = DEFAULT_TOP_K
    ) -> list[tuple[str, float]]:
        """Search for similar vectors. Returns [(key, similarity), ...]."""
        if not self._embeddings:
            return []

        q = query.astype(np.float32)
        if self._normalize:
            q = self._normalize_vec(q)

        if self.index is not None:
            k = min(top_k, self.index.ntotal)
            if k == 0:
                return []
            scores, indices = self.index.search(q.reshape(1, -1), k)
            results: list[tuple[str, float]] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self._keys):
                    results.append((self._keys[idx], float(score)))
            return results

        # Pure numpy fallback
        mat = np.vstack(self._embeddings)
        sims = mat @ q  # dot product (normalized = cosine)
        top_idx = np.argsort(sims)[-top_k:][::-1]
        return [(self._keys[i], float(sims[i])) for i in top_idx if i < len(self._keys)]

    def remove(self, key: str) -> None:
        """Remove a key from the index."""
        if key in self._keys:
            idx = self._keys.index(key)
            self._keys.pop(idx)
            self._embeddings.pop(idx)
            if self.index is not None and self._embeddings:
                self.index.reset()
                self.index.add(np.vstack(self._embeddings))

    def size(self) -> int:
        """Number of vectors in the index."""
        return len(self._keys)

    def save(self) -> None:
        """Persist index and metadata to disk."""
        try:
            if _HAS_FAISS and self.index is not None and self.index.ntotal > 0:
                faiss.write_index(self.index, self.index_path)
            with open(self.meta_path, "wb") as f:
                pickle.dump({"keys": self._keys, "embeddings": self._embeddings}, f)
        except Exception as e:
            logger.warning("FAISS save failed: %s", e)

    def _load(self) -> None:
        """Load index and metadata from disk."""
        try:
            if (
                _HAS_FAISS
                and os.path.exists(self.index_path)
                and os.path.exists(self.meta_path)
            ):
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    data = pickle.load(f)
                    self._keys = data.get("keys", [])
                    self._embeddings = data.get("embeddings", [])
                logger.info("Loaded FAISS index: %d vectors", len(self._keys))
        except Exception as e:
            logger.warning("FAISS load failed: %s", e)


# ── Main Memory Class ──────────────────────────────────────────────────────


class TencentMemory:
    """
    AI agent memory backed by TencentDB with FAISS fallback.

    Provides:
      - store(key, text, metadata, embedding) → store a memory
      - search(query_text, query_embedding, top_k) → retrieve similar memories
      - get(key) → exact lookup
      - delete(key) → forget a memory
      - decay() → remove low-importance memories
      - get_stats() → memory statistics
    """

    def __init__(
        self,
        tencent_endpoint: str | None = None,
        embedding_dim: int = EMBEDDING_DIM,
    ) -> None:
        self.embedding_dim = embedding_dim

        # TencentDB (primary)
        self.tencent = TencentDBConnector(endpoint=tencent_endpoint)
        self.tencent.connect()

        # FAISS (secondary)
        self.faiss = FAISSIndex(dim=embedding_dim)

        # In-memory dict (tertiary, always available)
        self._local: dict[str, MemoryEntry] = {}

        # Redis key prefix
        self._prefix = "ai_memory:"

    def _make_key(self, key: str) -> str:
        """Create the full storage key."""
        return f"{self._prefix}{key}"

    def store(
        self,
        key: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        embedding: np.ndarray | None = None,
        importance: float = 1.0,
    ) -> bool:
        """Store a memory entry in TencentDB + FAISS + local."""
        if embedding is None:
            # Generate a simple hash-based embedding (NO external dep)
            embedding = self._hash_embedding(text)

        entry = MemoryEntry(
            key=key,
            text=text,
            embedding=embedding,
            metadata=metadata or {},
            importance=importance,
        )
        data = pickle.dumps(entry)

        # Store in all 3 backends

        # 1. TencentDB
        if self.tencent.connected:
            try:
                self.tencent.set(self._make_key(key), data, ttl=MEMORY_TTL_SEC)
            except Exception as e:
                logger.warning("TencentDB store failed: %s", e)

        # 2. FAISS
        self.faiss.add(key, embedding)

        # 3. Local dict
        self._local[key] = entry

        # Save FAISS to disk periodically
        if len(self._local) % 100 == 0:
            self.faiss.save()

        return True

    def search(
        self,
        query_text: str,
        query_embedding: np.ndarray | None = None,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> list[SearchResult]:
        """Search memories by text or embedding similarity."""
        if query_embedding is None:
            query_embedding = self._hash_embedding(query_text)

        # Primary: FAISS (fastest for vector search)
        hits = self.faiss.search(query_embedding, top_k=top_k)

        results: list[SearchResult] = []
        for rank, (key, sim) in enumerate(hits):
            if sim >= threshold:
                entry = self._retrieve_entry(key)
                if entry:
                    entry.last_accessed = time.time()
                    entry.access_count += 1
                    results.append(SearchResult(entry=entry, similarity=sim, rank=rank))

        return results

    def _retrieve_entry(self, key: str) -> MemoryEntry | None:
        """Retrieve a full MemoryEntry from any available backend."""
        # 1. Local cache
        if key in self._local:
            return self._local[key]

        # 2. TencentDB
        if self.tencent.connected:
            try:
                data = self.tencent.get(self._make_key(key))
                if data:
                    entry = pickle.loads(data)
                    self._local[key] = entry  # cache locally
                    return entry
            except Exception:
                logging.getLogger(__name__).exception('Suppressed exception')

        # 3. Create minimal entry from FAISS metadata
        # (FAISS only stores vectors, not text — we need a metadata store)
        return MemoryEntry(
            key=key,
            text="(retrieved from FAISS, metadata in TencentDB)",
            embedding=np.zeros(self.embedding_dim, dtype=np.float32),
        )

    def get(self, key: str) -> MemoryEntry | None:
        """Exact key lookup."""
        return self._retrieve_entry(key)

    def delete(self, key: str) -> bool:
        """Delete a memory from all backends."""
        # TencentDB
        if self.tencent.connected:
            self.tencent.delete(self._make_key(key))

        # FAISS
        self.faiss.remove(key)

        # Local
        self._local.pop(key, None)

        return True

    def decay(self, min_importance: float = 0.1, max_age_sec: float = MEMORY_TTL_SEC) -> int:
        """
        Remove low-importance or stale memories.
        Returns count of removed entries.
        """
        now = time.time()
        removed = 0
        keys_to_remove: list[str] = []

        for key, entry in self._local.items():
            age = now - entry.created_at
            # Decay importance over time
            decayed_importance = entry.importance * max(0.1, 1.0 - age / max_age_sec)
            if decayed_importance < min_importance:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.delete(key)
            removed += 1

        return removed

    def get_stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        now = time.time()
        entries = list(self._local.values())
        total_entries = len(entries)
        total_embedded = self.faiss.size()

        if entries:
            avg_importance = sum(e.importance for e in entries) / total_entries
            avg_age = sum(now - e.created_at for e in entries) / total_entries
            avg_access = sum(e.access_count for e in entries) / total_entries
        else:
            avg_importance = 0.0
            avg_age = 0.0
            avg_access = 0.0

        return {
            "backend": "TencentDB" if self.tencent.connected else "FAISS/Local",
            "tencentdb_connected": self.tencent.connected,
            "faiss_available": _HAS_FAISS,
            "total_entries": total_entries,
            "total_embedded": total_embedded,
            "avg_importance": round(avg_importance, 4),
            "avg_age_hours": round(avg_age / 3600, 2),
            "avg_access_count": round(avg_access, 2),
            "embedding_dim": self.embedding_dim,
            "memory_dir": MEMORY_DIR,
        }

    def store_decision(
        self,
        symbol: str,
        decision: str,
        reasoning: str,
        outcome: str | None = None,
        embedding: np.ndarray | None = None,
    ) -> str:
        """Convenience method to store a trading decision."""
        key = f"decision:{symbol}:{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        text = f"{symbol} {decision}: {reasoning}"
        metadata = {
            "symbol": symbol,
            "decision": decision,
            "outcome": outcome,
            "reasoning": reasoning,
        }
        importance = 1.0 if outcome == "profit" else (0.8 if outcome == "loss" else 0.5)
        self.store(key, text, metadata, embedding, importance)
        return key

    def store_pattern(
        self,
        symbol: str,
        pattern_type: str,
        description: str,
        accuracy: float = 0.0,
        embedding: np.ndarray | None = None,
    ) -> str:
        """Convenience method to store a chart pattern detection."""
        key = f"pattern:{symbol}:{pattern_type}:{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        text = f"{symbol} {pattern_type}: {description}"
        metadata = {
            "symbol": symbol,
            "pattern_type": pattern_type,
            "description": description,
            "accuracy": accuracy,
        }
        self.store(key, text, metadata, embedding, importance=accuracy)
        return key

    def store_observation(
        self,
        category: str,
        text: str,
        embedding: np.ndarray | None = None,
        importance: float = 0.5,
    ) -> str:
        """Convenience method to store a market observation."""
        key = f"obs:{category}:{hashlib.md5(text.encode()).hexdigest()[:12]}"
        self.store(key, text, {"category": category}, embedding, importance)
        return key

    def close(self) -> None:
        """Save and close all backends."""
        self.faiss.save()
        self.tencent.close()

    def _hash_embedding(self, text: str) -> np.ndarray:
        """
        Generate a deterministic embedding from text (hash-based, no model needed).
        Not as good as a real embedding model but works offline.
        """
        # Use hash bytes scaled to [-1, 1] range for stable float32
        emb = np.zeros(self.embedding_dim, dtype=np.float32)
        for i in range(self.embedding_dim):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            # Take first 4 bytes, scale from [0, 255] to [-1, 1]
            val = int.from_bytes(h[:4], "little") / 0xFFFFFFFF  # [0, 1]
            emb[i] = val * 2.0 - 1.0  # [-1, 1]
        # L2 normalize
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb


# ── Singleton accessor ─────────────────────────────────────────────────────

_memory_instance: TencentMemory | None = None


def get_memory() -> TencentMemory:
    """Get or create the singleton memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = TencentMemory()
    return _memory_instance


__all__ = [
    "EMBEDDING_DIM",
    "FAISSIndex",
    "MemoryEntry",
    "SearchResult",
    "TencentDBConnector",
    "TencentMemory",
    "get_memory",
]
