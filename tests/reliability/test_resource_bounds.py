"""Reliability tests for input/output resource bounds and concurrency caps."""

import pytest
from app.core.config import Settings
from app.core.exceptions import InvalidMessageError, ToolValidationError
from app.agent.agent import Agent
from app.tools.filesystem import CreateFileTool
from app.tools.registry import ToolRegistry


def test_empty_prompt_rejected() -> None:
    agent = Agent(settings=Settings())
    with pytest.raises(InvalidMessageError):
        agent.run("")
    with pytest.raises(InvalidMessageError):
        agent.run("   ")


def test_oversized_file_write_rejected() -> None:
    settings = Settings(max_file_write_bytes=1000)
    tool = CreateFileTool(settings=settings)
    giant_content = "A" * 5000

    res = tool.execute({"path": "data/giant.txt", "content": giant_content})
    assert res.success is False
    assert "exceeds limit" in res.error.lower()
