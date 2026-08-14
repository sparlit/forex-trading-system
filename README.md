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

## Installation & Configuration
### Pre‑Installation Requirements
| Requirement | Description | Verify |
|-------------|-------------|--------|
| OS | Windows 10 64‑bit (native deployment) | `ver` |
| Python | 3.11 or 3.12 (installed via Scoop) | `python --version` |
| Poetry | Dependency manager (Scoop package) | `poetry --version` |
| Scoop | Windows package manager – must be on PATH | `scoop which scoop` |
| Git (optional) | For version control | `git --version` |
| External Services (production) | PostgreSQL, Redis, InfluxDB, NATS, Prometheus, Grafana – installed via Scoop if required | `scoop list` |
| MetaTrader 5 client | Required for live FX data (login `60022138`, `SIMULATE_TRADING=1`) | Verify MT5 connectivity |
| CCXT‑compatible APIs | Binance, Bybit, Kraken – API keys stored in `.env` | Ensure keys are present |

### Post‑Installation Verification
After setup, run these checks:
1. **Prometheus endpoint** – `curl http://localhost:8000/metrics` should return gauge definitions.
2. **Test suite** – `poetry run pytest -q` must report **0 failures**.
3. **Health monitor** – stdout should display `Health check passed` each minute.
4. **Dashboard** – if installed, open `http://localhost:3000` and confirm the Prometheus data source loads.

### Step‑by‑step Installation
```bash
# 1️⃣  Navigate to the project root (the repository is already cloned at D:\forex-trading-system)
cd D:\forex-trading-system

# 2️⃣  Install **Scoop** (if not present) and add the extra bucket which contains many of the required utilities
#     (skip if Scoop is already installed and on your PATH)
powershell -Command "iwr -useb get.scoop.sh | iex"
scoop bucket add extras

# 3️⃣  Install core system tools – **Python 3.11+** and **Poetry** (the dependency manager)
scoop install python
scoop install poetry

# 4️⃣  (Optional) Install production‑grade infrastructure services. These are only required for a full‑stack deployment; the CI test suite can run without them.
scoop install postgresql redis influxdb nats-server prometheus grafana

# 5️⃣  Install the Python package tree, including development, ML, visualisation and trading extras.
poetry install --with dev,ml,viz,trading

# 6️⃣  Create the runtime configuration file.
copy .env.example .env   # edit the resulting .env with your MT5 credentials, exchange API keys and any DB connection strings.
#   You can also customise `config/settings.yaml` – e.g. change the Prometheus port or select the market‑data feed.

# 7️⃣  Initialise the PostgreSQL database (adjust the user/password if your local instance uses different credentials)
psql -U postgres -c "CREATE DATABASE eaqts;"

# 8️⃣  Start background services required for the live system. Each command runs the service in the background so the terminal remains usable.
#   • Prometheus exporter (exposes metrics on :8000)
start /b poetry run python -m src.monitoring.prometheus_client
#   • (If you installed PostgreSQL, it should already be running as a Windows service. If not, start it manually.)

# 9️⃣  Launch the autonomous trading loop – this starts the main event loop, health monitor and market‑data ingestion.
poetry run python -m src.trading_loop.engine
```

### Running the Trading System from Ground Zero
The following checklist assumes a **brand‑new Windows 10 machine** with no prior Python or service installations.

1. **Install Scoop** – the Windows package manager that will pull down Python, Poetry and all optional services.
   ```powershell
   powershell -Command "iwr -useb get.scoop.sh | iex"
   ```
2. **Add the extras bucket** (contains PostgreSQL, Redis, etc.)
   ```powershell
   scoop bucket add extras
   ```
3. **Install core languages and tools**
   ```powershell
   scoop install python
   scoop install poetry
   ```
4. **(Optional) Install infrastructure services** – required only for a full production deployment.
   ```powershell
   scoop install postgresql redis influxdb nats-server prometheus grafana
   ```
5. **Clone the repository** (skip if you already have the code in `D:\forex-trading-system`).
   ```bash
   git clone https://github.com/your-org/forex-trading-system D:\forex-trading-system
   cd D:\forex-trading-system
   ```
6. **Install all Python dependencies** using Poetry.
   ```bash
   poetry install --with dev,ml,viz,trading
   ```
7. **Configure runtime secrets** – copy the example environment file and fill in the required values.
   ```bash
   copy .env.example .env
   # Edit .env:
   #   MT5_USER=your_user
   #   MT5_PASSWORD=your_password
   #   BINANCE_API_KEY=…
   #   POSTGRES_URL=postgresql://postgres@localhost/eaqts
   ```
8. **Create the PostgreSQL database** (skip if you are using an external DB).
   ```bash
   psql -U postgres -c "CREATE DATABASE eaqts;"
   ```
9. **Start the Prometheus exporter** – this must be running before the trading loop so metrics are collected.
   ```bash
   start /b poetry run python -m src.monitoring.prometheus_client
   ```
10. **Verify the exporter** – request the metrics endpoint.
    ```bash
    curl http://localhost:8000/metrics
    ```
    You should see a list of `eaqts_*` gauges.
11. **Run the autonomous trading engine** – this will start market‑data ingestion, the health monitor, and the main trade‑execution loop.
    ```bash
    poetry run python -m src.trading_loop.engine
    ```
    The console will output log lines such as `Health check passed` every minute and `Trading loop started` when the system is active.
12. **(Optional) Launch the Streamlit dashboard** for visual monitoring.
    ```bash
    poetry run streamlit run src/dashboard/app.py
    ```
    Open `http://localhost:8501` in a browser to see live KPIs.

Follow the steps exactly in order; missing any of the background services (Prometheus, PostgreSQL) will cause the trading loop to abort with clear error messages.

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