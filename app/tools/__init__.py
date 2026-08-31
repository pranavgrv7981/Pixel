"""Extensible tool registry and execution engine."""

from app.tools.applications import (
    ApplicationDefinition,
    ApplicationRegistry,
    CloseApplicationTool,
    IsApplicationRunningTool,
    OpenApplicationTool,
)
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.demo import DemoMediumRiskTool, GetCurrentTimeTool, SafeCalculateTool
from app.tools.filesystem import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteDirectoryTool,
    DeleteFileTool,
    FileSystemTool,
    GetFileInfoTool,
    ListDirectoryTool,
    MoveFileTool,
    ReadTextFileTool,
    RenameFileTool,
    SearchFilesTool,
    WriteTextFileTool,
)
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry
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
from app.tools.terminal import (
    CompileCProgramTool,
    GitDiffTool,
    GitStatusTool,
    RunCProgramTool,
    RunPytestTool,
    RunPythonFileTool,
    TerminalTool,
)
from app.tools.memory import (
    ForgetMemoryTool,
    MemoryTool,
    RecallMemoryTool,
    RememberMemoryTool,
)
from app.tools.knowledge import (
    BaseKnowledgeTool,
    IndexDirectoryTool,
    IndexDocumentTool,
    ListIndexedDocumentsTool,
    RemoveDocumentTool,
    SearchKnowledgeTool,
)
from app.tools.browser import (
    BaseBrowserTool,
    BrowserBackTool,
    BrowserClickTool,
    BrowserCloseTool,
    BrowserCurrentPageTool,
    BrowserForwardTool,
    BrowserGetPageTool,
    BrowserOpenTool,
    BrowserScrollTool,
    BrowserSearchTool,
    BrowserTypeTool,
)
from app.tools.task_tools import (
    BaseTaskTool,
    CancelTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetTaskExecutionsTool,
    GetTaskTool,
    ListTasksTool,
    PauseTaskTool,
    ResumeTaskTool,
    RunTaskNowTool,
)




__all__ = [
    # Core
    "RiskLevel",
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "PathGuard",
    "GetCurrentTimeTool",
    "SafeCalculateTool",
    "DemoMediumRiskTool",
    # Filesystem tools
    "FileSystemTool",
    "ListDirectoryTool",
    "GetFileInfoTool",
    "SearchFilesTool",
    "ReadTextFileTool",
    "CreateDirectoryTool",
    "CreateFileTool",
    "WriteTextFileTool",
    "CopyFileTool",
    "MoveFileTool",
    "RenameFileTool",
    "DeleteFileTool",
    "DeleteDirectoryTool",
    # System tools
    "SystemProvider",
    "GetSystemInfoTool",
    "GetCpuUsageTool",
    "GetMemoryUsageTool",
    "GetBatteryStatusTool",
    "GetUptimeTool",
    "ListRunningProcessesTool",
    "GetProcessInfoTool",
    # Application tools
    "ApplicationDefinition",
    "ApplicationRegistry",
    "OpenApplicationTool",
    "CloseApplicationTool",
    "IsApplicationRunningTool",
    # Terminal tools
    "TerminalTool",
    "GitStatusTool",
    "GitDiffTool",
    "CompileCProgramTool",
    "RunPythonFileTool",
    "RunPytestTool",
    "RunCProgramTool",
    # Memory tools
    "MemoryTool",
    "RememberMemoryTool",
    "RecallMemoryTool",
    "ForgetMemoryTool",
    # Knowledge / RAG tools
    "BaseKnowledgeTool",
    "SearchKnowledgeTool",
    "ListIndexedDocumentsTool",
    "IndexDocumentTool",
    "IndexDirectoryTool",
    "RemoveDocumentTool",
    # Browser tools
    "BaseBrowserTool",
    "BrowserOpenTool",
    "BrowserSearchTool",
    "BrowserGetPageTool",
    "BrowserCurrentPageTool",
    "BrowserClickTool",
    "BrowserTypeTool",
    "BrowserScrollTool",
    "BrowserBackTool",
    "BrowserForwardTool",
    "BrowserCloseTool",
    # Task tools (Phase 14)
    "BaseTaskTool",
    "CreateTaskTool",
    "ListTasksTool",
    "GetTaskTool",
    "PauseTaskTool",
    "ResumeTaskTool",
    "CancelTaskTool",
    "DeleteTaskTool",
    "RunTaskNowTool",
    "GetTaskExecutionsTool",
    # Automation & Trigger tools (Phase 14)
    "BaseAutomationTool",
    "CreateTriggerTool",
    "ListTriggersTool",
    "PauseTriggerTool",
    "ResumeTriggerTool",
    "DeleteTriggerTool",
    "GetEventHistoryTool",
    "SetAutomationModeTool",
    # Planning tools (Phase 15)
    "CreatePlanTool",
    "GetPlanStatusTool",
    "ListPlansTool",
    "CancelPlanTool",
]
from app.tools.planning import CancelPlanTool, CreatePlanTool, GetPlanStatusTool, ListPlansTool


