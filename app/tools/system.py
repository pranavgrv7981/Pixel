"""Safe system-information tools for hardware and process inspection."""

from datetime import timedelta
import os
import platform
import sys
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.tools.base import RiskLevel, Tool, ToolResult

logger = get_logger("tools.system")


# --- Platform Provider Layer ---

class SystemProvider:
    """Provides low-level system metrics using standard-library ctypes on Windows."""

    def __init__(self) -> None:
        self.is_windows = sys.platform == "win32"
        self._kernel32 = None
        if self.is_windows:
            try:
                import ctypes
                self._kernel32 = ctypes.windll.kernel32
            except Exception as err:
                logger.warning("Failed to initialize kernel32 ctypes: %s", err)

    def get_system_info(self) -> dict[str, Any]:
        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "hostname": platform.node(),
            "python_version": platform.python_version(),
        }

    def get_cpu_usage(self, sampling_interval: float = 0.2) -> float:
        if not self.is_windows or not self._kernel32:
            return 0.0

        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        def ft_to_int(ft: FILETIME) -> int:
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        idle1, kern1, user1 = FILETIME(), FILETIME(), FILETIME()
        self._kernel32.GetSystemTimes(ctypes.byref(idle1), ctypes.byref(kern1), ctypes.byref(user1))

        time.sleep(max(0.05, min(sampling_interval, 1.0)))

        idle2, kern2, user2 = FILETIME(), FILETIME(), FILETIME()
        self._kernel32.GetSystemTimes(ctypes.byref(idle2), ctypes.byref(kern2), ctypes.byref(user2))

        idle_delta = ft_to_int(idle2) - ft_to_int(idle1)
        kern_delta = ft_to_int(kern2) - ft_to_int(kern1)
        user_delta = ft_to_int(user2) - ft_to_int(user1)
        total_delta = kern_delta + user_delta

        if total_delta <= 0:
            return 0.0

        usage = (1.0 - (idle_delta / total_delta)) * 100.0
        return round(max(0.0, min(100.0, usage)), 1)

    def get_memory_usage(self) -> dict[str, Any]:
        if not self.is_windows or not self._kernel32:
            return {
                "total_bytes": 0,
                "available_bytes": 0,
                "used_bytes": 0,
                "usage_percent": 0.0,
            }

        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        self._kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

        total = stat.ullTotalPhys
        avail = stat.ullAvailPhys
        used = total - avail
        percent = float(stat.dwMemoryLoad)

        return {
            "total_bytes": total,
            "available_bytes": avail,
            "used_bytes": used,
            "usage_percent": percent,
            "total_gb": round(total / (1024**3), 2),
            "available_gb": round(avail / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
        }

    def get_battery_status(self) -> dict[str, Any]:
        if not self.is_windows or not self._kernel32:
            return {"present": False, "status": "Unsupported platform"}

        import ctypes
        from ctypes import wintypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", wintypes.BYTE),
                ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE),
                ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        pwr = SYSTEM_POWER_STATUS()
        if not self._kernel32.GetSystemPowerStatus(ctypes.byref(pwr)):
            return {"present": False, "status": "Failed to read power status"}

        # BatteryFlag 128 = No system battery, 255 = Unknown
        if pwr.BatteryFlag == 128 or pwr.BatteryLifePercent == 255:
            return {
                "present": False,
                "power_source": "AC Power" if pwr.ACLineStatus == 1 else "Unknown",
            }

        percent = int(pwr.BatteryLifePercent)
        is_charging = bool(pwr.BatteryFlag & 8) or (pwr.ACLineStatus == 1 and percent < 100)

        return {
            "present": True,
            "percentage": percent,
            "is_charging": is_charging,
            "power_source": "AC Power" if pwr.ACLineStatus == 1 else "Battery",
        }

    def get_uptime_seconds(self) -> float:
        if not self.is_windows or not self._kernel32:
            return 0.0
        ms = self._kernel32.GetTickCount64()
        return round(ms / 1000.0, 1)

    def list_processes(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.is_windows or not self._kernel32:
            return []

        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        h_snap = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snap == -1:
            return []

        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

        processes: list[dict[str, Any]] = []
        try:
            if self._kernel32.Process32First(h_snap, ctypes.byref(pe)):
                while True:
                    pid = pe.th32ProcessID
                    exe_name = pe.szExeFile.decode("mbcs", errors="replace")
                    processes.append({
                        "pid": pid,
                        "name": exe_name,
                        "parent_pid": pe.th32ParentProcessID,
                        "threads": pe.cntThreads,
                    })
                    if not self._kernel32.Process32Next(h_snap, ctypes.byref(pe)):
                        break
        finally:
            self._kernel32.CloseHandle(h_snap)

        # Deterministic sorting by name, then PID
        processes.sort(key=lambda p: (p["name"].lower(), p["pid"]))
        return processes[:limit]

    def get_process_info(self, pid: int) -> Optional[dict[str, Any]]:
        procs = self.list_processes(limit=10000)
        for p in procs:
            if p["pid"] == pid:
                return p
        return None


# --- Parameter Schemas ---

class EmptyArgs(BaseModel):
    pass


class GetCpuUsageArgs(BaseModel):
    sampling_interval: Optional[float] = Field(
        default=0.2,
        description="Sampling window in seconds to calculate CPU utilization (between 0.1 and 1.0)",
    )


class ListProcessesArgs(BaseModel):
    limit: Optional[int] = Field(
        default=None,
        description="Maximum number of running processes to return (default capped by system settings)",
    )


class GetProcessInfoArgs(BaseModel):
    pid: int = Field(description="Process Identifier (PID) to inspect")


# --- System Tools ---

class GetSystemInfoTool(Tool):
    """Retrieves basic operating system and platform metadata."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_system_info",
            description="Retrieve basic host operating system, architecture, and platform information.",
            risk_level=RiskLevel.READ,
            args_model=EmptyArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        try:
            info = self.provider.get_system_info()
            return ToolResult(
                success=True,
                data=info,
                message=f"Host system: {info['os']} {info['os_release']} ({info['architecture']})",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to retrieve system info: {err}")


class GetCpuUsageTool(Tool):
    """Measures current CPU utilization over a bounded sampling interval."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_cpu_usage",
            description="Measure current overall CPU utilization percentage.",
            risk_level=RiskLevel.READ,
            args_model=GetCpuUsageArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        interval = args.get("sampling_interval") or 0.2
        try:
            usage = self.provider.get_cpu_usage(sampling_interval=interval)
            return ToolResult(
                success=True,
                data={"cpu_percent": usage, "sampling_interval_seconds": interval},
                message=f"Current CPU utilization is {usage}%.",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to measure CPU usage: {err}")


class GetMemoryUsageTool(Tool):
    """Retrieves total, available, and percentage RAM usage."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_memory_usage",
            description="Retrieve physical RAM utilization and availability.",
            risk_level=RiskLevel.READ,
            args_model=EmptyArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        try:
            mem = self.provider.get_memory_usage()
            return ToolResult(
                success=True,
                data=mem,
                message=f"RAM Usage: {mem['usage_percent']}% (Used: {mem.get('used_gb', 0)} GB / {mem.get('total_gb', 0)} GB).",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to read memory usage: {err}")


class GetBatteryStatusTool(Tool):
    """Retrieves battery charge percentage and AC connection status."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_battery_status",
            description="Retrieve battery charge percentage and charging status.",
            risk_level=RiskLevel.READ,
            args_model=EmptyArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        try:
            battery = self.provider.get_battery_status()
            if not battery.get("present", False):
                return ToolResult(
                    success=True,
                    data=battery,
                    message="No system battery detected (running on AC power/desktop).",
                )

            pct = battery.get("percentage", 0)
            charging_str = "charging" if battery.get("is_charging") else "discharging"
            return ToolResult(
                success=True,
                data=battery,
                message=f"Battery is at {pct}% ({charging_str}).",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to check battery status: {err}")


class GetUptimeTool(Tool):
    """Retrieves system uptime in seconds and human-readable format."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_uptime",
            description="Retrieve system uptime since last boot.",
            risk_level=RiskLevel.READ,
            args_model=EmptyArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        try:
            seconds = self.provider.get_uptime_seconds()
            formatted = str(timedelta(seconds=int(seconds)))
            return ToolResult(
                success=True,
                data={"uptime_seconds": seconds, "uptime_formatted": formatted},
                message=f"System uptime: {formatted} ({seconds:.1f} seconds).",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to retrieve uptime: {err}")


class ListRunningProcessesTool(Tool):
    """Lists currently running processes bounded by max results limit."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="list_running_processes",
            description="List currently active processes (PID and executable name) up to a bounded limit.",
            risk_level=RiskLevel.READ,
            args_model=ListProcessesArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        limit = args.get("limit") or self.settings.max_process_results
        try:
            procs = self.provider.list_processes(limit=limit)
            return ToolResult(
                success=True,
                data={"total_returned": len(procs), "processes": procs},
                message=f"Listed {len(procs)} active processes.",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to list processes: {err}")


class GetProcessInfoTool(Tool):
    """Inspects metadata for a specific process PID."""

    def __init__(
        self,
        provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="get_process_info",
            description="Retrieve basic process information for a specific PID.",
            risk_level=RiskLevel.READ,
            args_model=GetProcessInfoArgs,
        )
        self.provider = provider or SystemProvider()
        self.settings = settings or get_settings()

    def _run(self, args: dict[str, Any]) -> ToolResult:
        pid = args["pid"]
        if pid < 0:
            return ToolResult(success=False, error=f"Invalid PID '{pid}': PID must be non-negative")

        try:
            info = self.provider.get_process_info(pid)
            if not info:
                return ToolResult(success=False, error=f"Process with PID {pid} not found or terminated")

            return ToolResult(
                success=True,
                data=info,
                message=f"Process {pid} ('{info['name']}') is running with {info.get('threads', 1)} threads.",
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to inspect PID {pid}: {err}")
