"""Safety Kernel.
Coordinates emergency controls, compliance checks, and shutdown handling.
"""

from collections.abc import Callable


class SafetyKernel:
    def __init__(self):
        self.emergency_handlers: list[Callable[[], None]] = []
        self.compliance_checks: list[Callable[[], bool]] = []

    def register_emergency_handler(self, handler: Callable[[], None]):
        self.emergency_handlers.append(handler)

    def register_compliance_check(self, check: Callable[[], bool]):
        self.compliance_checks.append(check)

    def run_compliance(self) -> bool:
        """Run all compliance checks; return True if all pass."""
        return all(check() for check in self.compliance_checks)

    def trigger_emergency(self):
        for handler in self.emergency_handlers:
            try:
                handler()
            except Exception:
                # In production log the failure; here we ignore
                pass
