"""Unit tests for GuiConfirmationProvider thread-safe confirmation flow."""

import os
import sys
import threading
from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import QCoreApplication, Qt

from app.security.permissions import ExecutionContext, PermissionDecision, SecurityDecision
from app.tools.base import RiskLevel
from app.ui.confirmation import GuiConfirmationProvider

# Ensure Qt offscreen for headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"


from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app



def test_gui_confirmation_provider_allow(qapp: QApplication) -> None:

    provider = GuiConfirmationProvider()

    ctx = ExecutionContext(
        tool_name="delete_file",
        risk_level=RiskLevel.HIGH,
        arguments={"path": "data/test.txt"},
    )
    decision = SecurityDecision(
        decision=PermissionDecision.CONFIRM,
        reason="HIGH risk file deletion requires user approval",
        tool_name=ctx.tool_name,
        risk_level=ctx.risk_level,
        request_id=ctx.request_id,
    )

    def handle_request(context: ExecutionContext, dec: SecurityDecision, event: threading.Event, holder: list[bool]) -> None:
        assert context.tool_name == "delete_file"
        assert dec.decision == PermissionDecision.CONFIRM
        holder[0] = True  # Simulate user clicking Allow
        event.set()

    provider.confirmation_requested.connect(handle_request, Qt.DirectConnection)

    # Invoke from background thread simulating Agent/Tool worker
    worker_result = [None]

    def worker_target() -> None:
        worker_result[0] = provider.request_confirmation(ctx, decision)

    t = threading.Thread(target=worker_target)
    t.start()
    t.join(timeout=3.0)

    assert worker_result[0] is True


def test_gui_confirmation_provider_deny(qapp: QApplication) -> None:
    provider = GuiConfirmationProvider()

    ctx = ExecutionContext(
        tool_name="run_python_file",
        risk_level=RiskLevel.HIGH,
        arguments={"path": "script.py"},
    )
    decision = SecurityDecision(
        decision=PermissionDecision.CONFIRM,
        reason="HIGH risk terminal execution requires user approval",
        tool_name=ctx.tool_name,
        risk_level=ctx.risk_level,
        request_id=ctx.request_id,
    )

    def handle_request(context: ExecutionContext, dec: SecurityDecision, event: threading.Event, holder: list[bool]) -> None:
        holder[0] = False  # Simulate user clicking Deny/Cancel
        event.set()

    provider.confirmation_requested.connect(handle_request, Qt.DirectConnection)

    worker_result = [None]

    def worker_target() -> None:
        worker_result[0] = provider.request_confirmation(ctx, decision)

    t = threading.Thread(target=worker_target)
    t.start()
    t.join(timeout=3.0)

    assert worker_result[0] is False
