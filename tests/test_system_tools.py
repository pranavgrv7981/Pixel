"""Tests for Phase 6 system information tools in app/tools/system.py."""

from unittest.mock import MagicMock
import pytest

from app.tools.system import (
    GetBatteryStatusTool,
    GetCpuUsageTool,
    GetMemoryUsageTool,
    GetProcessInfoTool,
    GetSystemInfoTool,
    GetUptimeTool,
    ListRunningProcessesTool,
    SystemProvider,
)


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock(spec=SystemProvider)
    provider.get_system_info.return_value = {
        "os": "Windows",
        "os_release": "11",
        "os_version": "10.0.22631",
        "architecture": "AMD64",
        "processor": "Intel64 Family 6 Model 158",
        "hostname": "TEST-PC",
        "python_version": "3.14.0",
    }
    provider.get_cpu_usage.return_value = 14.5
    provider.get_memory_usage.return_value = {
        "total_bytes": 17179869184,
        "available_bytes": 8589934592,
        "used_bytes": 8589934592,
        "usage_percent": 50.0,
        "total_gb": 16.0,
        "available_gb": 8.0,
        "used_gb": 8.0,
    }
    provider.get_battery_status.return_value = {
        "present": True,
        "percentage": 85,
        "is_charging": True,
        "power_source": "AC Power",
    }
    provider.get_uptime_seconds.return_value = 3661.0
    provider.list_processes.return_value = [
        {"pid": 100, "name": "explorer.exe", "parent_pid": 4, "threads": 12},
        {"pid": 200, "name": "notepad.exe", "parent_pid": 100, "threads": 4},
    ]
    provider.get_process_info.side_effect = lambda pid: (
        {"pid": pid, "name": "notepad.exe", "parent_pid": 100, "threads": 4}
        if pid == 200
        else None
    )
    return provider


def test_get_system_info_tool(mock_provider: MagicMock) -> None:
    tool = GetSystemInfoTool(provider=mock_provider)
    res = tool.execute({})
    assert res.success is True
    assert res.data["os"] == "Windows"
    assert res.data["architecture"] == "AMD64"
    assert "Host system: Windows" in res.message


def test_get_cpu_usage_tool(mock_provider: MagicMock) -> None:
    tool = GetCpuUsageTool(provider=mock_provider)
    res = tool.execute({"sampling_interval": 0.3})
    assert res.success is True
    assert res.data["cpu_percent"] == 14.5
    assert mock_provider.get_cpu_usage.called


def test_get_memory_usage_tool(mock_provider: MagicMock) -> None:
    tool = GetMemoryUsageTool(provider=mock_provider)
    res = tool.execute({})
    assert res.success is True
    assert res.data["usage_percent"] == 50.0
    assert res.data["total_gb"] == 16.0


def test_get_battery_status_tool_present(mock_provider: MagicMock) -> None:
    tool = GetBatteryStatusTool(provider=mock_provider)
    res = tool.execute({})
    assert res.success is True
    assert res.data["present"] is True
    assert res.data["percentage"] == 85
    assert "85%" in res.message


def test_get_battery_status_tool_absent(mock_provider: MagicMock) -> None:
    mock_provider.get_battery_status.return_value = {
        "present": False,
        "power_source": "AC Power",
    }
    tool = GetBatteryStatusTool(provider=mock_provider)
    res = tool.execute({})
    assert res.success is True
    assert res.data["present"] is False
    assert "No system battery detected" in res.message


def test_get_uptime_tool(mock_provider: MagicMock) -> None:
    tool = GetUptimeTool(provider=mock_provider)
    res = tool.execute({})
    assert res.success is True
    assert res.data["uptime_seconds"] == 3661.0
    assert "1:01:01" in res.data["uptime_formatted"]


def test_list_running_processes_tool(mock_provider: MagicMock) -> None:
    tool = ListRunningProcessesTool(provider=mock_provider)
    res = tool.execute({"limit": 10})
    assert res.success is True
    assert res.data["total_returned"] == 2
    assert res.data["processes"][0]["name"] == "explorer.exe"


def test_get_process_info_valid_pid(mock_provider: MagicMock) -> None:
    tool = GetProcessInfoTool(provider=mock_provider)
    res = tool.execute({"pid": 200})
    assert res.success is True
    assert res.data["name"] == "notepad.exe"
    assert res.data["threads"] == 4


def test_get_process_info_nonexistent_pid(mock_provider: MagicMock) -> None:
    tool = GetProcessInfoTool(provider=mock_provider)
    res = tool.execute({"pid": 99999})
    assert res.success is False
    assert "not found or terminated" in res.error


def test_get_process_info_invalid_negative_pid(mock_provider: MagicMock) -> None:
    tool = GetProcessInfoTool(provider=mock_provider)
    res = tool.execute({"pid": -5})
    assert res.success is False
    assert "must be non-negative" in res.error
