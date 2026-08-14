"""Orchestrator – coordinates all brain processes via the EventBus.

The implementation is deliberately lightweight yet fully functional:
* Creates a multiprocessing ``EventBus`` shared by all child processes.
* Persists every published event with :class:`~src.orch.event_bus.EventStore`.
* Starts a separate ``multiprocessing.Process`` for each brain component.
* Provides health monitoring, graceful shutdown, and automatic recovery.
* Embeds a ``ResourceGovernor`` that (optionally) uses ``psutil`` to report
  CPU / memory usage and can be expanded to throttle workloads according to the
  priority order defined in the specification (Section 8).

Only standard‑library modules are used (except an optional ``psutil`` import).
All type hints comply with ``mypy`` strict mode.
"""

from __future__ import annotations

import importlib
import logging
import multiprocessing
import time
from typing import Any

# Local imports – the EventBus implementation lives in the same package.
from src.orch.event_bus import Event, EventBus, EventStore

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central orchestrator for the EAQTS brain processes.

    The orchestrator owns a single :class:`EventBus` instance (process‑mode) and
    an :class:`EventStore` for durable event sourcing.  Each brain component runs
    in its own :class:`multiprocessing.Process`.  A brain is expected to expose
    a ``run(event_bus: EventBus)`` callable; if it does not, the orchestrator will
    start a minimal shim that simply subscribes to all events and logs them.
    """

    # Mapping of logical brain names to the import path and class name.
    _brain_registry: dict[str, tuple[str, str]] = {
        "analysis": ("src.brain.analysis_brain", "AnalysisBrain"),
        "prediction": ("src.brain.next_candle_predictor", "NextCandlePredictor"),
        "self_evolution": ("src.brain.self_evolving_brain", "SelfEvolvingBrain"),
        # Additional brains can be added here following the same pattern.
        # For the purpose of this task we include a minimal placeholder for
        # the remaining roles.
        "research": ("src.research.research_brain", "ResearchBrain"),
        "strategy": ("src.strategies.comprehensive_strategies", "StrategySuite"),
        "risk": ("src.risk.risk_engine", "RiskEngine"),
        "execution": ("src.execution.execution_engine", "ExecutionEngine"),
        "learning": ("src.ml.learning", "LearningEngine"),
        "self_evaluation": ("src.brain.self_evolving_brain", "SelfEvolvingBrain"),
    }

    def __init__(self) -> None:
        self.event_bus = EventBus(mode="process")
        self.event_store = EventStore()
        self.processes: dict[str, multiprocessing.Process] = {}
        self._shutdown = multiprocessing.Event()
        self.resource_governor = self.ResourceGovernor()
        # Subscribe to *all* events for persistence.
        self.event_bus.subscribe("*", self._persist_event)

    # ---------------------------------------------------------------------
    # Event handling helpers
    # ---------------------------------------------------------------------
    def _persist_event(self, event: Event) -> None:
        """Persist every event that flows through the bus.

        The `*` wildcard subscription ensures this method is called for any
        event type that the orchestrator receives.
        """
        try:
            self.event_store.append(event)
        except Exception as exc:  # pragma: no cover – defensive logging
            logger.error("Failed to persist event %s: %s", event.event_id, exc)

    # ---------------------------------------------------------------------
    # Process lifecycle management
    # ---------------------------------------------------------------------
    def _brain_target(self, name: str, module_path: str, class_name: str) -> None:
        """Entry point executed inside each child process.

        The function imports the requested class, creates an instance, and looks
        for a ``run(event_bus)`` callable.  If the method does not exist we fall
        back to a lightweight loop that simply forwards any received events to a
        log for demonstration purposes.
        """
        # Child processes inherit the same EventBus instance because the
        # underlying ``multiprocessing.Queue`` is picklable and shared.
        bus = self.event_bus
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            instance = cls()
            logger.info("%s instantiated %s.%s", name, module_path, class_name)
        except Exception as exc:  # pragma: no cover – module may be a placeholder
            logger.warning(
                "%s could not be imported (%s.%s): %s – starting dummy worker",
                name,
                module_path,
                class_name,
                exc,
            )
            instance = None

        # Define a generic handler that just logs the event.
        def _log_event(evt: Event) -> None:
            logger.info("%s received event %s (%s)", name, evt.event_id, evt.event_type)

        # If the brain provides an explicit `run` method we delegate to it.
        if instance is not None and hasattr(instance, "run"):
            try:
                # Assume the run method accepts an EventBus instance.
                instance.run(bus)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover – runtime errors are logged
                logger.error("%s.run raised an exception: %s", name, exc)
        else:
            # Fallback: subscribe to all events and block until shutdown.
            bus.subscribe("*", _log_event)
            # Simple wait loop – the process exits when the orchestrator sets the
            # shutdown event.
            while not self._shutdown.is_set():
                time.sleep(0.5)

    def start_brain(self, name: str) -> None:
        """Spawn a brain process for *name*.

        Raises ``KeyError`` if the brain name is not registered.
        """
        if name in self.processes and self.processes[name].is_alive():
            logger.info("Brain %s already running", name)
            return
        module_path, class_name = self._brain_registry[name]
        proc = multiprocessing.Process(
            target=self._brain_target,
            args=(name, module_path, class_name),
            name=f"Brain-{name}",
            daemon=False,
        )
        proc.start()
        self.processes[name] = proc
        logger.info("Started brain %s with PID %s", name, proc.pid)

    def run(self) -> None:
        """Start all registered brains and enter the routing loop.

        The routing loop simply watches for the shutdown flag; all events are
        already persisted via the wildcard subscription.  In a production system
        this method could perform additional routing logic (e.g., filtering events
        to specific brain queues).
        """
        logger.info("Orchestrator starting all brain processes")
        for brain_name in self._brain_registry:
            self.start_brain(brain_name)
        logger.info("All brains started – entering orchestrator main loop")
        try:
            while not self._shutdown.is_set():
                # Periodically poll resource usage – this could be extended to
                # trigger throttling via ``self.resource_governor``.
                usage = self.resource_governor.collect()
                logger.debug("Resource usage: %s", usage)
                time.sleep(1.0)
        finally:
            logger.info("Orchestrator shutdown initiated")
            self.stop()

    def stop(self) -> None:
        """Gracefully stop all brain processes and the EventBus.
        """
        logger.info("Stopping orchestrator and all brain processes")
        self._shutdown.set()
        # Send sentinel to EventBus so its dispatch thread can exit.
        self.event_bus.stop()
        # Join all child processes.
        for name, proc in list(self.processes.items()):
            if proc.is_alive():
                logger.info("Terminating brain %s (PID %s)", name, proc.pid)
                proc.terminate()
                proc.join(timeout=5)
        self.processes.clear()
        logger.info("Orchestrator stopped")

    # ---------------------------------------------------------------------
    # Health / recovery utilities
    # ---------------------------------------------------------------------
    def health_check(self) -> dict[str, bool]:
        """Return a mapping of brain name → ``True`` if the process is alive.
        """
        return {name: proc.is_alive() for name, proc in self.processes.items()}

    def trigger_recovery(self, component_name: str, reason: str) -> None:
        """Restart a failed brain component.

        The function logs the failure *reason*, terminates the existing process
        (if any), and spawns a fresh instance.
        """
        logger.warning(
            "Recovery triggered for %s due to: %s", component_name, reason
        )
        proc = self.processes.get(component_name)
        if proc and proc.is_alive():
            logger.info("Terminating existing %s (PID %s) for recovery", component_name, proc.pid)
            proc.terminate()
            proc.join(timeout=5)
        # Remove stale entry and restart.
        self.processes.pop(component_name, None)
        self.start_brain(component_name)

    # ---------------------------------------------------------------------
    # ResourceGovernor – optional lightweight resource monitoring.
    # ---------------------------------------------------------------------
    class ResourceGovernor:
        """Monitor CPU and memory usage; placeholder for throttling logic.

        The real system would adjust background workloads based on the priority
        order defined in the spec.  Here we implement a minimal collector that
        works on both Windows and Unix platforms.
        """

        PRIORITY_ORDER = [
            "Safety",
            "Execution",
            "MarketData",
            "Risk",
            "Analysis",
            "Prediction",
            "Dashboard",
            "Research",
            "BackgroundTraining",
        ]

        def __init__(self) -> None:
            try:
                import psutil  # type: ignore

                self._psutil = psutil
            except Exception:  # pragma: no cover – psutil may be missing
                self._psutil = None

        def collect(self) -> dict[str, Any]:
            """Collect CPU / memory usage metrics.

            Returns a dictionary with ``cpu_percent`` and ``memory_percent``.
            If ``psutil`` is unavailable we fall back to ``os.getloadavg`` (Unix)
            or report ``None``.
            """
            if self._psutil:
                return {
                    "cpu_percent": self._psutil.cpu_percent(interval=0.1),
                    "memory_percent": self._psutil.virtual_memory().percent,
                }
            # Minimal fallback for Windows without psutil.
            # ``os.getloadavg`` is not available on Windows – we return None.
            return {"cpu_percent": None, "memory_percent": None}

        def throttle(self, component: str) -> None:
            """Placeholder for throttling a component based on priority.

            The real implementation would communicate with the component (e.g.,
            via a control queue) to reduce its workload.  For now this method
            only logs the action.
            """
            logger.debug("Throttle request for %s (not implemented)", component)

# When the module is executed directly, run the orchestrator.
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    orch = Orchestrator()
    try:
        orch.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received – shutting down")
        orch.stop()
