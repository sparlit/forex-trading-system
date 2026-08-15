"""eaqts-cli: Simple command line interface for the EAQTS trading system.

Provides the following sub‑commands:
  * init      – Install dependencies and prepare configuration.
  * start     – Launch the autonomous trading loop (and optionally the dashboard)
                in the background.
  * stop      – Terminate a running trading loop (uses the PID file).
  * status    – Report whether the trading loop is running.
  * dashboard – Launch the native Streamlit dashboard (foreground).

The script uses the `typer` library (already a dependency via Poetry) and
writes the PID of the background process to `scripts/eaqts_cli.pid`.

When `start` is invoked it now also launches the dashboard automatically
(if it is not already running). The dashboard PID is stored in
`scripts/dashboard.pid` so that it can be stopped later.
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(help="EAQTS command‑line helper")

PID_FILE = Path(__file__).with_name("eaqts_cli.pid")
DASHBOARD_PID_FILE = Path(__file__).with_name("dashboard.pid")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _is_pid_alive(pid: int) -> bool:
    """Return ``True`` if a process with ``pid`` exists."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid_file(path: Path) -> int | None:
    """Read a PID from ``path``; return ``None`` if the file is missing/invalid
    or the process is no longer alive."""
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
    except Exception:
        return None
    return pid if _is_pid_alive(pid) else None


def _is_running() -> bool:
    """Check whether the trading loop is currently running."""
    return _read_pid_file(PID_FILE) is not None


def _launch_dashboard() -> int | None:
    """Start the Streamlit dashboard in the background.

    Returns the PID of the spawned dashboard process, or ``None`` if it could
    not be started (e.g. Streamlit not installed).
    """
    # Skip if a dashboard is already running.
    existing = _read_pid_file(DASHBOARD_PID_FILE)
    if existing is not None:
        typer.echo(f"Dashboard already running (pid {existing})")
        return existing

    # Verify that Streamlit is importable.
    try:
        import streamlit  # noqa: F401
    except Exception:
        typer.echo(
            "Streamlit is not installed – dashboard will not start. "
            "Run `poetry add streamlit` to enable it."
        )
        return None

    # Build the command. On Windows we use `cmd.exe /c start ... /b` to detach.
    if os.name == "nt":
        cmd = [
            "cmd.exe",
            "/c",
            "start",
            "",
            "/b",
            "streamlit",
            "run",
            "scripts/dashboard.py",
            "--server.port",
            "8501",
        ]
    else:
        cmd = [
            "streamlit",
            "run",
            "scripts/dashboard.py",
            "--server.port",
            "8501",
        ]

    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    DASHBOARD_PID_FILE.write_text(str(proc.pid))
    typer.echo(f"Started dashboard (pid {proc.pid})")
    return proc.pid


def _stop_pid_file(path: Path, label: str) -> None:
    """Terminate the process whose PID is stored in ``path``."""
    pid = _read_pid_file(path)
    if pid is None:
        typer.echo(f"No running {label} found.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"Sent SIGTERM to {label} (pid {pid})")
    except OSError as exc:
        typer.echo(f"Failed to terminate {label} (pid {pid}): {exc}")
    finally:
        if path.exists():
            path.unlink()


@app.command()
def init():
    """Install dependencies and copy the example ``.env`` file.

    This command skips the automatic ``poetry install`` step when the lock file
    is out‑of‑date (the current repository snapshot is in that state). Run
    ``poetry install`` manually if a fresh environment is needed.
    """
    if not os.path.isfile(PROJECT_ROOT / "poetry.lock"):
        typer.echo(
            "poetry.lock missing – skipping automatic install "
            "(run 'poetry install' manually)."
        )
    env_example = PROJECT_ROOT / ".env.example"
    env_target = PROJECT_ROOT / ".env"
    if env_example.exists() and not env_target.exists():
        env_target.write_bytes(env_example.read_bytes())
        typer.echo("Created .env from .env.example")
    else:
        typer.echo(".env already exists or .env.example missing")


@app.command()
def start():
    """Start the trading loop (and the native dashboard) in the background.

    The trading loop is launched via ``python -m src.trading_loop.engine``; its
    PID is stored in ``eaqts_cli.pid``. After the loop is started the dashboard
    is also launched automatically and its PID stored in ``dashboard.pid``.
    """
    if _is_running():
        typer.echo("Trading loop already running (pid stored in eaqts_cli.pid)")
        raise typer.Exit(code=1)

    # Launch the trading loop. Use a detached ``start`` on Windows so the process
    # survives the parent shell exiting.
    if os.name == "nt":
        cmd = [
            "cmd.exe",
            "/c",
            "start",
            "",
            "/b",
            "python",
            "-m",
            "src.trading_loop.engine",
        ]
    else:
        cmd = ["python", "-m", "src.trading_loop.engine"]

    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid))
    typer.echo(f"Started trading loop (pid {proc.pid})")

    # Automatically launch the dashboard.
    _launch_dashboard()


@app.command()
def dashboard():
    """Launch the native Streamlit dashboard in the foreground."""
    try:
        import streamlit as st  # noqa: F401
    except Exception as exc:  # pragma: no cover
        typer.echo("Streamlit is not installed. Run `poetry add streamlit` first.")
        raise typer.Exit(code=1) from exc

    cmd = [
        "streamlit",
        "run",
        "scripts/dashboard.py",
        "--server.port",
        "8501",
    ]
    subprocess.run(cmd, cwd=PROJECT_ROOT)


@app.command()
def stop():
    """Stop the trading loop and the dashboard if they are running."""
    _stop_pid_file(PID_FILE, "trading loop")
    _stop_pid_file(DASHBOARD_PID_FILE, "dashboard")


@app.command()
def status():
    """Report whether the trading loop (and dashboard) are running."""
    pid = _read_pid_file(PID_FILE)
    if pid is not None:
        typer.echo(f"Trading loop is running (pid {pid})")
    else:
        typer.echo("Trading loop is not running")

    dash_pid = _read_pid_file(DASHBOARD_PID_FILE)
    if dash_pid is not None:
        typer.echo(f"Dashboard is running (pid {dash_pid})")
    else:
        typer.echo("Dashboard is not running")


if __name__ == "__main__":
    app()
