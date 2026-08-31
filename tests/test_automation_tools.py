"""Unit tests for Automation and Task management tools."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.events.database import EventDatabase
from app.events.engine import EventEngine
from app.events.repository import EventRepository
from app.tasks.database import TaskDatabase
from app.tasks.manager import TaskManager
from app.tasks.repository import TaskRepository
from app.tools.automation_tools import (
    CreateTriggerTool,
    DeleteTriggerTool,
    GetEventHistoryTool,
    ListTriggersTool,
    PauseTriggerTool,
    ResumeTriggerTool,
    SetAutomationModeTool,
)
from app.tools.task_tools import (
    CancelTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetTaskTool,
    ListTasksTool,
    PauseTaskTool,
    ResumeTaskTool,
    RunTaskNowTool,
)


from app.tools.path_guard import PathGuard


@pytest.fixture
def automation_tools(tmp_path: Path):
    db = EventDatabase(db_path=tmp_path / "tools_event.db")
    repo = EventRepository(db=db)
    guard = PathGuard(allowed_roots=[tmp_path])
    engine = EventEngine(repository=repo, path_guard=guard)
    return {
        "create": CreateTriggerTool(event_engine=engine),
        "list": ListTriggersTool(event_engine=engine),
        "pause": PauseTriggerTool(event_engine=engine),
        "resume": ResumeTriggerTool(event_engine=engine),
        "delete": DeleteTriggerTool(event_engine=engine),
        "history": GetEventHistoryTool(event_engine=engine),
        "mode": SetAutomationModeTool(event_engine=engine),
        "engine": engine,
    }



@pytest.fixture
def task_tools(tmp_path: Path):
    db = TaskDatabase(db_path=tmp_path / "tools_task.db")
    repo = TaskRepository(db=db)
    mgr = TaskManager(repository=repo, settings=Settings(tasks_enabled=False))
    return {
        "create": CreateTaskTool(task_manager=mgr),
        "list": ListTasksTool(task_manager=mgr),
        "get": GetTaskTool(task_manager=mgr),
        "pause": PauseTaskTool(task_manager=mgr),
        "resume": ResumeTaskTool(task_manager=mgr),
        "cancel": CancelTaskTool(task_manager=mgr),
        "delete": DeleteTaskTool(task_manager=mgr),
        "run_now": RunTaskNowTool(task_manager=mgr),
        "manager": mgr,
    }


def test_create_and_list_triggers(automation_tools) -> None:
    create_tool = automation_tools["create"]
    list_tool = automation_tools["list"]

    res = create_tool.execute({
        "name": "Auto PDF Watcher",
        "event_type": "file_created",
        "prompt": "New PDF created",
        "file_pattern": "*.pdf",
    })
    assert res.success is True
    tid = res.data["trigger_id"]

    list_res = list_tool.execute({})
    assert list_res.success is True
    assert list_res.data["count"] == 1


def test_set_automation_mode_tool(automation_tools) -> None:
    mode_tool = automation_tools["mode"]
    res = mode_tool.execute({"enabled": False})
    assert res.success is True
    assert res.data["automation_enabled"] is False
    assert automation_tools["engine"].automation_enabled is False


def test_create_and_run_task_tool(task_tools) -> None:
    create_tool = task_tools["create"]
    list_tool = task_tools["list"]
    run_tool = task_tools["run_now"]

    res = create_tool.execute({
        "title": "Study AFL Task",
        "task_type": "one_time",
        "prompt": "Study AFL chapter 4",
        "time_expression": "in 10 minutes",
    })
    assert res.success is True
    tid = res.data["task_id"]

    run_res = run_tool.execute({"task_id": tid})
    assert run_res.success is True
    assert "Study AFL" in run_res.data["result_summary"]
