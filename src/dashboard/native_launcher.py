#!/usr/bin/env python3
"""
Elite Autonomous Quantum Trading System - Native Dashboard Launcher
"""

import subprocess
import sys


def main():
    """Launch the native dashboard."""
    # Check if PyQt6 is available
    try:
        import PyQt6
        import qasync
    except ImportError:
        print("Installing native dashboard dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "PyQt6", "PyQt6-WebEngine", "qasync", "pyqtgraph"], check=True)
    
    # Import and run the native dashboard
    import qasync

    from src.dashboard.native_dashboard import NativeDashboard
    
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = NativeDashboard()
    window.show()
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()