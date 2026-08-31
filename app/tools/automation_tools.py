"""Tools for managing background automation triggers, event history, and master automation mode."""

from typing import Any, Mapping, Optional
from pydantic import BaseModel, Field

from app.core.exceptions import ToolValidationError, TriggerError
from app.events.engine import EventEngine
from app.events.models import EventType, Trigger, TriggerActionType, TriggerStatus
from app.tools.base import RiskLevel, Tool, ToolResult


class BaseAutomationTool(Tool):
    """Base class for automation tools referencing the EventEngine."""

    def __init__(
        self,
        event_engine: EventEngine,
        name: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.READ,
        args_model: Optional[type[BaseModel]] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.event_engine = event_engine


class CreateTriggerArgs(BaseModel):
    name: str = Field(description="Descriptive name for the trigger rule")
    event_type: str = Field(
        description="Event category: 'file_created', 'file_modified', 'system_threshold', 'process_started', 'process_stopped'",
    )
    prompt: str = Field(description="Message or prompt to execute when trigger conditions match")
    file_pattern: Optional[str] = Field(
        default=None,
        description="Glob pattern for file events (e.g. '*.pdf', '*.txt')",
    )
    watch_directory: Optional[str] = Field(
        default=None,
        description="Target directory path for filesystem events",
    )
    system_metric: Optional[str] = Field(
        default=None,
        description="System metric for threshold events: 'ram', 'cpu', 'battery'",
    )
    threshold_value: Optional[float] = Field(
        default=None,
        description="Threshold percentage value (e.g. 90.0)",
    )
    application_name: Optional[str] = Field(
        default=None,
        description="Application name substring for process events (e.g. 'code', 'notepad')",
    )
    cooldown_seconds: int = Field(
        default=300,
        description="Cooldown period in seconds before the trigger can fire again",
    )


class CreateTriggerTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="create_trigger",
            description="Create a new real-time background event trigger (file watch, system threshold, or app lifecycle).",
            risk_level=RiskLevel.MEDIUM,
            args_model=CreateTriggerArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        name = args.get("name", "").strip()
        ev_type_str = args.get("event_type", "").strip().lower()
        prompt = args.get("prompt", "").strip()

        if not name:
            raise ToolValidationError("Trigger name cannot be empty")
        if not prompt:
            raise ToolValidationError("Trigger prompt/action content cannot be empty")

        try:
            ev_type = EventType(ev_type_str)
        except ValueError:
            raise ToolValidationError(f"Unsupported event_type '{ev_type_str}'")

        conditions: dict[str, Any] = {}
        if args.get("file_pattern"):
            conditions["pattern"] = args["file_pattern"]
        if args.get("watch_directory"):
            conditions["path"] = args["watch_directory"]
        if args.get("system_metric"):
            conditions["metric"] = args["system_metric"]
            conditions["operator"] = ">="
            conditions["value"] = args.get("threshold_value", 90.0)
        if args.get("application_name"):
            conditions["application"] = args["application_name"]

        cooldown = int(args.get("cooldown_seconds", 300))

        trigger = Trigger(
            name=name,
            event_type=ev_type,
            conditions=conditions,
            action_type=TriggerActionType.NOTIFY_USER,
            action_payload={"prompt": prompt},
            status=TriggerStatus.ACTIVE,
            cooldown_seconds=cooldown,
        )

        created = self.event_engine.repository.create_trigger(trigger)
        return ToolResult(
            success=True,
            data={
                "trigger_id": created.trigger_id,
                "name": created.name,
                "event_type": created.event_type.value,
                "status": created.status.value,
                "cooldown_seconds": created.cooldown_seconds,
                "message": f"Successfully created background trigger '{created.name}'",
            },
        )


class ListTriggersTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="list_triggers",
            description="List all configured background event automation triggers.",
            risk_level=RiskLevel.READ,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        triggers = self.event_engine.repository.list_triggers()
        return ToolResult(
            success=True,
            data={
                "count": len(triggers),
                "automation_enabled": self.event_engine.automation_enabled,
                "triggers": [
                    {
                        "id": t.trigger_id,
                        "name": t.name,
                        "event_type": t.event_type.value,
                        "status": t.status.value,
                        "conditions": t.conditions,
                        "trigger_count": t.trigger_count,
                        "last_triggered_at": t.last_triggered_at.isoformat() if t.last_triggered_at else None,
                    }
                    for t in triggers
                ],
            },
        )


class TriggerIdArgs(BaseModel):
    trigger_id: str = Field(description="Unique UUID identifier of the trigger")


class PauseTriggerTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="pause_trigger",
            description="Pause an active background trigger.",
            risk_level=RiskLevel.MEDIUM,
            args_model=TriggerIdArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        tid = args.get("trigger_id", "").strip()
        trigger = self.event_engine.repository.get_trigger(tid)
        if not trigger:
            return ToolResult(success=False, error=f"Trigger '{tid}' not found")

        trigger.status = TriggerStatus.PAUSED
        self.event_engine.repository.update_trigger(trigger)
        return ToolResult(success=True, data={"trigger_id": tid, "status": "paused", "message": f"Trigger '{trigger.name}' paused."})


class ResumeTriggerTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="resume_trigger",
            description="Resume a paused background trigger.",
            risk_level=RiskLevel.MEDIUM,
            args_model=TriggerIdArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        tid = args.get("trigger_id", "").strip()
        trigger = self.event_engine.repository.get_trigger(tid)
        if not trigger:
            return ToolResult(success=False, error=f"Trigger '{tid}' not found")

        trigger.status = TriggerStatus.ACTIVE
        self.event_engine.repository.update_trigger(trigger)
        return ToolResult(success=True, data={"trigger_id": tid, "status": "active", "message": f"Trigger '{trigger.name}' resumed."})


class DeleteTriggerTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="delete_trigger",
            description="Permanently delete a background automation trigger.",
            risk_level=RiskLevel.MEDIUM,
            args_model=TriggerIdArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        tid = args.get("trigger_id", "").strip()
        deleted = self.event_engine.repository.delete_trigger(tid)
        return ToolResult(
            success=deleted,
            data={"trigger_id": tid, "deleted": deleted, "message": "Trigger deleted." if deleted else "Trigger not found."},
        )


class GetEventHistoryArgs(BaseModel):
    limit: int = Field(default=20, description="Maximum number of recent events to retrieve")


class GetEventHistoryTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="get_event_history",
            description="View recent audit records of processed background watcher and scheduler events.",
            risk_level=RiskLevel.READ,
            args_model=GetEventHistoryArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        limit = int(args.get("limit", 20))
        records = self.event_engine.repository.get_recent_events(limit=limit)
        return ToolResult(
            success=True,
            data={
                "count": len(records),
                "events": [
                    {
                        "id": r.record_id,
                        "type": r.event_type.value,
                        "source": r.source,
                        "timestamp": r.timestamp.isoformat(),
                        "summary": r.summary,
                        "matched_triggers": r.matched_triggers,
                    }
                    for r in records
                ],
            },
        )


class SetAutomationModeArgs(BaseModel):
    enabled: bool = Field(description="True to enable master automation, False to pause all background triggers")


class SetAutomationModeTool(BaseAutomationTool):
    def __init__(self, event_engine: EventEngine) -> None:
        super().__init__(
            event_engine=event_engine,
            name="set_automation_mode",
            description="Toggle the master background automation switch (pause or resume all event watchers).",
            risk_level=RiskLevel.MEDIUM,
            args_model=SetAutomationModeArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        enabled = bool(args.get("enabled", True))
        self.event_engine.set_automation_enabled(enabled)
        return ToolResult(
            success=True,
            data={
                "automation_enabled": self.event_engine.automation_enabled,
                "message": f"Automation mode set to {'ACTIVE' if enabled else 'PAUSED'}.",
            },
        )
