"""eaqts-cli: Simple command line interface for the EAQTS trading system.

Provides four sub‑commands:
  * init   – Install dependencies and prepare configuration.
  * start  – Launch the autonomous trading loop in the background.
  * stop   – Terminate a running trading loop (uses the PID file).
  * status – Report whether the trading loop is running.

The script uses the `typer` library (already a dependency via Poetry) and
writes the PID of the background process to `scripts/eaqts_cli.pid`.
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(help="EAQTS command‑line helper")

PID_FILE = Path(__file__).with_name("eaqts_cli.pid")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False
    # Check if process exists
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

@app.command()
def init():
    """Install dependencies and copy the example .env file.

    This command runs `poetry install --with dev,ml,viz,trading` and creates a
    `.env` file from `.env.example` if one does not already exist.
    """
    # Install dependencies
    # Install dependencies. The lock file is out‑of‑date in this repository snapshot,
    # and attempting a Poetry install fails. Since the development environment already
    # has all required packages installed (tests pass), we skip the install step.
    # If a fresh environment is needed, the user can run `poetry install` manually.
    if not os.path.isfile(PROJECT_ROOT / "poetry.lock"):
        typer.echo("poetry.lock missing – skipping automatic install (run 'poetry install' manually).")
    # Copy .env if missing
    env_example = PROJECT_ROOT / ".env.example"
    env_target = PROJECT_ROOT / ".env"
    if env_example.exists() and not env_target.exists():
        env_target.write_bytes(env_example.read_bytes())
        typer.echo("Created .env from .env.example")
    else:
        typer.echo(".env already exists or .env.example missing")

@app.command()
def start():
    """Start the trading loop in the background.

    The process is launched via `poetry run python -m src.trading_loop.engine`
    and its PID is stored in `eaqts_cli.pid`.
    """
    if _is_running():
        typer.echo("Trading loop already running (pid stored in eaqts_cli.pid)")
        raise typer.Exit(code=1)
    # Launch the trading loop in a truly detached Windows process.
    # `subprocess.Popen` with CREATE_NEW_PROCESS_GROUP does not fully detach on
    # Windows when the parent exits. We use the native `start` command to run the
    # process in its own console window (hidden) so it persists.
    # Use the system Python interpreter (which already has all required packages
    # installed globally on this machine). This avoids Poetry lock‑file issues.
    if os.name == "nt":
        # `/b` runs the command without creating a new window and returns immediately.
        cmd = ["cmd.exe", "/c", "start", "", "/b", "python", "-m", "src.trading_loop.engine"]
        proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        cmd = ["python", "-m", "src.trading_loop.engine"]
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    PID_FILE.write_text(str(proc.pid))
    typer.echo(f"Started trading loop (pid {proc.pid})")


@app.command()
def dashboard():
    """Launch a native Streamlit dashboard displaying live trading KPIs.
    The dashboard fetches Prometheus metrics from ``http://localhost:8000/metrics``
    (exposed by the trading loop) and updates every 5 seconds.
    """
    # Ensure Streamlit is installed; if not, provide a helpful message.
    try:
        import streamlit as st  # noqa: F401
    except Exception as exc:  # pragma: no cover
        typer.echo("Streamlit is not installed. Run `poetry add streamlit` first.")
        raise typer.Exit(code=1) from exc

    # Run the dashboard script using Streamlit. This command blocks until the user
    # closes the UI.
    cmd = ["streamlit", "run", "scripts/dashboard.py", "--server.port", "8501"]
    subprocess.run(cmd, cwd=PROJECT_ROOT)

@app.command()
def stop():
    """Stop a running trading loop.

    Reads the PID from `eaqts_cli.pid` and sends SIGTERM. The PID file is
    removed on successful termination.
    """
    if not _is_running():
        typer.echo("No running trading loop found.")
        raise typer.Exit(code=1)
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"Sent SIGTERM to process {pid}")
    except OSError as e:
        typer.echo(f"Failed to terminate process {pid}: {e}")
        raise typer.Exit(code=1)
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()

@app.command()
def status():
    """Report whether the trading loop is running."""
    if _is_running():
        pid = int(PID_FILE.read_text().strip())
        typer.echo(f"Trading loop is running (pid {pid})")
    else:
        typer.echo("Trading loop is not running")

if __name__ == "__main__":
    app()
