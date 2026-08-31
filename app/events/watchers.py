"""Local background watchers for filesystem changes, system metric thresholds, and application state."""

from datetime import datetime, timezone
from pathlib import Path
import threading
import time
from typing import Callable, Optional, Set

from app.core.config import Settings, get_settings
from app.core.exceptions import WatcherError
from app.core.logging import get_logger
from app.events.models import Event, EventOrigin, EventType
from app.tools.path_guard import PathGuard
from app.tools.system import SystemProvider

logger = get_logger("events.watchers")


class FileWatcher:
    """Monitors configured local directories bounded by PathGuard for file changes."""

    def __init__(
        self,
        event_sink: Callable[[Event], None],
        path_guard: Optional[PathGuard] = None,
        poll_interval: float = 1.0,
        settings: Optional[Settings] = None,
    ) -> None:
        self.event_sink = event_sink
        self.settings = settings or get_settings()
        self.path_guard = path_guard or PathGuard(settings=self.settings)
        self.poll_interval = poll_interval

        self._watched_paths: dict[Path, dict[Path, float]] = {}  # {watched_dir: {file_path: mtime}}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def add_watch_directory(self, directory: Path) -> None:
        """Add a directory to be watched if validated by PathGuard."""
        norm_dir = self.path_guard.validate_path(directory)
        if not norm_dir.is_dir():
            raise WatcherError(f"Cannot watch non-directory path: {directory}")

        with self._lock:
            # Snapshot initial directory contents
            initial_snapshot: dict[Path, float] = {}
            try:
                for f in norm_dir.rglob("*"):
                    if f.is_file():
                        try:
                            initial_snapshot[f] = f.stat().st_mtime
                        except Exception:
                            pass
            except Exception as err:
                logger.warning("Error taking initial snapshot of %s: %s", norm_dir, err)

            self._watched_paths[norm_dir] = initial_snapshot
            logger.info("Added watch directory: %s (%d files indexed)", norm_dir, len(initial_snapshot))

    def remove_watch_directory(self, directory: Path) -> None:
        with self._lock:
            norm_dir = directory.resolve()
            if norm_dir in self._watched_paths:
                del self._watched_paths[norm_dir]
                logger.info("Removed watch directory: %s", norm_dir)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="FileWatcherThread", daemon=True)
            self._thread.start()
            logger.info("FileWatcher started (poll_interval=%.1fs).", self.poll_interval)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("FileWatcher stopped.")

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as err:
                logger.exception("Error in FileWatcher poll: %s", err)
            self._stop_event.wait(self.poll_interval)

    def poll_once(self) -> list[Event]:
        """Perform a single directory scan diff and emit detected events."""
        events: list[Event] = []
        with self._lock:
            watched_dirs = list(self._watched_paths.keys())

        for watch_dir in watched_dirs:
            if not watch_dir.exists():
                continue

            current_files: dict[Path, float] = {}
            try:
                for f in watch_dir.rglob("*"):
                    if f.is_file():
                        try:
                            current_files[f] = f.stat().st_mtime
                        except Exception:
                            pass
            except Exception as err:
                logger.warning("Error scanning %s: %s", watch_dir, err)
                continue

            with self._lock:
                previous_files = self._watched_paths.get(watch_dir, {})

            # 1. Check for CREATED files
            for path, mtime in current_files.items():
                if path not in previous_files:
                    ev = Event(
                        event_type=EventType.FILE_CREATED,
                        origin=EventOrigin.WATCHER,
                        source="file_watcher",
                        payload={"path": str(path), "filename": path.name, "directory": str(watch_dir)},
                    )
                    events.append(ev)
                    self.event_sink(ev)
                elif mtime > previous_files[path] + 0.05:  # Modified
                    ev = Event(
                        event_type=EventType.FILE_MODIFIED,
                        origin=EventOrigin.WATCHER,
                        source="file_watcher",
                        payload={"path": str(path), "filename": path.name, "directory": str(watch_dir)},
                    )
                    events.append(ev)
                    self.event_sink(ev)

            # 2. Check for DELETED files
            for path in previous_files:
                if path not in current_files:
                    ev = Event(
                        event_type=EventType.FILE_DELETED,
                        origin=EventOrigin.WATCHER,
                        source="file_watcher",
                        payload={"path": str(path), "filename": path.name, "directory": str(watch_dir)},
                    )
                    events.append(ev)
                    self.event_sink(ev)

            with self._lock:
                self._watched_paths[watch_dir] = current_files

        return events


class SystemMonitor:
    """Local periodic sampler for CPU, RAM, and battery threshold events with hysteresis."""

    def __init__(
        self,
        event_sink: Callable[[Event], None],
        provider: Optional[SystemProvider] = None,
        poll_interval: float = 5.0,
        settings: Optional[Settings] = None,
    ) -> None:
        self.event_sink = event_sink
        self.provider = provider or SystemProvider()
        self.poll_interval = poll_interval
        self.settings = settings or get_settings()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Hysteresis state tracking: {metric_name: is_above_threshold}
        self._exceeded_states: dict[str, bool] = {}

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="SystemMonitorThread", daemon=True)
            self._thread.start()
            logger.info("SystemMonitor started (poll_interval=%.1fs).", self.poll_interval)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("SystemMonitor stopped.")

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            try:
                self.poll_metrics()
            except Exception as err:
                logger.warning("Error in SystemMonitor poll: %s", err)
            self._stop_event.wait(self.poll_interval)

    def poll_metrics(self) -> list[Event]:
        """Sample local system metrics and generate threshold events with hysteresis."""
        events: list[Event] = []
        try:
            cpu_val = self.provider.get_cpu_usage()
            cpu_pct = float(cpu_val.get("cpu_percent", cpu_val) if isinstance(cpu_val, dict) else cpu_val)

            ram_info = self.provider.get_memory_usage()
            ram_pct = float(ram_info.get("usage_percent", ram_info.get("virtual_memory_percent", 0.0)))

            batt_info = self.provider.get_battery_status()
            batt_pct = float(batt_info.get("percentage", batt_info.get("battery_percent", 100.0)))

            # 1. RAM check (Hysteresis threshold: 90%)
            self._check_metric("ram", ram_pct, threshold=90.0, is_lower_better=True, events=events)

            # 2. CPU check (Hysteresis threshold: 90%)
            self._check_metric("cpu", cpu_pct, threshold=90.0, is_lower_better=True, events=events)

            # 3. Battery check (Hysteresis threshold: 15%)
            if batt_info.get("present", False) and not batt_info.get("is_charging", True):
                self._check_metric("battery", batt_pct, threshold=15.0, is_lower_better=False, events=events)

        except Exception as err:
            logger.warning("Failed to collect system metrics: %s", err)

        return events


    def _check_metric(
        self,
        metric: str,
        value: float,
        threshold: float,
        is_lower_better: bool,
        events: list[Event],
    ) -> None:
        is_exceeded = (value >= threshold) if is_lower_better else (value <= threshold)
        prev_exceeded = self._exceeded_states.get(metric, False)

        if is_exceeded and not prev_exceeded:
            # Crossed into threshold -> fire event
            self._exceeded_states[metric] = True
            ev = Event(
                event_type=EventType.SYSTEM_THRESHOLD,
                origin=EventOrigin.WATCHER,
                source="system_monitor",
                payload={"metric": metric, "value": value, "threshold": threshold},
            )
            events.append(ev)
            self.event_sink(ev)
        elif not is_exceeded and prev_exceeded:
            # Dropped back below threshold -> reset hysteresis state
            self._exceeded_states[metric] = False


class ApplicationWatcher:
    """Monitors running process lifecycle for configured whitelisted applications."""

    def __init__(
        self,
        event_sink: Callable[[Event], None],
        provider: Optional[SystemProvider] = None,
        monitored_apps: Optional[Set[str]] = None,
        poll_interval: float = 3.0,
    ) -> None:
        self.event_sink = event_sink
        self.provider = provider or SystemProvider()
        self.monitored_apps = monitored_apps or {"code", "notepad", "chrome", "firefox", "calculator"}
        self.poll_interval = poll_interval

        self._active_pids: dict[str, Set[int]] = {app: set() for app in self.monitored_apps}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._snapshot_initial_processes()

    def _snapshot_initial_processes(self) -> None:
        """Capture active process PIDs on initialization without emitting events."""
        try:
            procs = []
            if hasattr(self.provider, "list_running_processes"):
                res = self.provider.list_running_processes(limit=500)
                if isinstance(res, list):
                    procs = res
            if not procs and hasattr(self.provider, "list_processes"):
                res = self.provider.list_processes(limit=500)
                if isinstance(res, list):
                    procs = res

            for p in procs:
                p_name = p.get("name", "").lower()
                pid = p.get("pid")
                if pid is None:
                    continue
                for app in self.monitored_apps:
                    if app in p_name:
                        self._active_pids[app].add(pid)
        except Exception as err:
            logger.warning("Error taking initial process snapshot in ApplicationWatcher: %s", err)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="AppWatcherThread", daemon=True)
            self._thread.start()
            logger.info("ApplicationWatcher started for %d apps.", len(self.monitored_apps))

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("ApplicationWatcher stopped.")

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            try:
                self.poll_processes()
            except Exception as err:
                logger.warning("Error in ApplicationWatcher poll: %s", err)
            self._stop_event.wait(self.poll_interval)

    def poll_processes(self) -> list[Event]:
        """Check active processes for configured applications."""
        events: list[Event] = []
        try:
            procs = []
            if hasattr(self.provider, "list_running_processes"):
                res = self.provider.list_running_processes(limit=500)
                if isinstance(res, list):
                    procs = res
            if not procs and hasattr(self.provider, "list_processes"):
                res = self.provider.list_processes(limit=500)
                if isinstance(res, list):
                    procs = res

            current_app_pids: dict[str, Set[int]] = {app: set() for app in self.monitored_apps}



            for p in procs:
                p_name = p.get("name", "").lower()
                pid = p.get("pid")
                if pid is None:
                    continue

                for app in self.monitored_apps:
                    if app in p_name:
                        current_app_pids[app].add(pid)

            for app, pids in current_app_pids.items():
                with self._lock:
                    prev_pids = self._active_pids.get(app, set())

                # Started
                started = pids - prev_pids
                for pid in started:
                    ev = Event(
                        event_type=EventType.PROCESS_STARTED,
                        origin=EventOrigin.WATCHER,
                        source="application_watcher",
                        payload={"application": app, "pid": pid},
                    )
                    events.append(ev)
                    self.event_sink(ev)

                # Stopped
                stopped = prev_pids - pids
                for pid in stopped:
                    ev = Event(
                        event_type=EventType.PROCESS_STOPPED,
                        origin=EventOrigin.WATCHER,
                        source="application_watcher",
                        payload={"application": app, "pid": pid},
                    )
                    events.append(ev)
                    self.event_sink(ev)

                with self._lock:
                    self._active_pids[app] = pids

        except Exception as err:
            logger.warning("Error scanning process table: %s", err)

        return events
