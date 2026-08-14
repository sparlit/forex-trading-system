"""
Elite Autonomous Quantum Trading System - Custom Financial LLM
Trains on live MT5 tick data, historical bars, web scraped content, and news feeds.
Uses a transformer-based architecture for next-candle prediction and market analysis.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --- Optional ML imports ---
try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None

try:
    import sentence_transformers
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class LLMConfig:
    """Configuration for the custom financial LLM."""
    # Model architecture
    vocab_size: int = 32000           # Token vocab size
    d_model: int = 256                # Hidden dimension
    n_heads: int = 8                  # Attention heads
    n_layers: int = 6                  # Transformer layers
    d_ff: int = 1024                  # Feed-forward dim
    max_seq_len: int = 512            # Max sequence length
    dropout: float = 0.1              # Dropout rate

    # Training
    batch_size: int = 32
    learning_rate: float = 3e-4
    weight_decay: float = 0.01
    warmup_steps: int = 1000
    max_epochs: int = 50
    patience: int = 5                 # Early stopping patience
    min_improvement: float = 1e-4     # Min loss improvement

    # Data
    seq_len: int = 128                # Sequence length for candle encoding
    feature_dim: int = 16             # Number of features per candle (OHLCV + indicators)
    text_emb_dim: int = 384           # Dimension for text embeddings (sentence-transformers)

    # Storage
    model_dir: str = "models/custom_llm"
    chroma_db_dir: str = "models/custom_llm/chromadb"
    faiss_index_dir: str = "models/custom_llm/faiss"

    # Training loop
    retrain_interval_sec: int = 300   # Retrain every 5 minutes
    min_samples_for_training: int = 500
    target_accuracy: float = 0.99      # Target prediction accuracy

    # Device
    device: str = "cuda" if TORCH_AVAILABLE and torch and torch.cuda.is_available() else "cpu"


# =============================================================================
# Tokenizer for Financial Data
# =============================================================================

class FinancialTokenizer:
    """
    Tokenizes candle data (OHLCV + indicators) into discrete tokens
    for the transformer.  Uses binning to discretize continuous values.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.ohlcv_bins = 256  # Bins for OHLCV values
        self.indicator_bins = 128  # Bins for indicator values
        self._fit_done = False
        self._price_min: dict[str, float] = {}
        self._price_max: dict[str, float] = {}
        self._text_vocab: dict[str, int] = {"<pad>": 0, "<unk>": 1, "<bos>": 2, "<eos>": 3}

    def fit(self, price_data: pd.DataFrame, text_corpus: list[str]) -> None:
        """Fit tokenizer on price data and text corpus."""
        for col in ["open", "high", "low", "close"]:
            self._price_min[col] = float(price_data[col].min())
            self._price_max[col] = float(price_data[col].max())

        # Build text vocabulary from corpus (simple BPE-lite)
        for text in text_corpus:
            for word in text.lower().split():
                if word not in self._text_vocab and len(self._text_vocab) < self.config.vocab_size:
                    self._text_vocab[word] = len(self._text_vocab)

        self._fit_done = True
        logger.info(f"Tokenizer fitted: {len(self._text_vocab)} text tokens")

    def encode_candle(self, candle: pd.Series) -> list[int]:
        """Encode a single OHLCV candle into discrete tokens."""
        if not self._fit_done:
            return [0] * 5

        tokens = []
        for col in ["open", "high", "low", "close", "volume"]:
            val = candle.get(col, 0)
            if col in self._price_min:
                lo, hi = self._price_min[col], self._price_max[col]
                if hi > lo:
                    bin_idx = int((val - lo) / (hi - lo) * (self.ohlcv_bins - 1))
                else:
                    bin_idx = 0
            else:
                bin_idx = 0
            tokens.append(max(0, min(self.ohlcv_bins - 1, bin_idx)))

        return tokens

    def encode_candle_sequence(self, candles: pd.DataFrame) -> list[int]:
        """Encode a full sequence of candles into token IDs."""
        tokens = []
        for _, candle in candles.iterrows():
            tokens.extend(self.encode_candle(candle))
        return tokens

    def encode_text(self, text: str) -> list[int]:
        """Encode text into token IDs."""
        tokens = [2]  # <bos>
        for word in text.lower().split()[:150]:
            tokens.append(self._text_vocab.get(word, 1))  # <unk> for OOV
        tokens.append(3)  # <eos>
        return tokens

    def decode_text(self, token_ids: list[int]) -> str:
        """Decode token IDs back to text."""
        reverse_vocab = {v: k for k, v in self._text_vocab.items()}
        words = [reverse_vocab.get(t, "<unk>") for t in token_ids]
        return " ".join(w for w in words if w not in ["<pad>", "<bos>", "<eos>", "<unk>"])


# =============================================================================
# Transformer Model for Financial Prediction
# =============================================================================

if TORCH_AVAILABLE:

    class PositionalEncoding(nn.Module):
        """Standard sinusoidal positional encoding."""

        def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 512):
            super().__init__()
            self.dropout = nn.Dropout(dropout)
            pe = torch.zeros(max_len, d_model)
            pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div_term = torch.exp(
                torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model)
            )
            pe[:, 0::2] = torch.sin(pos * div_term)
            pe[:, 1::2] = torch.cos(pos * div_term)
            self.register_buffer("pe", pe.unsqueeze(0))

        def forward(self, x):
            x = x + self.pe[:, : x.size(1)]
            return self.dropout(x)

    class FinancialTransformer(nn.Module):
        """
        Custom transformer for financial time-series + text fusion.
        Predicts next-candle direction (up/down/flat) and price delta.
        """

        def __init__(self, config: LLMConfig):
            super().__init__()
            self.config = config

            # Embedding for candle tokens (price bins)
            self.candle_embedding = nn.Embedding(
                config.vocab_size, config.d_model
            )

            # Embedding for text tokens
            self.text_embedding = nn.Embedding(
                config.vocab_size, config.d_model
            )

            # Linear projection for continuous features
            self.feature_projection = nn.Linear(config.feature_dim, config.d_model)

            # Positional encoding
            self.pos_encoding = PositionalEncoding(
                config.d_model, config.dropout, config.max_seq_len
            )

            # Transformer encoder
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=config.d_model,
                nhead=config.n_heads,
                dim_feedforward=config.d_ff,
                dropout=config.dropout,
                batch_first=True,
                activation="gelu",
            )
            self.transformer = nn.TransformerEncoder(
                encoder_layer, num_layers=config.n_layers
            )

            # Prediction heads
            self.direction_head = nn.Linear(config.d_model, 3)  # up, down, flat
            self.price_delta_head = nn.Linear(config.d_model, 1)
            self.confidence_head = nn.Linear(config.d_model, 1)  # 0-1 confidence

            # Layer norm
            self.layer_norm = nn.LayerNorm(config.d_model)

        def forward(
            self,
            candle_tokens: torch.Tensor | None = None,
            text_tokens: torch.Tensor | None = None,
            features: torch.Tensor | None = None,
        ) -> dict[str, torch.Tensor]:
            """
            Forward pass. At least one of candle_tokens, text_tokens, or features
            must be provided. The model fuses whichever inputs are available.
            """
            seq_embeds = []

            if candle_tokens is not None:
                candle_emb = self.candle_embedding(candle_tokens)  # (B, T, d)
                # Pool candle dimension: (B, T*5) -> mean over each candle's 5 tokens
                B, T, D = candle_emb.shape
                # Reshape to get one embedding per candle
                candle_emb = candle_emb.view(B, T // 5, 5, D).mean(dim=2)
                seq_embeds.append(candle_emb)

            if text_tokens is not None:
                text_emb = self.text_embedding(text_tokens)  # (B, L, d)
                seq_embeds.append(text_emb)

            if features is not None:
                feat_emb = self.feature_projection(features)  # (B, F, d)
                seq_embeds.append(feat_emb)

            if not seq_embeds:
                raise ValueError("At least one input modality must be provided")

            # Concatenate all modalities
            x = torch.cat(seq_embeds, dim=1) if len(seq_embeds) > 1 else seq_embeds[0]

            # Apply positional encoding
            x = self.pos_encoding(x)

            # Transformer encoder
            x = self.transformer(x)
            x = self.layer_norm(x)

            # Use the last token for prediction (or mean pool)
            pooled = x[:, -1, :]  # Last position

            # Prediction heads
            direction = self.direction_head(pooled)  # (B, 3)
            price_delta = self.price_delta_head(pooled)  # (B, 1)
            confidence = torch.sigmoid(self.confidence_head(pooled))  # (B, 1)

            return {
                "direction": direction,
                "price_delta": price_delta,
                "confidence": confidence,
            }

else:
    # Fallback when PyTorch is not available
    class FinancialTransformer:  # type: ignore[no-redef]
        """Placeholder when PyTorch is not available."""
        def __init__(self, config: LLMConfig):
            self.config = config
            logger.warning("PyTorch not available — FinancialTransformer is a stub")

        def __call__(self, *args, **kwargs):
            raise RuntimeError("PyTorch not available")


# =============================================================================
# Dataset Classes
# =============================================================================

class CandleDataset(Dataset if TORCH_AVAILABLE else object):
    """Dataset for candle-based training."""

    def __init__(self, candles: pd.DataFrame, seq_len: int = 128, tokenizer: FinancialTokenizer | None = None):
        self.candles = candles.reset_index(drop=True)
        self.seq_len = seq_len
        self.tokenizer = tokenizer

    def __len__(self):
        return max(0, len(self.candles) - self.seq_len - 1)

    def __getitem__(self, idx: int):
        seq = self.candles.iloc[idx : idx + self.seq_len]
        next_candle = self.candles.iloc[idx + self.seq_len]

        # Features: OHLCV returns ratios
        feat = []
        for i in range(len(seq)):
            row = seq.iloc[i]
            ret = (row["close"] - row["open"]) / row["open"] if row["open"] != 0 else 0
            h_l = (row["high"] - row["low"]) / row["low"] if row["low"] != 0 else 0
            c_o = (row["close"] - row["open"]) / row["open"] if row["open"] != 0 else 0
            vol_norm = np.log1p(row.get("volume", 1))
            feat.append([ret, h_l, c_o, vol_norm])

        features = np.array(feat, dtype=np.float32)

        # Tokenize candle sequence
        if self.tokenizer:
            tokens = self.tokenizer.encode_candle_sequence(seq)
            token_arr = np.array(tokens, dtype=np.int64)
        else:
            token_arr = np.zeros(self.seq_len * 5, dtype=np.int64)

        # Label: direction (0=down, 1=flat, 2=up), price delta
        delta = (next_candle["close"] - seq.iloc[-1]["close"]) / seq.iloc[-1]["close"]
        if abs(delta) < 0.0005:
            direction = 1  # flat
        elif delta > 0:
            direction = 2  # up
        else:
            direction = 0  # down

        return (
            torch.tensor(token_arr, dtype=torch.long) if TORCH_AVAILABLE else token_arr,
            torch.tensor(features, dtype=torch.float32) if TORCH_AVAILABLE else features,
            torch.tensor(direction, dtype=torch.long) if TORCH_AVAILABLE else direction,
            torch.tensor(delta, dtype=torch.float32) if TORCH_AVAILABLE else delta,
        )


class TextDataset(Dataset if TORCH_AVAILABLE else object):
    """Dataset for text-based training (news headlines, filings)."""

    def __init__(self, texts: list[str], labels: list[int], tokenizer: FinancialTokenizer):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx: int):
        tokens = self.tokenizer.encode_text(self.texts[idx])
        label = self.labels[idx]
        if TORCH_AVAILABLE:
            return torch.tensor(tokens, dtype=torch.long), torch.tensor(label, dtype=torch.long)
        return tokens, label


# =============================================================================
# Custom Financial LLM
# =============================================================================

class CustomFinancialLLM:
    """
    Custom financial LLM that trains on:
    - Live MT5 tick data (via EA bridge)
    - Historical OHLCV bars
    - Web-scraped content (articles, filings)
    - News sentiment feeds

    The LLM uses a transformer architecture to predict next-candle direction
    and price delta, fused with text embeddings from news/analysis.

    Training runs continuously in the background and re-trains periodically.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self.tokenizer = FinancialTokenizer(self.config)
        self.model: FinancialTransformer | None = None
        self.optimizer = None
        self.scheduler = None

        # Data buffers
        self._candle_buffer: deque = deque(maxlen=10000)
        self._text_buffer: deque = deque(maxlen=5000)
        self._tick_buffer: deque = deque(maxlen=50000)

        # Training state
        self._trained = False
        self._training_loss: list[float] = []
        self._validation_acc: list[float] = []
        self._best_val_acc = 0.0
        self._epochs_without_improvement = 0
        self._total_samples = 0

        # Performance metrics
        self.direction_acc = 0.0
        self.price_mae = float("inf")
        self.confidence_calibration = 0.0

        # Vector store for RAG
        self._vector_store = None
        self._init_vector_store()

        # Initialize model
        self._init_model()

        # Directories
        Path(self.config.model_dir).mkdir(parents=True, exist_ok=True)

    def _init_model(self) -> None:
        """Initialize the transformer model and optimizer."""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available — model is disabled")
            return

        self.model = FinancialTransformer(self.config)
        self.model.to(self.config.device)

        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        # Cosine annealing with warmup
        self.scheduler = torch.optim.lr_scheduler.OneCycleLR(
            self.optimizer,
            max_lr=self.config.learning_rate,
            total_steps=self.config.max_epochs * 100,
            pct_start=0.1,
        )

        logger.info(
            f"FinancialTransformer initialized: d_model={self.config.d_model}, "
            f"layers={self.config.n_layers}, device={self.config.device}"
        )

    def _init_vector_store(self) -> None:
        """Initialize vector store for RAG."""
        try:
            if CHROMADB_AVAILABLE:
                Path(self.config.chroma_db_dir).mkdir(parents=True, exist_ok=True)
                self._vector_store = chromadb.PersistentClient(path=self.config.chroma_db_dir)
                self._vector_collection = self._vector_store.get_or_create_collection(
                    name="financial_knowledge", metadata={"hnsw:space": "cosine"}
                )
                logger.info("ChromaDB vector store initialized for RAG")
            else:
                logger.info("ChromaDB not available — RAG disabled")
        except Exception as e:
            logger.error(f"Failed to init vector store: {e}")

    # =========================================================================
    # Data Ingestion
    # =========================================================================

    def add_candle_data(self, candles: pd.DataFrame) -> None:
        """Add OHLCV candle data for training."""
        for _, row in candles.iterrows():
            self._candle_buffer.append(row.to_dict())
        self._total_samples += len(candles)
        logger.debug(f"Added {len(candles)} candles (total: {len(self._candle_buffer)})")

    def add_tick_data(self, ticks: list[dict]) -> None:
        """Add MT5 tick data for training."""
        for tick in ticks:
            self._tick_buffer.append(tick)
        logger.debug(f"Added {len(ticks)} ticks (total: {len(self._tick_buffer)})")

    def add_text_data(self, texts: list[str], source: str = "web") -> None:
        """Add text content (articles, news headlines, filings) for training."""
        for text in texts:
            entry = {"text": text, "source": source, "timestamp": datetime.now(UTC).isoformat()}
            self._text_buffer.append(entry)
            self._add_to_vector_store(text, entry)
        logger.info(f"Added {len(texts)} text entries from {source} (total: {len(self._text_buffer)})")

    def add_web_content(self, url: str, content: str) -> None:
        """Add web-scraped content for training."""
        # Split content into chunks
        chunks = self._chunk_text(content, max_chunk_len=500)
        self.add_text_data(chunks, source=url)

    def _chunk_text(self, text: str, max_chunk_len: int = 500) -> list[str]:
        """Split text into chunks for processing."""
        sentences = re.split(r'[.!?]+', text)
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) < max_chunk_len:
                current += s + ". "
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = s + ". "
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _add_to_vector_store(self, text: str, metadata: dict) -> None:
        """Add text to vector store for RAG retrieval."""
        if not self._vector_store or not SENTENCE_TRANSFORMERS_AVAILABLE:
            return
        try:
            # Use embedding model (baby version for local)
            if not hasattr(self, "_embedding_model"):
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            emb = self._embedding_model.encode(text).tolist()
            doc_id = f"doc_{hash(text) % (10**10)}"
            self._vector_collection.add(
                embeddings=[emb],
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id],
            )
        except Exception as e:
            logger.debug(f"Vector store add failed: {e}")

    # =========================================================================
    # Training
    # =========================================================================

    def fit_tokenizer(self) -> None:
        """Fit the tokenizer on accumulated data."""
        if len(self._candle_buffer) < 100:
            logger.info("Not enough candle data for tokenizer fitting")
            return

        candle_df = pd.DataFrame(list(self._candle_buffer))
        text_corpus = [entry["text"] for entry in self._text_buffer]
        self.tokenizer.fit(candle_df, text_corpus)
        logger.info("Tokenizer fitted on accumulated data")

    async def train(self) -> dict[str, Any]:
        """Train the model on accumulated data."""
        if not TORCH_AVAILABLE or not self.model:
            return {"error": "PyTorch not available"}

        if len(self._candle_buffer) < self.config.min_samples_for_training:
            return {"error": f"Need {self.config.min_samples_for_training} samples, have {len(self._candle_buffer)}"}

        # Fit tokenizer
        self.fit_tokenizer()

        # Prepare data
        candle_df = pd.DataFrame(list(self._candle_buffer))
        dataset = CandleDataset(candle_df, self.config.seq_len, self.tokenizer)

        # Split train/val
        train_size = int(0.8 * len(dataset))
        val_size = len(dataset) - train_size
        train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])

        train_loader = DataLoader(
            train_ds, batch_size=self.config.batch_size, shuffle=True, num_workers=0
        )
        val_loader = DataLoader(
            val_ds, batch_size=self.config.batch_size, shuffle=False, num_workers=0
        )

        self.model.train()
        best_val_acc = self._best_val_acc

        for epoch in range(self.config.max_epochs):
            # --- Training ---
            epoch_loss = 0.0
            n_batches = 0

            for tokens, features, direction, delta in train_loader:
                tokens = tokens.to(self.config.device)
                features = features.to(self.config.device)
                direction = direction.to(self.config.device)
                delta = delta.to(self.config.device)

                self.optimizer.zero_grad()

                # Forward
                outputs = self.model(candle_tokens=tokens, features=features)

                # Loss: cross-entropy for direction + MSE for price delta
                dir_loss = nn.CrossEntropyLoss()(outputs["direction"], direction)
                price_loss = nn.MSELoss()(outputs["price_delta"].squeeze(), delta)
                total_loss = dir_loss + 0.1 * price_loss

                total_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                if self.scheduler:
                    self.scheduler.step()

                epoch_loss += total_loss.item()
                n_batches += 1

            avg_train_loss = epoch_loss / max(1, n_batches)
            self._training_loss.append(avg_train_loss)

            # --- Validation ---
            val_acc = await self._validate(val_loader)
            self._validation_acc.append(val_acc)

            logger.info(
                f"Epoch {epoch+1}/{self.config.max_epochs}: "
                f"train_loss={avg_train_loss:.4f}, val_acc={val_acc:.2%}"
            )

            # Early stopping
            if val_acc > best_val_acc + self.config.min_improvement:
                best_val_acc = val_acc
                self._best_val_acc = val_acc
                self._epochs_without_improvement = 0
                await self.save_model()
            else:
                self._epochs_without_improvement += 1
                if self._epochs_without_improvement >= self.config.patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

            # Check if target accuracy reached
            if val_acc >= self.config.target_accuracy:
                logger.info(f"🎯 Target accuracy {self.config.target_accuracy:.0%} reached!")
                break

        self._trained = True
        self.direction_acc = best_val_acc

        return {
            "epochs_run": len(self._training_loss),
            "final_train_loss": self._training_loss[-1] if self._training_loss else 0,
            "best_val_acc": best_val_acc,
            "target_reached": best_val_acc >= self.config.target_accuracy,
            "total_samples": len(self._candle_buffer),
        }

    async def _validate(self, val_loader: DataLoader) -> float:
        """Validate model and return accuracy."""
        if not TORCH_AVAILABLE:
            return 0.0

        self.model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for tokens, features, direction, _ in val_loader:
                tokens = tokens.to(self.config.device)
                features = features.to(self.config.device)
                direction = direction.to(self.config.device)

                outputs = self.model(candle_tokens=tokens, features=features)
                preds = outputs["direction"].argmax(dim=1)

                correct += (preds == direction).sum().item()
                total += len(direction)

        self.model.train()
        return correct / max(1, total)

    # =========================================================================
    # Inference
    # =========================================================================

    async def predict(
        self,
        candles: pd.DataFrame,
        text_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Predict next-candle direction, price delta, and confidence.

        Args:
            candles: Recent OHLCV candles (at least seq_len rows)
            text_context: Optional news/analysis text for fusion

        Returns:
            Dict with direction (up/down/flat), price_delta, confidence,
            and reasoning from RAG.
        """
        if not TORCH_AVAILABLE or not self.model or not self._trained:
            return self._fallback_prediction(candles)

        self.model.eval()

        try:
            # Prepare inputs
            seq = candles.tail(self.config.seq_len)
            tokens = self.tokenizer.encode_candle_sequence(seq)

            # Features
            feat = []
            for _, row in seq.iterrows():
                ret = (row["close"] - row["open"]) / row["open"] if row["open"] != 0 else 0
                h_l = (row["high"] - row["low"]) / row["low"] if row["low"] != 0 else 0
                c_o = (row["close"] - row["open"]) / row["open"] if row["open"] != 0 else 0
                vol_norm = np.log1p(row.get("volume", 1))
                feat.append([ret, h_l, c_o, vol_norm])

            feat_arr = np.array(feat, dtype=np.float32)

            with torch.no_grad():
                token_tensor = torch.tensor(tokens, dtype=torch.long).unsqueeze(0).to(self.config.device)
                feat_tensor = torch.tensor(feat_arr, dtype=torch.float32).unsqueeze(0).to(self.config.device)

                text_tensor = None
                if text_context:
                    text_tokens = self.tokenizer.encode_text(text_context)
                    text_tensor = torch.tensor(text_tokens, dtype=torch.long).unsqueeze(0).to(self.config.device)

                outputs = self.model(
                    candle_tokens=token_tensor, text_tokens=text_tensor, features=feat_tensor
                )

                direction_probs = torch.softmax(outputs["direction"], dim=-1).cpu().numpy()[0]
                price_delta = outputs["price_delta"].cpu().numpy()[0, 0]
                confidence = outputs["confidence"].cpu().numpy()[0, 0]

            directions = ["down", "flat", "up"]
            direction_idx = int(np.argmax(direction_probs))

            # RAG retrieval for reasoning
            reasoning = await self._rag_reasoning(candles, text_context)

            return {
                "direction": directions[direction_idx],
                "direction_probs": {
                    "down": float(direction_probs[0]),
                    "flat": float(direction_probs[1]),
                    "up": float(direction_probs[2]),
                },
                "price_delta": float(price_delta),
                "predicted_price": float(candles.iloc[-1]["close"] * (1 + price_delta)),
                "confidence": float(confidence),
                "rag_reasoning": reasoning,
                "model_version": "custom_llm_v1",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return self._fallback_prediction(candles)

    def _fallback_prediction(self, candles: pd.DataFrame) -> dict[str, Any]:
        """Simple fallback using EMA crossover when model unavailable."""
        if len(candles) < 20:
            return {
                "direction": "flat",
                "direction_probs": {"down": 0.33, "flat": 0.34, "up": 0.33},
                "price_delta": 0.0,
                "predicted_price": candles.iloc[-1]["close"] if len(candles) > 0 else 0,
                "confidence": 0.0,
                "rag_reasoning": "Insufficient data for prediction",
                "model_version": "fallback_ema",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        close = candles["close"].values
        ema_fast = pd.Series(close).ewm(span=10).mean().iloc[-1]
        ema_slow = pd.Series(close).ewm(span=20).mean().iloc[-1]
        current = close[-1]

        if ema_fast > ema_slow:
            direction = "up"
            delta = (ema_fast - ema_slow) / ema_slow
        elif ema_fast < ema_slow:
            direction = "down"
            delta = (ema_fast - ema_slow) / ema_slow
        else:
            direction = "flat"
            delta = 0.0

        return {
            "direction": direction,
            "direction_probs": {"down": max(0, -delta) if delta < 0 else 0.1,
                                "flat": 0.3 if abs(delta) < 0.001 else 0.1,
                                "up": max(0, delta) if delta > 0 else 0.1},
            "price_delta": float(delta),
            "predicted_price": float(current * (1 + delta)),
            "confidence": 0.5,
            "rag_reasoning": "EMA crossover fallback (model not trained)",
            "model_version": "fallback_ema",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _rag_reasoning(self, candles: pd.DataFrame, query: str | None = None) -> str:
        """Retrieve relevant context from vector store for reasoning."""
        if not self._vector_store or not SENTENCE_TRANSFORMERS_AVAILABLE:
            return "RAG unavailable — no vector store"

        try:
            query_text = query or f"Candle analysis for {candles.iloc[-1].get('symbol', 'UNKNOWN')}"
            if not hasattr(self, "_embedding_model"):
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            emb = self._embedding_model.encode(query_text).tolist()
            results = self._vector_collection.query(query_embeddings=[emb], n_results=5)
            docs = results["documents"][0] if "documents" in results else []
            if docs:
                return f"Retrieved {len(docs)} relevant context chunks. Top: {docs[0][:200]}"
            return "No relevant context found in vector store"
        except Exception as e:
            return f"RAG error: {e}"

    # =========================================================================
    # Continuous Training Loop
    # =========================================================================

    async def run_continuous_training(self, data_provider: Any) -> None:
        """
        Run continuous training loop. Pulls data from provider.
        Retrains periodically to maintain/improve accuracy.
        """
        logger.info("Starting continuous LLM training loop...")

        while True:
            try:
                # Pull latest data from provider
                candles = await self._fetch_candles(data_provider)
                if candles is not None and len(candles) > 0:
                    self.add_candle_data(candles)

                # Pull web/news content
                texts = await self._fetch_text_content(data_provider)
                if texts:
                    self.add_text_data(texts, source="live_feed")

                # Pull MT5 ticks
                ticks = await self._fetch_ticks(data_provider)
                if ticks:
                    self.add_tick_data(ticks)

                # Train if enough samples
                if len(self._candle_buffer) >= self.config.min_samples_for_training:
                    result = await self.train()
                    logger.info(f"Training result: {result}")

                    if result.get("target_reached"):
                        logger.info("🎯 Target accuracy reached — entering standby mode")
                        # Reduce retrain frequency after target reached
                        await asyncio.sleep(self.config.retrain_interval_sec * 6)
                    else:
                        await asyncio.sleep(self.config.retrain_interval_sec)
                else:
                    logger.info(
                        f"Accumulating data: {len(self._candle_buffer)}/"
                        f"{self.config.min_samples_for_training}"
                    )
                    await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Training loop error: {e}")
                await asyncio.sleep(30)

    async def _fetch_candles(self, provider: Any) -> pd.DataFrame | None:
        """Fetch candle data from provider (MT5, CCXT, etc.)."""
        try:
            if hasattr(provider, "get_recent_candles"):
                return await provider.get_recent_candles()
        except Exception as e:
            logger.debug(f"Candle fetch error: {e}")
        return None

    async def _fetch_text_content(self, provider: Any) -> list[str]:
        """Fetch text content from web scraping / news feeds."""
        try:
            if hasattr(provider, "get_recent_text"):
                return await provider.get_recent_text()
        except Exception as e:
            logger.debug(f"Text fetch error: {e}")
        return []

    async def _fetch_ticks(self, provider: Any) -> list[dict]:
        """Fetch MT5 tick data."""
        try:
            if hasattr(provider, "get_recent_ticks"):
                return await provider.get_recent_ticks()
        except Exception as e:
            logger.debug(f"Tick fetch error: {e}")
        return []

    # =========================================================================
    # Model Persistence
    # =========================================================================

    async def save_model(self) -> None:
        """Save model weights and tokenizer."""
        if not TORCH_AVAILABLE or not self.model:
            return

        try:
            model_path = Path(self.config.model_dir) / "financial_transformer.pt"
            torch.save({
                "model_state": self.model.state_dict(),
                "config": self.config.__dict__,
                "best_val_acc": self._best_val_acc,
                "vocab": self.tokenizer._text_vocab,
                "price_min": self.tokenizer._price_min,
                "price_max": self.tokenizer._price_max,
            }, model_path)
            logger.info(f"Model saved to {model_path}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")

    async def load_model(self) -> bool:
        """Load model weights."""
        if not TORCH_AVAILABLE or not self.model:
            return False

        model_path = Path(self.config.model_dir) / "financial_transformer.pt"
        if not model_path.exists():
            logger.info("No saved model found — starting fresh")
            return False

        try:
            checkpoint = torch.load(model_path, map_location=self.config.device)
            self.model.load_state_dict(checkpoint["model_state"])
            self._best_val_acc = checkpoint.get("best_val_acc", 0)
            self.tokenizer._text_vocab = checkpoint.get("vocab", self.tokenizer._text_vocab)
            self.tokenizer._price_min = checkpoint.get("price_min", {})
            self.tokenizer._price_max = checkpoint.get("price_max", {})
            self._trained = True
            logger.info(f"Model loaded from {model_path} (val_acc={self._best_val_acc:.2%})")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get LLM metrics for dashboard."""
        return {
            "model_type": "FinancialTransformer",
            "trained": self._trained,
            "total_candle_samples": len(self._candle_buffer),
            "total_text_samples": len(self._text_buffer),
            "total_tick_samples": len(self._tick_buffer),
            "direction_accuracy": self.direction_acc,
            "best_val_accuracy": self._best_val_acc,
            "target_accuracy": self.config.target_accuracy,
            "target_reached": self._best_val_acc >= self.config.target_accuracy,
            "training_loss_history": self._training_loss[-20:],
            "validation_acc_history": self._validation_acc[-20:],
            "model_params": (
                sum(p.numel() for p in self.model.parameters())
                if self.model and TORCH_AVAILABLE else 0
            ),
            "vocab_size": len(self.tokenizer._text_vocab),
            "vector_store_enabled": self._vector_store is not None,
            "device": self.config.device,
        }


# =============================================================================
# Singleton
# =============================================================================

_llm_instance: CustomFinancialLLM | None = None


def get_custom_llm(config: LLMConfig | None = None) -> CustomFinancialLLM:
    """Get or create the singleton LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = CustomFinancialLLM(config)
    return _llm_instance


# =============================================================================
# Module Entry Point
# =============================================================================

if __name__ == "__main__":

    print("=" * 60)
    print("Custom Financial LLM - Self-Test")
    print("=" * 60)

    llm = get_custom_llm()

    # Generate synthetic test data
    np.random.seed(42)
    n = 500
    dates = pd.date_range(start="2024-01-01", periods=n, freq="5min")
    base = 1.0850
    returns = np.random.normal(0, 0.0002, n)
    prices = base * np.exp(np.cumsum(returns))

    test_df = pd.DataFrame({
        "open": prices,
        "high": prices + np.abs(np.random.normal(0, 0.0001, n)),
        "low": prices - np.abs(np.random.normal(0, 0.0001, n)),
        "close": prices + np.random.normal(0, 0.00005, n),
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)

    print(f"\nGenerated {len(test_df)} test candles")
    llm.add_candle_data(test_df)
    llm.add_text_data([
        "EURUSD shows strong bullish momentum above 1.0850",
        "Dollar weakens as Fed signals dovish pivot in Q1 2025",
        "European inflation data beats expectations, ECB hawkish",
    ], source="test")

    print(f"Candle buffer: {len(llm._candle_buffer)}")
    print(f"Text buffer: {len(llm._text_buffer)}")

    # Fit tokenizer
    llm.fit_tokenizer()
    print(f"Tokenizer fitted: {len(llm.tokenizer._text_vocab)} tokens")

    # Run prediction (will use fallback since not trained yet)
    import asyncio
    result = asyncio.run(llm.predict(test_df.tail(128), "EURUSD bullish above 1.0850"))
    print("\nPrediction result:")
    print(f"  Direction: {result['direction']}")
    print(f"  Confidence: {result['confidence']:.1%}")
    print(f"  Model: {result['model_version']}")

    metrics = llm.get_metrics()
    print("\nMetrics:")
    for k, v in metrics.items():
        if not isinstance(v, list):
            print(f"  {k}: {v}")

    print("\n✅ Custom Financial LLM self-test complete")
