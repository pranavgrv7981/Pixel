"""Tests for main.py entry point and CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.ollama_client import ModelStatus, OllamaClient, OllamaStatus, ServerStatus
from main import main, print_status_banner, run_single_chat, run_system_check


@pytest.fixture(autouse=True)
def isolate_main_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure all tests in test_main use isolated temporary data and log directories."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))


@pytest.fixture
def mock_healthy_client() -> MagicMock:
    """Provide a mock OllamaClient representing a connected server and available model."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "llama3"
    client.check_connection.return_value = True
    client.model_exists.return_value = True
    client.get_status.return_value = OllamaStatus(
        server_status=ServerStatus.CONNECTED,
        model_status=ModelStatus.AVAILABLE,
        base_url="http://localhost:11434",
        model_name="llama3",
        available_models=["llama3:latest"],
    )
    client.list_models.return_value = ["llama3:latest"]
    client.stream_chat.return_value = iter(["Hello", " from", " assistant."])
    from app.core.ollama_client import ModelResponse
    client.chat.return_value = ModelResponse("Hello from assistant.")
    return client




@pytest.fixture
def mock_disconnected_client() -> MagicMock:
    """Provide a mock OllamaClient representing an unreachable Ollama server."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "llama3"
    client.check_connection.return_value = False
    client.model_exists.return_value = False
    client.get_status.return_value = OllamaStatus(
        server_status=ServerStatus.DISCONNECTED,
        model_status=ModelStatus.UNKNOWN,
        base_url="http://localhost:11434",
        model_name="llama3",
        available_models=[],
        error_message="Connection refused",
    )
    return client


def test_main_default(mock_healthy_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main execution without arguments initializes cleanly."""
    with patch("main.OllamaClient", return_value=mock_healthy_client):
        exit_code = main([])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Local AI Personal Assistant" in captured.out
        assert "Phase 14: Tasks & Controlled Automation Active" in captured.out
        assert "Application initialized successfully" in captured.out


def test_main_gui_flag() -> None:
    """Verify main --gui invokes run_gui and returns its exit code."""
    with patch("app.ui.run_gui", return_value=0) as mock_run_gui:
        exit_code = main(["--gui"])
        assert exit_code == 0
        mock_run_gui.assert_called_once()


def test_main_frozen_executable_launches_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify frozen LocalAssistant.exe without args defaults directly to launching GUI."""
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with patch("app.ui.run_gui", return_value=0) as mock_run_gui:
        exit_code = main([])
        assert exit_code == 0
        mock_run_gui.assert_called_once()


def test_main_background_flag() -> None:
    """Verify main --background invokes run_gui with background_mode=True."""
    with patch("app.ui.run_gui", return_value=0) as mock_run_gui:
        exit_code = main(["--background"])
        assert exit_code == 0
        mock_run_gui.assert_called_once()
        _, kwargs = mock_run_gui.call_args
        assert kwargs.get("background_mode") is True




def test_main_check_flag_success(mock_healthy_client: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main --check returns 0 when all subsystems are healthy."""
    with patch("main.OllamaClient", return_value=mock_healthy_client):
        exit_code = main(["--check"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "[OK] Configuration loaded" in captured.out
        assert "[OK] Runtime directories verified" in captured.out
        assert "[OK] Tool registry initialized" in captured.out
        assert "[OK] Security policy initialized" in captured.out
        assert "[OK] Filesystem boundaries verified" in captured.out
        assert "[OK] System tools initialized" in captured.out
        assert "[OK] Application registry initialized" in captured.out
        assert "[OK] Execution policy initialized" in captured.out
        assert "[OK] Controlled terminal tools initialized" in captured.out
        assert "[OK] Memory database initialized" in captured.out
        assert "[OK] Persistent memory tools initialized" in captured.out
        assert "[OK] Knowledge database initialized" in captured.out
        assert "[OK] Personal knowledge tools initialized" in captured.out
        assert "[OK] Browser manager initialized" in captured.out
        assert "[OK] Browser automation tools initialized" in captured.out
        assert "[OK] Voice input initialized" in captured.out
        assert "[OK] Speech-to-text engine ready" in captured.out
        assert "[OK] Audio output devices initialized" in captured.out
        assert "[OK] Text-to-speech engine ready" in captured.out
        assert "[OK] Task database initialized" in captured.out
        assert "[OK] Task scheduler ready" in captured.out
        assert "[OK] Ollama server reachable" in captured.out
        assert "[OK] Model 'llama3' available" in captured.out
        assert "System check passed successfully" in captured.out












def test_main_check_flag_ollama_offline(
    mock_disconnected_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main --check returns 1 when Ollama server is offline."""
    with patch("main.OllamaClient", return_value=mock_disconnected_client):
        exit_code = main(["--check"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "[FAIL] Ollama server unreachable" in captured.out
        assert "System check encountered errors" in captured.out


def test_main_check_flag_model_missing(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main --check returns 1 when model is missing from server."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "missing-model"
    client.get_status.return_value = OllamaStatus(
        server_status=ServerStatus.CONNECTED,
        model_status=ModelStatus.NOT_AVAILABLE,
        base_url="http://localhost:11434",
        model_name="missing-model",
        available_models=["other-model:latest"],
    )

    with patch("main.OllamaClient", return_value=client):
        exit_code = main(["--check"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "[FAIL] Model 'missing-model' not installed" in captured.out
        assert "System check encountered errors" in captured.out


def test_main_chat_command_success(
    mock_healthy_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main --chat streams response and exits with code 0."""
    with patch("main.OllamaClient", return_value=mock_healthy_client):
        exit_code = main(["--chat", "Explain gravity in one sentence."])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Prompt: Explain gravity in one sentence." in captured.out
        assert "Assistant:" in captured.out
        assert "Hello from assistant." in captured.out


def test_main_chat_command_server_offline(
    mock_disconnected_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main --chat reports error and exits with code 1 when server is offline."""
    with patch("main.OllamaClient", return_value=mock_disconnected_client):
        exit_code = main(["--chat", "Hello"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "Could not connect to Ollama" in captured.err


def test_main_chat_command_model_missing(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main --chat reports error and exits with code 1 when model is not available."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "uninstalled_model"
    client.check_connection.return_value = True
    client.model_exists.return_value = False
    client.list_models.return_value = ["modelA", "modelB"]

    with patch("main.OllamaClient", return_value=client):
        exit_code = main(["--chat", "Hello"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "is not available on Ollama" in captured.err


def test_system_check_success(isolated_settings: Settings, mock_healthy_client: MagicMock) -> None:
    """Verify run_system_check returns True when directories and Ollama are available."""
    from app.tools.registry import ToolRegistry
    assert run_system_check(isolated_settings, mock_healthy_client, ToolRegistry()) is True


def test_system_check_failure_when_path_is_file(
    tmp_path: Path, mock_healthy_client: MagicMock
) -> None:
    """Verify run_system_check returns False when data path is an existing file instead of directory."""
    from app.tools.registry import ToolRegistry
    conflict_file = tmp_path / "not_a_dir"
    conflict_file.write_text("dummy", encoding="utf-8")

    settings = Settings(
        project_root=tmp_path,
        data_dir=conflict_file,
        logs_dir=tmp_path / "logs",
    )
    assert run_system_check(settings, mock_healthy_client, ToolRegistry()) is False


def test_print_status_banner(isolated_settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify status banner renders configuration details and Ollama status."""
    status = OllamaStatus(
        server_status=ServerStatus.CONNECTED,
        model_status=ModelStatus.AVAILABLE,
        base_url="http://localhost:11434",
        model_name="llama3",
        available_models=["llama3"],
    )
    print_status_banner(isolated_settings, status, tools_count=2)
    captured = capsys.readouterr()
    assert isolated_settings.app_name in captured.out
    assert "Connected (http://localhost:11434)" in captured.out
    assert "llama3 (Available)" in captured.out
    assert "2 registered" in captured.out



def test_main_config_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main returns non-zero code on configuration errors."""
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LOG_LEVEL")
    exit_code = main([])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "[FATAL] Configuration error:" in captured.err


def test_main_interactive_mode_quit(
    mock_healthy_client: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main --interactive exits cleanly on /exit."""
    inputs = iter(["/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.OllamaClient", return_value=mock_healthy_client):
        exit_code = main(["--interactive"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Interactive Multi-Turn Chat" in captured.out
        assert "Exiting interactive chat. Goodbye!" in captured.out


def test_main_interactive_mode_turn_and_clear(
    mock_healthy_client: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify multi-turn interaction and /clear in interactive mode."""
    inputs = iter(["Hello assistant", "/clear", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.OllamaClient", return_value=mock_healthy_client):
        exit_code = main(["--interactive"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Assistant: Hello from assistant." in captured.out
        assert "Conversation history cleared." in captured.out


def test_main_interactive_mode_server_offline(
    mock_disconnected_client: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main --interactive exits with code 1 if server is offline."""
    with patch("main.OllamaClient", return_value=mock_disconnected_client):
        exit_code = main(["--interactive"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "Could not connect to Ollama" in captured.err

