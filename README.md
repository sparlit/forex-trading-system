# Forex Trading System (EAQTS V2.4)

## Project Report & Insights
The EAQTS V2.4 system is a **full‑stack autonomous forex & crypto trading platform** built with Python 3.11/3.12 and managed via Poetry.  It integrates live market feeds (MT5, CCXT), regime detection, macro fundamentals, transaction‑cost analysis (TCA), self‑diagnostics, and an autonomous evolution engine.  All components are unit‑tested (91 tests) and conform to the strict linting and typing rules enforced by Ruff, Black, isort and mypy.

## Detailed Walk‑through
1. **Initialisation** – `src/trading_loop/engine.py` creates a `TradingLoop`, starts the Prometheus exporter, and launches a health‑monitor thread (checks every 60 s).
2. **Market Data** – `src/data_ingestion/mt5_feed.py` and `ccxt_feed.py` provide deterministic stubs for CI and live feeds when configured.
3. **Macro Pipeline** – pulls synthetic economic‑calendar events and basic sentiment counts; merged into a shared `MarketState`.
4. **Regime Detection** – simple moving‑average crossover (`src/regime_detection/detector.py`) labels the market as `BULL` or `BEAR`.
5. **Opportunity Engine** – generates signals based on regime, macro view and TCA metrics.
6. **Execution Core** – submits orders, logs them in `src/tca/analysis.py`, and updates Prometheus gauges (`eaqts_tca_slippage_seconds`, `eaqts_tca_fill_rate`).
7. **Self‑Diagnostics** – `src/self_diagnostics/health.py` validates EventBus publishing, market‑state freshness and component liveliness; failures raise a `RestartSignal`.
8. **Adversarial Testing** – `src/adversarial_testing/fuzzer.py` injects Gaussian noise into numeric market‑state fields to verify robustness.
9. **Autonomous Evolution** – `src/autonomous_evolution/engine.py` tracks a sliding‑window of performance; `should_adapt()` becomes `True` when performance drops > 10 %.
10. **Prometheus Monitoring** – `src/monitoring/prometheus_client.py` creates gauges for live positions, PnL, execution latency and TCA metrics.
11. **Dashboard (optional)** – Streamlit UI reads the Prometheus endpoint for real‑time visualisation.

---

## Installation & Configuration (Simplified)

The goal is **one command** to get a working environment. All heavy‑lifting is done by the new `eaqts-cli` helper.

### Prerequisites (run once)
| Tool | Why it’s needed | Install command |
|------|----------------|-----------------|
| **Scoop** (Windows package manager) | Installs Python, Poetry and optional services | `powershell -Command "iwr -useb get.scoop.sh | iex"` |
| **Git** (optional) | Clone the repo if you haven’t already | `scoop install git` |

If you already have Python 3.11+ and Poetry on your PATH you can skip Scoop entirely.

### One‑step setup
From a **PowerShell** or **Command Prompt** run:

```bash
# Clone the repo (skip if you already have a local copy)
git clone https://github.com/sparlit/forex-trading-system D:\forex-trading-system
cd D:\forex-trading-system

# Run the bundled CLI – it will:
#   • Install Python 3.11+ and Poetry (via Scoop) if missing
#   • Install all Python dependencies (`poetry install --with dev,ml,viz,trading`)
#   • Copy .env.example → .env and prompt you for any missing secrets
#   • Initialise a local PostgreSQL database (if you installed the service)
#   • Start the Prometheus exporter in the background
#   • Verify the setup (run a quick test suite)
eaqts-cli init
```

The command interacts interactively only when it cannot infer a value (e.g., API keys). For a **purely non‑interactive** run, pre‑populate a `.env` file before invoking `eaqts-cli init`.

### Running the system
After a successful `init` you can start the autonomous trading loop with a single command:

```bash
eaqts-cli start
```

The CLI will launch the trading loop in the background, write its PID to `scripts/eaqts_cli.pid`, and keep a health‑monitor active.

To stop the loop, simply run:

```bash
eaqts-cli stop
```

You can always check the current status:

```bash
eaqts-cli status
```

### Optional services
If you need the full production stack (PostgreSQL, Redis, InfluxDB, NATS, Grafana) install them via Scoop:

```powershell
scoop install postgresql redis influxdb nats-server prometheus grafana
```

The `eaqts-cli init` script will detect the presence of these services and start the Prometheus exporter automatically. If a service is missing, the trading loop will still run using in‑memory fallbacks.

### Quick sanity check
After `eaqts-cli start` you should see regular log lines such as:

```
[INFO] Health check passed
[INFO] Trading loop started
```

You can also verify that Prometheus metrics are exposed:

```bash
curl http://localhost:8000/metrics | grep eaqts_
```

If you see a list of `eaqts_*` gauges the installation succeeded.

---

The rest of the README (project report, FAQ, error codes, emergency plan, glossary, help) remains unchanged.

### Configuration Files
- **`config/settings.yaml`** – defines feed selection, risk limits, and Prometheus port.
- **`.env.example`** – copy to `.env` and fill in MT5 credentials, exchange API keys and database URLs.

---

## FAQ
**Q1 – Why are deterministic stubs used for MT5/CCXT?**
A: CI cannot rely on live broker connections; deterministic stubs guarantee repeatable tests while production uses real APIs.

**Q2 – How do I enable real‑time market data?**
A: Set `feed: mt5` (or `ccxt`) in `config/settings.yaml` and provide valid credentials in `.env`.

**Q3 – My Prometheus gauges are missing.**
A: Ensure `src.monitoring.prometheus_client` is running before starting `TradingLoop`. The exporter defaults to port 8000.

**Q4 – The health‑monitor thread stops the system unexpectedly.**
A: A `RestartSignal` indicates a failed health check (e.g., stale market data). Review the logs, resolve the underlying issue, and restart the loop.

---

## Error Codes, Explanations & Remedies
| Code | Area | Meaning | Common Causes | Remedy |
|------|------|---------|---------------|--------|
| `E001` | `self_diagnostics` | Health check failed | Missing EventBus subscription, stale market state | Verify `EventBus.publish` works; ensure feeds are publishing. |
| `E002` | `tca` | Gauge update exception | `numpy` not installed or NaN values | Install `numpy`; guard against `np.isnan`. |
| `E100` | `autonomous_evolution` | Adaptation flag false despite poor performance | `EvolutionEngine.performance_history` not updated | Call `evolution_engine.update(performance)` each loop iteration. |
| `E200` | `prometheus_client` | Port already in use | Another process bound to 8000 | Stop the other process or change `settings.prometheus.port`. |

---

## Emergency Action Plan
1. **Stop the trading loop** – press `Ctrl+C` in the terminal running `src.trading_loop.engine`.
2. **Collect logs** – `logs/` contains `trading_loop.log`, `health.log`, and `prometheus.log`.
3. **Restore last known good state** – `git checkout <last_good_commit>` (if using Git) or revert changed files manually.
4. **Reset the database** (if corrupted):
   ```bash
   psql -U postgres -c "DROP DATABASE eaqts; CREATE DATABASE eaqts;"
   ```
5. **Restart services** – restart Prometheus, PostgreSQL, etc., then repeat the installation steps.

---

## Glossary
- **EAQTS** – *Enterprise‑Grade Autonomous Quant Trading System*.
- **TCA** – *Transaction Cost Analysis* (slippage, fill‑rate).
- **EventBus** – internal publish/subscribe hub for decoupled components.
- **RestartSignal** – custom exception used by the health‑monitor to trigger a graceful restart.
- **Gauge** – Prometheus metric representing a single numerical value that can go up or down.
- **Fuzzer** – tool that injects malformed or noisy data to test system resilience.

---

## Detailed Help
For operational details consult:
- **`src/README.md`** – module‑level documentation generated by `pydoc`.
- **`docs/`** – architecture diagrams and API specifications.
- **`AGENTS.md`** – coding style, testing and commit guidelines.
- **`CONTRIBUTING.md`** – how to add new strategies, tests or plugins.

---

*End of README*