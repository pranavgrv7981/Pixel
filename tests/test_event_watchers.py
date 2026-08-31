"""Unit tests for local FileWatcher, SystemMonitor, and ApplicationWatcher."""

from pathlib import Path
import time
from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.core.exceptions import PermissionDeniedError, WatcherError
from app.events.models import Event, EventType
from app.events.watchers import ApplicationWatcher, FileWatcher, SystemMonitor
from app.tools.path_guard import PathGuard


def test_file_watcher_detects_creation_and_deletion(tmp_path: Path) -> None:
    events_received: list[Event] = []
    watch_dir = tmp_path / "watch_target"
    watch_dir.mkdir()

    guard = PathGuard(allowed_roots=[tmp_path])
    cfg = Settings()

    watcher = FileWatcher(
        event_sink=lambda e: events_received.append(e),
        path_guard=guard,
        poll_interval=0.1,
        settings=cfg,
    )
    watcher.add_watch_directory(watch_dir)

    # 1. Initially empty
    polled = watcher.poll_once()
    assert len(polled) == 0

    # 2. Create a file
    test_file = watch_dir / "sample.txt"
    test_file.write_text("hello world")

    polled = watcher.poll_once()
    assert len(polled) == 1
    assert polled[0].event_type == EventType.FILE_CREATED
    assert polled[0].payload["filename"] == "sample.txt"

    # 3. Delete the file
    test_file.unlink()
    polled = watcher.poll_once()
    assert len(polled) == 1
    assert polled[0].event_type == EventType.FILE_DELETED


def test_file_watcher_rejects_disallowed_root(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    guard = PathGuard(allowed_roots=[allowed_dir])
    cfg = Settings()

    watcher = FileWatcher(
        event_sink=lambda e: None,
        path_guard=guard,
        settings=cfg,
    )

    with pytest.raises(Exception):
        watcher.add_watch_directory(outside_dir)



def test_system_monitor_threshold_and_hysteresis() -> None:
    events: list[Event] = []
    mock_provider = MagicMock()

    # Initial normal metrics
    mock_provider.get_cpu_usage.return_value = {"cpu_percent": 30.0}
    mock_provider.get_memory_usage.return_value = {"virtual_memory_percent": 65.0}
    mock_provider.get_battery_status.return_value = {"battery_percent": 80.0, "power_plugged": True}

    monitor = SystemMonitor(
        event_sink=lambda e: events.append(e),
        provider=mock_provider,
        poll_interval=0.1,
    )

    # 1. Normal poll -> no events
    evs = monitor.poll_metrics()
    assert len(evs) == 0

    # 2. RAM jumps to 94% -> fires SYSTEM_THRESHOLD
    mock_provider.get_memory_usage.return_value = {"virtual_memory_percent": 94.0}
    evs = monitor.poll_metrics()
    assert len(evs) == 1
    assert evs[0].event_type == EventType.SYSTEM_THRESHOLD
    assert evs[0].payload["metric"] == "ram"
    assert evs[0].payload["value"] == 94.0

    # 3. Second poll while still at 94% -> hysteresis blocks duplicate trigger!
    evs = monitor.poll_metrics()
    assert len(evs) == 0

    # 4. Drops to 70% -> resets hysteresis state
    mock_provider.get_memory_usage.return_value = {"virtual_memory_percent": 70.0}
    evs = monitor.poll_metrics()
    assert len(evs) == 0

    # 5. Jumps again to 92% -> fires new event
    mock_provider.get_memory_usage.return_value = {"virtual_memory_percent": 92.0}
    evs = monitor.poll_metrics()
    assert len(evs) == 1


def test_application_watcher_start_stop() -> None:
    events: list[Event] = []
    mock_provider = MagicMock()

    # Initially notepad not running
    mock_provider.list_running_processes.return_value = [
        {"name": "explorer.exe", "pid": 100},
    ]

    app_watcher = ApplicationWatcher(
        event_sink=lambda e: events.append(e),
        provider=mock_provider,
        monitored_apps={"notepad"},
        poll_interval=0.1,
    )

    evs = app_watcher.poll_processes()
    assert len(evs) == 0

    # Notepad starts
    mock_provider.list_running_processes.return_value = [
        {"name": "explorer.exe", "pid": 100},
        {"name": "notepad.exe", "pid": 555},
    ]
    evs = app_watcher.poll_processes()
    assert len(evs) == 1
    assert evs[0].event_type == EventType.PROCESS_STARTED
    assert evs[0].payload["application"] == "notepad"
    assert evs[0].payload["pid"] == 555

    # Notepad stops
    mock_provider.list_running_processes.return_value = [
        {"name": "explorer.exe", "pid": 100},
    ]
    evs = app_watcher.poll_processes()
    assert len(evs) == 1
    assert evs[0].event_type == EventType.PROCESS_STOPPED
    assert evs[0].payload["application"] == "notepad"
