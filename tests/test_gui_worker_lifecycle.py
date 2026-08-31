"""Regression tests for AgentWorker lifecycle, signals, and cancellation."""

import time
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
import pytest
from app.agent.agent import Agent
from app.ui.worker import AgentWorker


def test_agent_worker_lifecycle(qapp: QApplication):
    """Verify AgentWorker starts, streams chunks, and emits finished signal."""
    agent = MagicMock(spec=Agent)
    agent.stream_run.return_value = ["Hello", " from", " worker"]

    worker = AgentWorker(agent=agent, prompt="hi", model="qwen3:30b")

    received_chunks = []
    finished_responses = []

    worker.chunk_received.connect(received_chunks.append)
    worker.finished.connect(finished_responses.append)

    worker.start()
    start_t = time.time()
    while worker.isRunning() and (time.time() - start_t) < 5.0:
        qapp.processEvents()
        time.sleep(0.01)

    worker.wait(1000)
    qapp.processEvents()

    assert "".join(received_chunks) == "Hello from worker"
    assert finished_responses == ["Hello from worker"]


def test_agent_worker_cancellation(qapp: QApplication):
    """Verify worker cancellation stops streaming loop cleanly."""
    def _slow_stream(*args, **kwargs):
        for i in range(100):
            time.sleep(0.02)
            yield f"chunk{i} "

    agent = MagicMock(spec=Agent)
    agent.stream_run.side_effect = _slow_stream

    worker = AgentWorker(agent=agent, prompt="hi")
    received_chunks = []

    def _on_chunk(chunk: str):
        received_chunks.append(chunk)
        if len(received_chunks) >= 2:
            worker.cancel()

    worker.chunk_received.connect(_on_chunk)
    worker.start()

    start_t = time.time()
    while worker.isRunning() and (time.time() - start_t) < 5.0:
        qapp.processEvents()
        time.sleep(0.01)

    worker.wait(1000)
    qapp.processEvents()

    assert worker.is_cancelled()
    assert len(received_chunks) <= 5
