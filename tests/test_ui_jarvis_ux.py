"""Unit and integration tests for Phase 20.5 Jarvis-class UI/UX and low-latency interaction design."""

import time
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QLabel
import pytest

from app.agent.agent import Agent
from app.ui.models import BackendStatus, ConversationItem, MessageRole, TurnMetrics
from app.ui.theme import APPLICATION_STYLESHEET, COLOR_ACCENT, COLOR_BG_DARK
from app.ui.widgets.input_bar import InputBar
from app.ui.widgets.message_bubble import MessageBubble
from app.ui.widgets.sidebar import ConversationSidebar
from app.ui.widgets.status_bar import SystemStatusBar
from app.ui.widgets.tool_activity import ToolActivityWidget
from app.ui.worker import AgentWorker
from datetime import datetime, timezone


def test_jarvis_theme_compilation():
    """Verify Jarvis application stylesheet contains essential dark and neon tokens."""
    assert COLOR_BG_DARK in APPLICATION_STYLESHEET
    assert COLOR_ACCENT in APPLICATION_STYLESHEET
    assert "primaryButton" in APPLICATION_STYLESHEET
    assert "chipButton" in APPLICATION_STYLESHEET


def test_message_bubble_jarvis_styling_and_telemetry(qapp: QApplication):
    """Verify MessageBubble renders role identity, copy action, and telemetry chip."""
    metrics = TurnMetrics(
        ttft=0.45,
        total_time=1.20,
        chunks_count=18,
        chars_count=95,
        tokens_per_second=24.0,
        model_name="qwen3:30b",
        role="standard",
    )

    bubble = MessageBubble(
        role=MessageRole.ASSISTANT,
        initial_content="Hello! How can I assist you with your project today?",
        metrics=metrics,
    )
    bubble.show()

    labels = [l.text() for l in bubble.findChildren(QLabel)]
    assert any(("PIXEL // ASSISTANT" in t or "JARVIS // ASSISTANT" in t) for t in labels)
    assert not bubble.telemetry_label.isHidden()
    assert "24.0 tok/s" in bubble.telemetry_label.text()
    assert "0.45s TTFT" in bubble.telemetry_label.text()
    assert "qwen3:30b [STANDARD]" in bubble.telemetry_label.text()

    # Test copy action
    bubble._copy_to_clipboard()
    clipboard = QApplication.clipboard()
    if clipboard:
        assert clipboard.text() == "Hello! How can I assist you with your project today?"


def test_input_bar_command_capsule_and_tier_cycling(qapp: QApplication):
    """Verify InputBar command capsule, tier selector cycling, and send submission."""
    input_bar = InputBar()
    emitted_tiers = []
    input_bar.tier_changed.connect(emitted_tiers.append)

    assert input_bar.tier_chip.text() == "⚡ Mode: Auto"

    # Cycle tier: Auto -> Fast -> Standard -> Heavy -> Auto
    input_bar._cycle_tier()
    assert input_bar.tier_chip.text() == "⚡ Mode: Fast"
    assert emitted_tiers[-1] == "fast"

    input_bar._cycle_tier()
    assert input_bar.tier_chip.text() == "⚡ Mode: Standard"
    assert emitted_tiers[-1] == "standard"

    # Test send submission
    emitted_prompts = []
    input_bar.send_submitted.connect(emitted_prompts.append)
    input_bar.text_input.setPlainText("Status report")
    input_bar._handle_send()

    assert emitted_prompts == ["Status report"]
    assert input_bar.text_input.toPlainText() == ""


def test_sidebar_telemetry_and_search_filter(qapp: QApplication):
    """Verify ConversationSidebar live search filtering and resource meter updates."""
    sidebar = ConversationSidebar()

    # Update resource meters
    sidebar.update_resource_meters(cpu_percent=35.5, ram_percent=62.0)
    assert sidebar.cpu_val_lbl.text() == "35.5%"
    assert sidebar.cpu_bar.value() == 35
    assert sidebar.ram_val_lbl.text() == "62.0%"
    assert sidebar.ram_bar.value() == 62

    # Populate conversations
    items = [
        ConversationItem(id="c1", title="Quantum Physics Research", updated_at=datetime.now(timezone.utc), message_count=5),
        ConversationItem(id="c2", title="Python Automation Script", updated_at=datetime.now(timezone.utc), message_count=2),
        ConversationItem(id="c3", title="System Maintenance Log", updated_at=datetime.now(timezone.utc), message_count=8),
    ]
    sidebar.update_conversations(items)
    assert sidebar.list_widget.count() == 3

    # Filter with search
    sidebar.search_input.setText("Python")
    assert sidebar.list_widget.count() == 1
    assert "Python Automation Script" in sidebar.list_widget.item(0).text()

    sidebar.search_input.setText("")
    assert sidebar.list_widget.count() == 3


def test_status_bar_hud_and_tier_pill(qapp: QApplication):
    """Verify SystemStatusBar tier pill updates and performance display."""
    status_bar = SystemStatusBar()

    status_bar.set_tier_badge("fast")
    assert status_bar.tier_badge.text() == "TIER: FAST"

    status_bar.set_tier_badge("heavy")
    assert status_bar.tier_badge.text() == "TIER: HEAVY"

    status_bar.set_performance_metric(model_name="qwen3:30b", latency_seconds=1.42, tok_per_sec=28.5)
    assert "28.5 t/s" in status_bar.perf_label.text()
    assert "1.42s" in status_bar.perf_label.text()


def test_agent_worker_turn_metrics_emission(qapp: QApplication):
    """Verify AgentWorker computes and emits TurnMetrics alongside response."""
    agent = MagicMock(spec=Agent)
    agent.stream_run.return_value = ["Instant", " Jarvis", " reply"]

    worker = AgentWorker(agent=agent, prompt="ping", model="qwen3:30b")

    received_metrics = []
    received_responses = []

    worker.metrics_ready.connect(received_metrics.append)
    worker.finished.connect(received_responses.append)

    worker.start()
    start_t = time.time()
    while worker.isRunning() and (time.time() - start_t) < 5.0:
        qapp.processEvents()
        time.sleep(0.01)

    worker.wait(1000)
    qapp.processEvents()

    assert len(received_responses) == 1
    assert received_responses[0] == "Instant Jarvis reply"
    assert len(received_metrics) == 1

    m = received_metrics[0]
    assert isinstance(m, TurnMetrics)
    assert m.chunks_count == 3
    assert m.chars_count == len("Instant Jarvis reply")
    assert m.total_time >= 0.0
