"""
Help tab — Complete user manual, tutorials, FAQ, troubleshooting,
glossary, cheat sheets, and emergency actions for the
Elite Autonomous Quantum Trading System.

Self-contained, no external deps beyond Streamlit + Pandas.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

# ── Helpers ─────────────────────────────────────────────────────────────────

def _system_info() -> dict[str, Any]:
    """Return a snapshot of runtime / system information."""
    return {
        "Python": sys.version.split()[0],
        "Platform": platform.platform(),
        "CWD": os.getcwd(),
        "Time": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "Streamlit": st.__version__,
    }


def _color_tag(label: str, color: str) -> str:
    """Inline colored label."""
    palette = {
        "green": "#3fb950", "red": "#f85149", "yellow": "#d29922",
        "blue": "#58a6ff", "purple": "#a371f7", "cyan": "#39c5cf",
        "orange": "#fb8500", "pink": "#ff6b9d", "gray": "#8b949e",
    }
    c = palette.get(color, color)
    return f"<span style='color:{c};font-weight:600'>{label}</span>"


def _section(title: str, anchor: str = "") -> str:
    """Return HTML for a section header."""
    a = f" id='{anchor}'" if anchor else ""
    return f"<h2{a} style='border-bottom:2px solid #58a6ff;padding-bottom:6px;'>{title}</h2>"


def _callout(kind: str, body: str) -> str:
    """Render a colored callout box: info, warn, danger, success, tip."""
    colors = {
        "info":    ("#1f6feb", "#1c2128", "ℹ️"),
        "warn":    ("#d29922", "#1c2128", "⚠️"),
        "danger":  ("#f85149", "#1c2128", "🚨"),
        "success": ("#3fb950", "#1c2128", "✅"),
        "tip":     ("#a371f7", "#1c2128", "💡"),
    }
    border, bg, icon = colors.get(kind, colors["info"])
    return (
        f"<div style='border-left:4px solid {border};background:{bg};"
        f"padding:12px 16px;margin:8px 0;border-radius:6px;color:#e6edf3;'>"
        f"<strong>{icon}</strong> {body}</div>"
    )


# ── Main render ─────────────────────────────────────────────────────────────

def render_help_tab() -> None:
    st.title("📖 Help & Documentation Center")
    st.caption(
        "Complete manual, tutorials, FAQ, troubleshooting, glossary, "
        "and emergency procedures for the Elite Autonomous Quantum Trading System."
    )

    info = _system_info()
    cols = st.columns(5)
    cols[0].metric("Python", info["Python"])
    cols[1].metric("Streamlit", info["Streamlit"])
    cols[2].metric("Platform", "Windows" if "Windows" in info["Platform"] else "Linux")
    cols[3].metric("Mode", os.getenv("SIMULATION_MODE", "False"))
    cols[4].metric("UTC", info["Time"].split()[1])

    # ── In-tab navigation TOC ─────────────────────────────────────────
    st.markdown("### 🧭 Quick Navigation")
    toc = st.columns(6)
    sections = [
        ("🚀 Getting Started", "getting-started"),
        ("🗂️ All Tabs", "all-tabs"),
        ("📈 Chart Guide", "chart-guide"),
        ("🤖 Custom LLM", "custom-llm"),
        ("⚡ Parallel Engine", "parallel-engine"),
        ("🌙 Overnight Safety", "overnight-safety"),
        ("🔐 Authentication", "authentication"),
        ("🧠 TencentDB Memory", "memory"),
        ("🎭 Sentiment Analyzer", "sentiment-analyzer"),
        ("📊 Stock Predictor", "stock-predictor"),
        ("🤖 Agentic AI", "agentic-ai"),
        ("🚨 Emergency Actions", "emergency"),
        ("🔧 Troubleshooting", "troubleshooting"),
        ("❓ FAQ", "faq"),
        ("📚 Glossary", "glossary"),
        ("⌨️ Command Bar", "command-bar"),
        ("🎓 Tutorials", "tutorials"),
        ("📞 Support", "support"),
    ]
    for i, (label, anchor) in enumerate(sections):
        with toc[i % 6]:
            st.markdown(
                f"<a href='#{anchor}' style='color:#58a6ff;text-decoration:none;'>"
                f"{label}</a>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════════
    # 1. GETTING STARTED
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🚀 Getting Started", "getting-started"), unsafe_allow_html=True)

    st.markdown(
        "The Elite Autonomous Quantum Trading System is a fully autonomous, "
        "self‑learning, multi‑asset, multi‑broker, multi‑session trading "
        "platform. After initial configuration, **no further user input is "
        "required** — the system selects strategies, styles, sessions, "
        "and symbols automatically, executes trades across Forex, Crypto, "
        "Equities, and Commodities, and learns from outcomes."
    )

    with st.expander("1️⃣ First-time Setup (5 minutes)", expanded=True):
        st.markdown("**Step 1 — Install dependencies**")
        st.code(
            "poetry install\n"
            "# or\n"
            "pip install -r requirements.txt",
            language="bash",
        )
        st.markdown("**Step 2 — Configure environment**")
        st.code(
            "# Copy example env\n"
            "copy .env.example .env\n\n"
            "# Edit .env with your broker / API credentials\n"
            "MT5_LOGIN=60022138\n"
            "MT5_PASSWORD=[REDACTED]\n"
            "MT5_SERVER=4TLtd-Live\n"
            "BINANCE_API_KEY=[REDACTED]\n"
            "BINANCE_SECRET=[REDACTED]\n"
            "SIMULATION_MODE=False",
            language="bash",
        )
        st.markdown("**Step 3 — Initialize infrastructure (Scoop)**")
        st.code(
            "scoop install postgresql redis influxdb nats prometheus grafana\n"
            "scripts\\init_infrastructure.bat",
            language="bash",
        )
        st.markdown("**Step 4 — Launch dashboard**")
        st.code(
            "poetry run streamlit run src/dashboard/app.py",
            language="bash",
        )
        st.markdown("**Step 5 — Launch MT5 EA**")
        st.markdown(
            "Open MetaTrader 5 → File → Open Data Folder → "
            "`MQL5/Experts/ForexTradingSystemEA.mq5` → Compile → Attach to chart."
        )
        st.markdown(_callout("success", "Setup complete! The system now runs fully autonomously."), unsafe_allow_html=True)

    with st.expander("2️⃣ Where to find what you need"):
        st.markdown("""
| If you want to… | Go to tab |
|-----------------|-----------|
| See the live chart | 📈 LIVE CHART |
| View open positions | 📋 TRADES |
| Change broker settings | 🔗 BROKER CONFIG |
| Configure credentials / 2FA | 🔐 CREDENTIALS |
| Set risk limits | ⚖️ RISK MANAGER |
| Build a strategy | ⚔️ STRATEGY ENGINE |
| See why the system chose a trade | 🧠 BRAIN |
| Read documentation | 📖 HELP (this page) |
| Stop everything | 🚨 Emergency → Close All |
        """)

    # ═════════════════════════════════════════════════════════════════════
    # 2. ALL TABS
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🗂️ All Tabs Reference", "all-tabs"), unsafe_allow_html=True)
    st.caption("Every tab in the dashboard and what it does.")

    tabs_ref = [
        ("📊 OVERVIEW", "Live PnL, equity curve, daily summary, key metrics"),
        ("🕐 SESSIONS", "Forex session timeline (Sydney / Tokyo / London / NY), overlaps, status"),
        ("📈 LIVE CHART", "TradingView FOSS chart with symbols, timeframes, scales, indicators, drawings"),
        ("🧠 BRAIN", "Self-evolving brain state, ML model metrics, predictions, reasoning"),
        ("📋 TRADES", "Open positions, pending orders, history, slippage, execution quality"),
        ("🖥️ CONSOLE", "Live log stream from the trading engine"),
        ("📟 BLOOMBERG", "Bloomberg-style terminal with keyboard-driven panels"),
        ("💡 COMMAND BAR", "Slash-command interface (/buy, /sell, /risk, /chart, /status…)"),
        ("⚙️ SETTINGS", "System-level configuration (database, Redis, risk thresholds)"),
        ("🔐 CREDENTIALS", "API keys, MT5 login, 2FA/MFA setup, secret rotation"),
        ("📥 DATA INGESTION", "Live tick streams, OHLCV backfill, news feeds, web scrapers"),
        ("🔧 FEATURES", "Computed technical indicators (RSI, MACD, EMA, ATR, Bollinger…)"),
        ("⚔️ STRATEGY ENGINE", "Pick / configure / backtest strategies, see style selection"),
        ("⚖️ RISK MANAGER", "Position sizing, max drawdown, exposure limits, kill-switch"),
        ("🗂️ ORDER MANAGER", "Order Book, Trade Book, Spread/Multi-leg, Trigger Orders"),
        ("🪵 EXECUTION LOG", "Every fill, latency, slippage, partial fills, rejections"),
        ("⏱️ MONITORING", "Alerts, notifications, health checks, throughput metrics"),
        ("🔒 SECURITY", "Audit log, encryption status, IP whitelist, session timeout"),
        ("🌙 OVERNIGHT SAFETY", "Close-everything-at-X, weekend flatten, gap protection"),
        ("📂 PORTFOLIO", "Position Book, Holdings, Funds, allocation pie"),
        ("👁️ WATCHLIST", "Symbols list + Heatmap (sector / strength / volatility)"),
        ("📊 MARKET", "Exchange Messages, Market Movers, Scanners, Fundamentals, Corporate Actions"),
        ("🔗 BROKER CONFIG", "Per-broker connection, lot sizing, symbol mapping"),
        ("🤖 AI & LLM", "Custom financial LLM training status, hyperparameters, prompt console"),
        ("🌐 EXTERNAL DATA", "API providers (news / sentiment / macro), website crawler config"),
        ("📚 TRADE BOOK", "Historical trade ledger with parallel feature computation"),
        ("🎭 SENTIMENT ANALYZER", "Deep market sentiment: news, social, Fear & Greed, P/C ratio, VIX, central bank"),
        ("📊 STOCK PREDICTOR", "OHLC analysis, SMA/EMA comparison, indicators, sentiment scores, Monte Carlo forecast"),
        ("🤖 AGENTIC AI", "Autonomous AI agent: data analysis, chart pattern detection, self-healing, Buy/Sell/Hold decisions"),
        ("📖 HELP", "This page"),
    ]

    df_ref = pd.DataFrame(tabs_ref, columns=["Tab", "Purpose"])
    st.dataframe(df_ref, use_container_width=True, hide_index=True)

    # ═════════════════════════════════════════════════════════════════════
    # 3. CHART GUIDE
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("📈 Chart Guide", "chart-guide"), unsafe_allow_html=True)
    st.caption("TradingView Lightweight Charts (FOSS, Apache 2.0).")

    st.markdown("**Symbol & Timeframe Selection**")
    st.markdown("""
- Click the symbol dropdown to switch between `EURUSD`, `GBPUSD`, `USDJPY`,
  `XAUUSD`, `BTCUSD`, `ETHUSD`, `SPY`, `AAPL`, `NAS100`.
- Click a timeframe button (1m, 5m, 15m, 1h, 4h, 1D) to change bar period.
    """)

    st.markdown("**Hover Behaviour Fix (v2)**")
    st.markdown("""
The chart disorientation bug is fixed by:
1. A 16 ms debounce on crosshair events (prevents rapid re-render flicker).
2. A floating `hoverPriceLine` that follows the cursor smoothly.
3. A `mouseleave` listener that clears the hover line when the cursor exits.
4. `ResizeObserver` auto-resize when the sidebar is collapsed/expanded.
    """)
    st.markdown(_callout("info", "If the chart still feels jittery, increase the debounce constant in `src/dashboard/chart_tab.py` (search for `crosshairDebounce` and change `16` to `32` or `50`)."), unsafe_allow_html=True)

    st.markdown("**Indicators**")
    st.markdown("""
- EMA 20 (orange) — short-term trend
- EMA 50 (blue) — medium-term trend
- EMA 200 (red) — long-term trend (institutional level)
- Bollinger Bands 20,2 — volatility envelope
- VWAP — volume-weighted average price (intraday)
- Volume — green / red bars below the chart
    """)

    st.markdown("**Drawings**")
    st.markdown("""
- Trend line — click `📐 Trend`, then click two points on the chart.
- Horizontal — click `━ Horizontal`, click once.
- Vertical — click `│ Vertical`, click once.
- Measure — click `📏 Measure`, click two points to see price & bar delta.
- Clear all → `🗑️ Clear`
    """)

    st.markdown("**Scales**")
    st.markdown("- **Linear** — default, equal spacing per price unit.")
    st.markdown("- **Logarithmic** — equal spacing per *percent* change. Use for crypto, gold, indices.")

    st.markdown("**🖱️ Drag-to-Scale (NEW)**")
    st.markdown("""
- **Drag the right price axis** up/down to manually compress or expand the price scale.
- **Drag the time axis** (bottom) left/right to compress or expand candle spacing.
- **Double-click any axis** to auto-reset it to fit the visible data.
- **⚡ Auto button** — toggles auto-scale on/off. When ON, the price scale
  automatically adjusts to the visible candle range.
- **↕ Reset Scale button** — instantly resets both price + volume scales to fit.
- **Scroll wheel** — zooms in/out on the time axis.
- **Click + drag inside chart** — pans left/right across candles.
- A **blue hint tooltip** appears when you hover near the right price axis,
  reminding you that you can drag to rescale.
    """)
    st.markdown(_callout("tip",
        "To manually set a price range: turn OFF Auto (⚡), then drag the price "
        "axis to your desired range. The scale stays locked until you re-enable "
        "Auto or double-click the axis."
    ), unsafe_allow_html=True)

    st.markdown("**🕯️ Correct Candle Timings (NEW)**")
    st.markdown("""
Candle timestamps are now **aligned to timeframe boundaries** — no more
arbitrary or misaligned candle times.

| Timeframe | Candle Boundary | Example Times (UTC) |
|-----------|----------------|---------------------|
| 1m | Every 60s | 12:00, 12:01, 12:02… |
| 5m | Every 300s | 12:00, 12:05, 12:10… |
| 15m | Every 900s | 12:00, 12:15, 12:30… |
| 1h | Every 3600s | 12:00, 13:00, 14:00… |
| 4h | Every 14400s | 00:00, 04:00, 08:00… |
| 1D | Every 86400s (midnight UTC) | Aug 1, Aug 2, Aug 3… |

The **time axis labels** also adapt per timeframe:
- 1D / 4h → `MM/DD` (date format)
- 1h / 15m / 5m / 1m → `HH:MM` (time format)

**Price precision per symbol:**
- JPY pairs (USDJPY) → 3 decimal places (0.001 min move)
- Stocks (SPY, QQQ, AAPL) → 2 decimal places (0.01 min move)
- Forex / Crypto / Gold → 5 decimal places (0.00001 min move)
    """)

    # ═════════════════════════════════════════════════════════════════════
    # 4. CUSTOM LLM
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🤖 Custom Financial LLM", "custom-llm"), unsafe_allow_html=True)

    st.markdown("""
The `CustomFinancialLLM` (`src/ai/custom_llm.py`) is a 21.1M parameter
FinancialTransformer trained on:
- **MT5 live & historical tick data** (continuous stream from connected broker)
- **OHLCV bar history** (M1 → MN across multiple symbols)
- **Web-scraped content** (news headlines, central-bank statements, earnings calls)
- **News / filings** (RSS, SEC, broker announcements)
    """)
    st.code(
        "from src.ai.custom_llm import CustomFinancialLLM\n"
        "llm = CustomFinancialLLM()\n"
        "out = llm.forward(batch)         # forward pass\n"
        "llm.train_step(batch, target)    # one training step\n"
        "llm.run_continuous_training()    # long-running loop\n"
        "embeddings = llm.encode(texts)   # for RAG retrieval",
        language="python",
    )
    st.markdown(_callout("tip", "The LLM auto-stops training at 99% validation accuracy to prevent overfitting. Use the AI & LLM tab to monitor loss curves."), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 5. PARALLEL ENGINE
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("⚡ Parallel Processing Engine", "parallel-engine"), unsafe_allow_html=True)
    st.caption("GIL-bypass via multi-processing, vectorized C extensions.")

    st.markdown("""
`src/core/parallel.py` provides:
- `parallel_map(fn, items)` — process pool, true parallelism
- `thread_map(fn, items)` — thread pool, ideal for network/API
- `run_monte_carlo(simulate_fn, n=100_000)` — 100k scenarios across cores
- `grid_search_parallel(fn, grid)` — hyperparameter sweep
- `vectorized_apply(df, fn)` — Polars/NumPy (drops GIL in C/Rust)
- `jit_compile(fn)` — Numba JIT with `nogil=True`
    """)

    st.code(
        "from src.core.parallel import parallel_map, run_monte_carlo\n"
        "results = parallel_map(eval_strategy, strategies)        # CPU-bound\n"
        "prices = thread_map(fetch_price, symbols)                 # I/O-bound\n"
        "stats  = run_monte_carlo(simulate_trade, n=100_000)       # MC sim",
        language="python",
    )

    st.markdown("**Hybrid CPU tuning (Intel i5/i7/i9)**")
    st.markdown(_callout("warn",
        "On hybrid Intel CPUs (8P + 12E cores = 20 threads), using all 20 "
        "workers can be **slower** than using only 6 or 12 (P-cores only). "
        "The system auto-selects `perf_workers = 60%` of logical CPUs. "
        "Try `mode='perf'` vs `mode='max'` if you see slowdown."
    ), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 6. OVERNIGHT SAFETY
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🌙 Critical Overnight Safety Features", "overnight-safety"), unsafe_allow_html=True)

    st.markdown("""
The 🌙 OVERNIGHT SAFETY tab contains 7 critical protective layers:

1. **Auto-close all positions at configured hour** (default 22:00 UTC)
2. **Friday flatten** — close everything 30 min before market close
3. **Weekend gap protection** — reduced leverage, wider stops
4. **Max exposure cap** — hard $ limit, kill-switch on breach
5. **Slippage guard** — reject fills > N pips from quoted price
6. **News blackout** — no new entries 5 min before/after high-impact news
7. **Deadman switch** — if no heartbeat from dashboard for 5 min, flatten all
    """)
    st.markdown(_callout("danger", "These safeguards are the LAST LINE OF DEFENSE. Never disable them on a live account."), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 7. USER AUTHENTICATION
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🔐 User Authentication System", "authentication"), unsafe_allow_html=True)

    st.markdown("""
The dashboard requires **authentication at startup** and **re-authentication
for the Settings tab**. This prevents unauthorized access to trading controls.

**Security features:**
- **PBKDF2-SHA256** password hashing with 200k iterations + per-user salt
- **Optional 2FA/MFA** via TOTP (Google Authenticator / Authy)
- **Session timeout** — auto-logout after 30 minutes of inactivity
- **Settings re-auth** — accessing ⚙️ SETTINGS requires fresh authentication
  (expires after 5 minutes for safety)
- **Failed-attempt lockout** — 5 wrong attempts = 5-minute lockout
- **Role-based access** — admin / trader / viewer roles
- **User database** stored in `~/.forex_trading_system/users.json`
    """)

    with st.expander("📘 Default Login Credentials"):
        st.markdown("""
| Field | Default Value |
|-------|---------------|
| Username | `admin` |
| Password | `admin123` |
| 2FA | Not configured by default |

⚠️ **Change the default password immediately** after first login!
Go to 🔐 CREDENTIALS → change password form.
        """)

    with st.expander("📘 How to add a new user"):
        st.markdown("""
```python
from src.dashboard.auth import _ensure_users_db, _save_users_db, _hash_password, _gen_salt

users = _ensure_users_db()
salt = _gen_salt()
users['trader1'] = {
    'password_hash': _hash_password('secure_password_here', salt),
    'salt': salt,
    'role': 'trader',
    'totp_secret': None,  # set to pyotp.random_base32() for 2FA
    'enabled': True,
}
_save_users_db(users)
```
        """)

    with st.expander("📘 How to enable 2FA / TOTP"):
        st.markdown("""
1. Install pyotp: `pip install pyotp`
2. Go to 🔐 CREDENTIALS → "Setup 2FA"
3. Scan QR code with Google Authenticator / Authy
4. Enter 6-digit code to confirm
5. **Save backup codes** — needed if phone is lost
6. From next login, password + 6-digit TOTP code required
        """)
        st.markdown(_callout("warn", "If you lose your 2FA device and don't have backup codes, you'll need to manually remove totp_secret from the users.json file."), unsafe_allow_html=True)

    with st.expander("📘 Settings Tab Re-Authentication"):
        st.markdown("""
The ⚙️ SETTINGS tab requires fresh authentication (within last 5 minutes):
1. Select ⚙️ SETTINGS from the dropdown
2. If your session auth has expired, you'll see a re-auth form
3. Enter your password (+ 2FA code if configured)
4. Click "🔓 Unlock Settings"
5. Settings tab content appears

This prevents someone from jumping on your computer and changing critical
system configurations while you're away from your desk.
        """)

    # ═════════════════════════════════════════════════════════════════════
    # 8. TENCENTDB AI MEMORY
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🧠 TencentDB AI Memory System", "memory"), unsafe_allow_html=True)

    st.markdown("""
The trading system's LLM has **persistent memory** backed by TencentDB for
Redis (fastest key-value + vector search), with FAISS and in-memory fallbacks.

**Architecture (3-tier fallback):**

| Tier | Backend | Speed | Persistence | Vector Search |
|------|---------|-------|-------------|----------------|
| 1 (primary) | TencentDB for Redis | ~0.1ms | AOF/RDB | Redisearch |
| 2 (fallback) | FAISS local index | ~0.5ms | Disk (pickle) | IndexFlatIP |
| 3 (last resort) | In-memory dict | ~0.01ms | None | NumPy dot |

**What the memory stores:**
- **Trading decisions** and their outcomes (for self-learning)
- **Market regime** observations (bearish/bullish/ranging)
- **Chart pattern detections** and their accuracy scores
- **LLM prompt/response pairs** for RAG retrieval
- **Error logs** and self-healing actions

**Memory lifecycle:**
1. **Store** — every decision/observation writes to memory with importance score
2. **Retrieve** — before each trade, the LLM retrieves similar past situations
3. **Decay** — low-importance memories auto-expire after 30 days (TTL)
4. **Self-learn** — outcome feedback updates importance weights

**Embeddings:** 768-dim vectors (hash-based when offline, LLM-generated when trained).
    """)

    st.code(
        "from src.ai.tencent_memory import get_memory\n"
        "mem = get_memory()\n"
        "mem.store_decision('EURUSD', 'BUY', 'EMA crossover + RSI oversold', 'profit')\n"
        "results = mem.search('EURUSD breakout', top_k=5)\n"
        "for r in results:\n"
        "    print(f'{r.entry.key}: sim={r.similarity:.3f}')",
        language="python",
    )
    st.markdown(_callout("tip", "Configure TencentDB via TENCENTDB_ENDPOINT and TENCENTDB_PASSWORD environment variables. Without them, the system uses FAISS locally — no data lost."), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 9. DEEP MARKET SENTIMENT ANALYZER
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🎭 Deep Market Sentiment Analyzer", "sentiment-analyzer"), unsafe_allow_html=True)

    st.markdown("""
The 🎭 SENTIMENT ANALYZER tab provides a **360-degree view** of market sentiment:

**8 Sections:**

| Section | What It Shows |
|---------|---------------|
| Overall Sentiment Gauge | Composite score 0-100 (red→yellow→green gradient) |
| News Sentiment | Top 20 headlines with sentiment score (-1 to +1) |
| Social Media Sentiment | Twitter/Reddit sentiment by symbol |
| Fear & Greed Index | Current value + 7d/30d trend sparkline |
| Put/Call Ratio | Bullish if <0.7, bearish if >1.0 |
| VIX / Volatility Index | Regime indicator (low <15, normal 15-25, high >25) |
| Sentiment vs Price Divergence | Symbols where sentiment ≠ price action |
| Central Bank Sentiment | Fed/ECB/BoJ/BoE hawkish/dovish labels |

**How to use it:** Before entering a trade, check the sentiment gauge.
If sentiment is strongly bullish but price is falling → potential reversal.
If sentiment is bearish and price is falling → trend confirmation.
    """)

    # ═════════════════════════════════════════════════════════════════════
    # 10. STOCK MARKET PREDICTOR
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("📊 Stock Market Predictor", "stock-predictor"), unsafe_allow_html=True)

    st.markdown("""
The 📊 STOCK PREDICTOR tab combines **technical analysis + sentiment + Monte Carlo**
to produce a price forecast:

**7 Sections:**

| Section | What It Does |
|---------|-------------|
| Symbol Selection | Pick from EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD, SPY, QQQ, AAPL, TSLA, NVDA |
| Historical OHLC Data | Last 180 bars as candlestick chart with volume |
| Moving Averages Comparison | SMA 20/50/200 + EMA 12/26/50 overlaid, crossover signals |
| Technical Indicators | RSI, MACD, Bollinger Bands, ATR, Stochastic, ADX — each with Buy/Sell/Neutral |
| Market Sentiment Scores | Radar chart: news + social + technical + options sentiment |
| Price Forecast Curves | 3 models: Linear regression, EMA-based, Monte Carlo (1000 paths, 95% CI) |
| Signal Summary | Final Buy/Sell/Hold recommendation with confidence % |

**Forecast models:**
- **Linear Regression** — extrapolates the trend line forward
- **EMA Forecast** — projects EMA trajectory forward
- **Monte Carlo** — 1,000 simulated price paths, median + 95% confidence band

The final recommendation weighs all signals: MA crossovers (25%), indicators (30%),
sentiment (25%), and Monte Carlo forecast direction (20%).
    """)

    # ═════════════════════════════════════════════════════════════════════
    # 11. AGENTIC AI
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🤖 Agentic AI System", "agentic-ai"), unsafe_allow_html=True)

    st.markdown("""
The 🤖 AGENTIC AI tab shows the **autonomous AI agent** that manages the trading system.

**Architecture: Python + Rust**

| Component | Language | Purpose |
|-----------|----------|---------|
| `AgenticAgent` | Python | Orchestrates all analysis, decision engine, self-healing |
| `agentic_core.rs` | Rust (pyo3) | High-performance: correlation matrix, pattern detection, Monte Carlo |
| Dashboard tab | Python/Streamlit | Live status, decisions, patterns, self-healing log |

**What the agent does each cycle:**
1. **Data analysis** — runs all technical indicators in parallel (multiprocessing)
2. **Chart pattern analysis** — detects Head & Shoulders, Double Tops/Bottoms, Triangles,
   Flags, Wedges, Doji, Hammer, Engulfing patterns
3. **Strategy evaluation** — weighs signals from all 50+ registered strategies
4. **Decision engine** — combines all signals → Buy/Sell/Hold with confidence %
5. **Self-monitoring** — checks system health (CPU, memory, connections, errors)
6. **Self-healing** — if any component fails, automatically restarts it
7. **Memory** — stores every decision + outcome in TencentDB memory for self-learning

**Rust core (when compiled):**
- `compute_correlation_matrix()` — O(n²) across all symbols, SIMD-accelerated
- `detect_chart_patterns_fast()` — sub-millisecond pattern detection
- `monte_carlo_parallel()` — 100k simulations across all CPU cores

**Self-healing capabilities:**
- MT5 connection lost → auto-reconnect with backoff
- Data feed timeout → restart connector
- LLM training crashed → restore from last checkpoint
- Memory full → run decay() to clean low-importance entries
    """)
    st.markdown(_callout("info", "The Rust core is optional — if not compiled, the Python fallback provides the same functionality (slower). Run `cargo build --release` in src/ai/ to compile."), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 13. KEYBOARD SHORTCUTS
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("⌨️ Keyboard Shortcuts", "keyboard"), unsafe_allow_html=True)
    # Build a DataFrame of shortcuts
    import pandas as pd
    shortcut_data = []
    for code, (tab, desc) in SHORTCUT_MAP.items():
        shortcut_data.append({"Code": code, "Tab": tab, "Description": desc})
    df_shortcuts = pd.DataFrame(shortcut_data).sort_values("Code")
    st.dataframe(df_shortcuts, use_container_width=True, hide_index=True)
    st.markdown(_callout("info", "Type the sheet code anywhere on the dashboard (no need to focus a textbox) – the system will jump to the corresponding tab instantly.\n\nE.g. type **GP** to open the Live Chart, **RISK** for the Risk Manager, **PRED** for Stock Predictor."), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════
    # 14. EMERGENCY ACTIONS (already present below)
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🚨 Emergency Actions", "emergency"), unsafe_allow_html=True)
    st.markdown(_callout("danger",
        "Use only when something is wrong. These actions take effect IMMEDIATELY."
    ), unsafe_allow_html=True)

    with st.expander("🚨 EMERGENCY: Close ALL positions NOW"):
        st.markdown("""
**What it does:** Sends market-close orders for every open position across every broker.

**How to trigger:**
1. Go to ⚖️ RISK MANAGER → "Kill Switch" → confirm
2. OR type `/emergency closeall` in 💡 COMMAND BAR
3. OR call MT5 EA right-click menu → "Emergency Close All"

**Side effects:**
- Slippage on illiquid symbols possible
- Spreads widen during close
- Order rejections logged but NOT retried

**Recovery:** Review 📋 TRADES for any that didn't close, retry manually.
        """)

    with st.expander("🚨 EMERGENCY: Stop the system"):
        st.markdown("""
**What it does:** Stops ALL trading activity. Existing positions remain but no new entries.

**How to trigger:**
1. Dashboard sidebar → "Stop System" (red button)
2. OR type `/shutdown` in 💡 COMMAND BAR
3. OR kill the python process: `taskkill /F /IM python.exe`

**Side effects:** None on positions; the system simply stops opening new trades.

**Restart:** `poetry run streamlit run src/dashboard/app.py`
        """)

    with st.expander("🚨 EMERGENCY: Roll back to last good state"):
        st.markdown("""
**What it does:** Reverts model + config to last validated snapshot.

**How to trigger:**
1. 🧠 BRAIN → "Rollback to last checkpoint"
2. OR Settings → "Restore from backup" → select snapshot

**When to use:** After a sudden loss, the system behaving erratically, or
a model started producing nonsense.
        """)

    with st.expander("🚨 EMERGENCY: Disable a single strategy"):
        st.markdown("""
**What it does:** Blacklists one specific strategy without stopping the rest.

**How to trigger:**
1. ⚔️ STRATEGY ENGINE → find strategy → click "Disable"
2. OR /disable `<strategy_name>` in 💡 COMMAND BAR
        """)

    with st.expander("🚨 EMERGENCY: Lock credentials (suspected compromise)"):
        st.markdown("""
**What it does:** Immediately invalidates all API keys, requires re-auth.

**How to trigger:**
1. 🔐 CREDENTIALS → "Lock All Credentials"
2. OR Settings → "Revoke all sessions"

**After:** Generate new keys with your broker, paste them back, restart.
        """)

    with st.expander("🚨 EMERGENCY: Network isolation"):
        st.markdown("""
If you suspect the system is being remotely controlled:
1. Disconnect WiFi / unplug Ethernet
2. Kill all `python.exe` and `terminal64.exe` processes
3. Rotate ALL credentials
4. Inspect `logs/` for unknown IPs
        """)

    # ═════════════════════════════════════════════════════════════════════
    # 8. TROUBLESHOOTING
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🔧 Troubleshooting", "troubleshooting"), unsafe_allow_html=True)

    trouble = [
        ("MT5 won't connect",
         ("1. Verify MT5 is logged in (bottom-right shows green).\n"
         "2. Check `MT5_SERVER` in `.env` (default `4TLtd-Live`).\n"
         "3. Enable Algo Trading: Tools → Options → Expert Advisors → Allow.\n"
         "4. Restart the EA: drag off the chart, drag back on.")),
        ("Chart not loading",
         ("1. Check browser console (F12) for CDN errors.\n"
         "2. Verify `https://unpkg.com/lightweight-charts` is reachable.\n"
         "3. Try a different browser (Chrome recommended).\n"
         "4. Clear Streamlit cache: ⋯ menu → Clear cache.")),
        ("Dashboard slow / laggy",
         ("1. Lower refresh interval in ⚙️ SETTINGS → Display → Refresh rate.\n"
         "2. Disable Watchlist heatmap if CPU-bound.\n"
         "3. Reduce the number of visible symbols.\n"
         "4. Check Task Manager — if Python > 30% CPU steady, restart.")),
        ("Order rejected by broker",
         ("1. Check ⏱️ MONITORING → Logs for rejection reason.\n"
         "2. Common causes: insufficient margin, market closed, symbol not enabled.\n"
         "3. Verify 🔗 BROKER CONFIG → Symbol whitelist.")),
        ("No live ticks arriving",
         ("1. Verify MT5 connection.\n"
         "2. Check 📥 DATA INGESTION → tick stream is green.\n"
         "3. Restart: `scripts\\restart_data_feed.bat`.")),
        ("LLM not training",
         ("1. 🤖 AI & LLM tab → check training status.\n"
         "2. Verify GPU/CPU available: `python -c 'import torch;print(torch.cuda.is_available())'`.\n"
         "3. Disk space > 5 GB on training drive.")),
        ("2FA code not accepted",
         ("1. Verify device clock is NTP-synced.\n"
         "2. Regenerate TOTP secret in 🔐 CREDENTIALS.\n"
         "3. Try backup codes (saved during 2FA setup).")),
        ("Overnight positions held unexpectedly",
         ("1. Check 🌙 OVERNIGHT SAFETY → auto-close hour.\n"
         "2. Verify time zone (all times are UTC).\n"
         "3. Check Friday-flatten setting.")),
        ("Dashboard dropdown shows nothing",
         ("1. Hard refresh browser (Ctrl+F5).\n"
         "2. Clear Streamlit cache.\n"
         "3. Restart dashboard.")),
        ("Database connection lost",
         ("1. Verify PostgreSQL is running: `pg_isready`.\n"
         "2. Start: `scoop start postgresql`.\n"
         "3. Connection details in ⚙️ SETTINGS → Database.")),
        ("Redis not responding",
         ("1. `redis-cli ping` should return `PONG`.\n"
         "2. Start: `scoop start redis`.\n"
         "3. Default port 6379.")),
    ]

    for title, fix in trouble:
        with st.expander(f"❌ {title}"):
            st.markdown(fix)

    # ═════════════════════════════════════════════════════════════════════
    # 9. FAQ
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("❓ Frequently Asked Questions", "faq"), unsafe_allow_html=True)

    faqs = [
        ("Does it really run without me?",
         ("Yes — once started, the system makes all decisions autonomously. "
         "You only interact for monitoring or emergency intervention.")),
        ("How do I log in?",
         "Enter your username and password on the login screen. If 2FA is "
         "enabled, you'll also need your 6-digit TOTP code. Default: admin / admin123."),
        ("Why does the Settings tab ask for my password again?",
         "Settings access re-authenticates after 5 minutes of inactivity for "
         "security. Enter your password again to unlock it."),
        ("Can I disable the login requirement?",
         "Not recommended — but you can comment out the require_login() call "
         "in src/dashboard/app.py. For development/testing only."),
        ("What is the TencentDB memory?",
         "It gives the LLM persistent memory of past decisions and outcomes so "
         "it learns from experience. Uses TencentDB for Redis (fastest) or "
         "FAISS locally if TencentDB isn't configured."),
        ("What does the Sentiment Analyzer show?",
         "A 360-degree view: news sentiment, social media, Fear & Greed Index, "
         "Put/Call ratio, VIX, central bank sentiment, and sentiment vs price divergences."),
        ("How does the Stock Predictor work?",
         "It combines MA crossovers, technical indicators, sentiment scores, and "
         "3 forecast models (linear regression, EMA, Monte Carlo) into a Buy/Sell/Hold "
         "recommendation with confidence level."),
        ("What does the Agentic AI do?",
         "It's an autonomous agent (Python + Rust) that runs all analysis in parallel, "
         "detects chart patterns, makes Buy/Sell/Hold decisions, self-monitors system "
         "health, and self-heals failed components."),
        ("Can I disable the autonomous mode?",
         "Yes — ⚙️ SETTINGS → Operating Mode → Manual. You'll get alerts instead of auto-execution."),
        ("How many strategies does it run?",
         ("50+ strategies in `src/strategies/`. The brain selects the top 3–5 "
         "based on current session, volatility, and recent performance.")),
        ("Why is the chart different from TradingView.com?",
         ("We use TradingView's FOSS `lightweight-charts` library (Apache 2.0). "
         "It's the same engine they embed on free sites — without the social/ideas features.")),
        ("What's the difference between SIMULATION_MODE=True and False?",
         ("True → orders are simulated, no real money moves. Use this to test. "
         "False → orders are sent to the live broker.")),
        ("Can I run it on a Mac/Linux?",
         "Yes — Python is cross-platform. Only the MT5 EA is Windows-only (it's an MQL5 binary)."),
        ("How do I add my own strategy?",
         ("1. Create `src/strategies/my_strategy.py` extending `BaseStrategy`.\n"
         "2. Decorate with `@register_strategy`.\n"
         "3. Restart the dashboard. It appears in ⚔️ STRATEGY ENGINE automatically.")),
        ("How is PnL colored?",
         ("Green for profit, red for loss — both in the dashboard AND the MT5 HUD. "
         "Each field (symbol, ticket, entry, SL, TP, etc.) has its own distinct color.")),
        ("Can I backtest a strategy?",
         ("Yes — ⚔️ STRATEGY ENGINE → select strategy → 'Backtest'. "
         "Choose date range, symbol, timeframe, and capital. Results show equity curve, Sharpe, drawdown.")),
        ("How accurate is the LLM?",
         ("Target is 99% validation accuracy (auto-stops). Real-world accuracy "
         "depends on market regime. Check 🤖 AI & LLM → 'Recent Predictions vs Outcomes'.")),
        ("Does it support crypto?",
         "Yes — Binance, Bybit, Kraken via CCXT. Sessions auto-fallback to crypto when Forex is closed."),
        ("What happens during a power outage?",
         ("The MT5 EA auto-closes positions before any planned shutdown. "
         "The dashboard auto-saves state every 60 s. On restart, it resumes from the last checkpoint.")),
        ("How do I export trade history?",
         ("📚 TRADE BOOK → 'Export CSV'. "
         "Or run: `psql -U trader -d forex -c \"SELECT * FROM trades\" > trades.csv`")),
        ("Can multiple users log in?",
         ("Yes — each user gets their own credentials (🔐 CREDENTIALS). "
         "Admin role required for global config changes.")),
        ("What's the minimum capital?",
         ("MT5 demo: $100. Live micro lots (0.01): $100. Live standard lots (1.0): $10,000. "
         "Lower balance → automatically scales down lot size.")),
    ]

    for q, a in faqs:
        with st.expander(f"❓ {q}"):
            st.markdown(a)

    # ═════════════════════════════════════════════════════════════════════
    # 10. GLOSSARY
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("📚 Glossary", "glossary"), unsafe_allow_html=True)

    glossary = [
        ("ATR", "Average True Range — volatility indicator"),
        ("BB", "Bollinger Bands — volatility envelope"),
        ("CCXT", "Crypto exchange unified library (Binance, Bybit, etc.)"),
        ("EMA", "Exponential Moving Average"),
        ("EA", "Expert Advisor — MT5 trading robot"),
        ("FOSS", "Free & Open-Source Software"),
        ("GIL", "Global Interpreter Lock — Python's threading bottleneck"),
        ("HFT", "High-Frequency Trading"),
        ("HUD", "Heads-Up Display — on-chart info overlay"),
        ("MACD", "Moving Average Convergence Divergence"),
        ("MAE", "Maximum Adverse Excursion"),
        ("MFE", "Maximum Favorable Excursion"),
        ("MT5", "MetaTrader 5 — forex/cfd platform"),
        ("PnL", "Profit and Loss"),
        ("RAG", "Retrieval-Augmented Generation (LLM pattern)"),
        ("RSI", "Relative Strength Index"),
        ("Sharpe", "Risk-adjusted return ratio (Sharpe Ratio)"),
        ("SL/TP", "Stop Loss / Take Profit"),
        ("SMC", "Smart Money Concepts"),
        ("Spread", "Bid/Ask difference"),
        ("Stoch", "Stochastic Oscillator"),
        ("TF", "Timeframe (1m, 5m, 1h, 1D…)"),
        ("TOTP", "Time-based One-Time Password (2FA)"),
        ("VWAP", "Volume-Weighted Average Price"),
        ("XGBoost", "Gradient boosting ML library"),
        ("Agentic AI", "Autonomous AI agent that manages the trading system (Python + Rust)"),
        ("FAISS", "Facebook AI Similarity Search — vector index for fast retrieval"),
        ("TencentDB", "Tencent's managed Redis database — fastest agent memory backend"),
        ("Monte Carlo", "Statistical simulation running thousands of scenarios in parallel"),
        ("RAG", "Retrieval-Augmented Generation — LLM pattern using memory for context"),
        ("Sentiment Score", "Numerical value -1 to +1 indicating bearish to bullish sentiment"),
        ("Fear & Greed Index", "Composite sentiment metric (0=extreme fear, 100=extreme greed)"),
        ("Put/Call Ratio", "Options put volume / call volume — bearish indicator when >1.0"),
        ("Head & Shoulders", "Chart pattern: 3 peaks with middle highest — bearish reversal signal"),
    ]
    df_glos = pd.DataFrame(glossary, columns=["Term", "Meaning"])
    st.dataframe(df_glos, use_container_width=True, hide_index=True)

    # ═════════════════════════════════════════════════════════════════════
    # 11. COMMAND BAR
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("⌨️ Command Bar Reference", "command-bar"), unsafe_allow_html=True)

    cmds = [
        ("/help", "Show this help"),
        ("/status", "Show system status (PnL, positions, brain state)"),
        ("/logs", "Tail the live log"),
        ("/config", "Show current configuration"),
        ("/backup", "Snapshot the system state"),
        ("/shutdown", "Stop all trading"),
        ("/buy SYMBOL LOT", "Open manual BUY (e.g. `/buy EURUSD 0.5`)"),
        ("/sell SYMBOL LOT", "Open manual SELL (e.g. `/sell XAUUSD 1.0`)"),
        ("/close SYMBOL", "Close all positions on symbol"),
        ("/closeall", "EMERGENCY: close everything"),
        ("/risk PCT", "Set risk per trade %"),
        ("/chart SYMBOL TF", "Open chart (e.g. `/chart BTCUSD 1h`)"),
        ("/vwap SYMBOL BARS", "Calculate VWAP for last N bars"),
        ("/strategy NAME", "Show strategy details"),
        ("/enable NAME", "Enable a strategy"),
        ("/disable NAME", "Disable a strategy"),
        ("/emergency closeall", "Same as /closeall but typed explicitly"),
    ]
    df_cmd = pd.DataFrame(cmds, columns=["Command", "Description"])
    st.dataframe(df_cmd, use_container_width=True, hide_index=True)

    # ═════════════════════════════════════════════════════════════════════
    # 12. TUTORIALS
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("🎓 Step-by-Step Tutorials", "tutorials"), unsafe_allow_html=True)

    with st.expander("📘 Tutorial 1: Configure your first broker (MT5)"):
        st.markdown("""
1. Open 🔗 BROKER CONFIG → click "+ Add Broker"
2. Choose `MT5` from the dropdown
3. Fill in:
   - Login: `60022138`
   - Password: `[REDACTED]` (never share!)
   - Server: `4TLtd-Live`
   - Symbol prefix: (empty)
   - Magic number: `60022138` (must be unique)
4. Click "Test Connection" → should show green ✅
5. Click "Save"
        """)

    with st.expander("📘 Tutorial 2: Set up a Binance API key"):
        st.markdown("""
1. Log in to binance.com → API Management
2. Create new key: enable "Enable Spot Trading", "Enable Futures"
3. Copy API Key + Secret into 🔐 CREDENTIALS
4. (Optional) Enable IP whitelist — add your server's IP
5. Click "Test Connection"
6. Enable 2FA on Binance account first (recommended)
        """)

    with st.expander("📘 Tutorial 3: Configure 2FA / MFA for the dashboard"):
        st.markdown("""
1. Install Google Authenticator or Authy on your phone
2. Go to 🔐 CREDENTIALS → "Setup 2FA"
3. Scan QR code with authenticator
4. Enter 6-digit code to confirm
5. **Save backup codes** — you'll need them if you lose your phone
6. From next login, you'll need both password + TOTP code
        """)

    with st.expander("📘 Tutorial 4: Write a custom strategy"):
        st.markdown("""
```python
# src/strategies/my_rsi_strategy.py
from src.strategy.base import BaseStrategy, register_strategy

@register_strategy
class MyRSIStrategy(BaseStrategy):
    name = "RSI Mean Reversion v1"
    style = "mean_reversion"

    def generate_signal(self, df):
        rsi = df['rsi_14'].iloc[-1]
        if rsi < 30:
            return {'side': 'BUY', 'confidence': 0.8}
        elif rsi > 70:
            return {'side': 'SELL', 'confidence': 0.8}
        return None
```

After saving, restart dashboard. New strategy appears in ⚔️ STRATEGY ENGINE.
        """)

    with st.expander("📘 Tutorial 5: Run a backtest"):
        st.markdown("""
1. ⚔️ STRATEGY ENGINE → pick a strategy
2. Click "Backtest"
3. Set:
   - Symbol: `EURUSD`
   - Timeframe: `1h`
   - Start: `2024-01-01`
   - End: `2024-12-31`
   - Initial capital: `$10,000`
4. Click "Run" → wait ~30 s
5. Results show: equity curve, Sharpe, max drawdown, win rate, total trades
        """)

    with st.expander("📘 Tutorial 6: Train the LLM on your own data"):
        st.markdown("""
```python
from src.ai.custom_llm import CustomFinancialLLM

llm = CustomFinancialLLM()

# Add custom text corpora (news, filings, etc.)
llm.add_corpus([
    "Fed signals 25bp cut in September meeting minutes",
    "ECB holds rates steady amid inflation concerns",
    # ... hundreds more
])

# Run training
llm.run_continuous_training(max_epochs=50)
```

Or use 🤖 AI & LLM tab → "Train" → upload your CSV/text corpus.
        """)

    with st.expander("📘 Tutorial 7: Add a new external data source"):
        st.markdown("""
1. 🌐 EXTERNAL DATA → "Add Source"
2. Choose type: REST API, RSS, Web Crawler, WebSocket
3. Fill URL, auth (if any), refresh rate
4. Test fetch → verify data shape
5. Save → data flows into 📥 DATA INGESTION automatically
        """)

    with st.expander("📘 Tutorial 8: Configure overnight safety"):
        st.markdown("""
1. 🌙 OVERNIGHT SAFETY
2. Set "Auto-close at" → `22:00 UTC` (or your preference)
3. Enable "Friday flatten" → `30 min` before market close
4. Enable "News blackout" → choose high-impact only
5. Set "Max overnight exposure" → e.g. `2%` of equity
6. Enable "Deadman switch" → `5 min` heartbeat
7. Save
        """)

    with st.expander("📘 Tutorial 9: Use the parallel engine from your own code"):
        st.markdown("""
```python
from src.core.parallel import parallel_map, run_monte_carlo

# Parallel CPU-bound
def heavy_calc(x):
    return sum(i*i for i in range(1_000_000)) * x

results = parallel_map(heavy_calc, range(100))

# Monte Carlo
def trade_simulation():
    import random
    return random.gauss(0, 50)

stats = run_monte_carlo(trade_simulation, n=100_000)
print(f"95% CI: {stats['p5']:.2f} to {stats['p95']:.2f}")
```
        """)

    with st.expander("📘 Tutorial 10: Monitor a live trading session"):
        st.markdown("""
Best workflow during a live session:

1. **📊 OVERVIEW** — keep visible, watch PnL tick up
2. **📈 LIVE CHART** — verify entries match what you expected
3. **🧠 BRAIN** — see *why* the system took each trade
4. **📋 TRADES** — monitor execution quality (slippage, latency)
5. **⏱️ MONITORING** — alerts tab, set thresholds
6. **🖥️ CONSOLE** — debug if anything looks wrong

Recommended refresh rate: 5–10 s. Faster doesn't help; slower hides issues.
        """)

    # ═════════════════════════════════════════════════════════════════════
    # 13. SUPPORT
    # ═════════════════════════════════════════════════════════════════════
    st.markdown(_section("📞 Support & Resources", "support"), unsafe_allow_html=True)

    st.markdown("""
- **In-app**: every tab has a `?` icon → tooltip / inline help
- **Logs**: 🪵 EXECUTION LOG + `logs/` directory on disk
- **Status page**: ⏱️ MONITORING → Service Health
- **Documentation**: this 📖 HELP tab
- **Emergency**: see 🚨 Emergency Actions section above

### 🎨 System Logo & Icon
- **Logo**: `assets/logo.svg` — 512×512 candlestick + trend line design, displayed on the login screen and sidebar
- **Icon**: `assets/icon.png` — 256×256 simplified version, used as the browser tab favicon (`page_icon`)
- **Branding**: EAQTS — Elite Autonomous Quantum Trading System
- To replace the logo, edit `assets/logo.svg` or replace `assets/logo.png`.

### System Info Snapshot
    """)
    st.code(json.dumps(info, indent=2), language="json")

    st.markdown(_callout("tip",
        "When reporting a bug, include the system info above + relevant "
        "log lines. 90% of issues resolve faster with timestamps."
    ), unsafe_allow_html=True)

    st.markdown("---")
    st.caption(
        "Elite Autonomous Quantum Trading System v2.0 · "
        "Self-Learning · Self-Training · Self-Healing · "
        "Always Watching the Markets for You."
    )
