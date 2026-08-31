"""Unit tests for OllamaManager lifecycle, executable discovery, and auto-start logic."""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.ollama_manager import OllamaManager


def test_ollama_manager_is_server_running_true() -> None:
    mgr = OllamaManager(settings=Settings())
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        assert mgr.is_server_running() is True


def test_ollama_manager_is_server_running_false() -> None:
    mgr = OllamaManager(settings=Settings())
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        assert mgr.is_server_running() is False


def test_find_executable_from_settings(tmp_path: Path) -> None:
    fake_exe = tmp_path / "fake_ollama.exe"
    fake_exe.write_text("binary")

    settings = Settings(ollama_executable=str(fake_exe))
    mgr = OllamaManager(settings=settings)

    assert mgr.find_executable() == fake_exe.resolve()


def test_find_executable_from_path() -> None:
    mgr = OllamaManager(settings=Settings())
    with patch("shutil.which", return_value=r"C:\Program Files\Ollama\ollama.exe"):
        exe = mgr.find_executable()
        assert exe == Path(r"C:\Program Files\Ollama\ollama.exe").resolve()


def test_start_server_reuses_existing_instance() -> None:
    mgr = OllamaManager(settings=Settings())
    with patch.object(mgr, "is_server_running", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            started = mgr.start_server()
            assert started is True
            assert mgr.started_by_app is False
            mock_popen.assert_not_called()


def test_start_server_spawns_process_and_waits(tmp_path: Path) -> None:
    fake_exe = tmp_path / "ollama.exe"
    fake_exe.write_text("binary")

    mgr = OllamaManager(settings=Settings(ollama_executable=str(fake_exe)))

    with patch.object(mgr, "is_server_running", side_effect=[False, True]):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 9999
            mock_popen.return_value = mock_proc

            started = mgr.start_server(wait_seconds=5.0)
            assert started is True
            assert mgr.started_by_app is True
            mock_popen.assert_called_once()


def test_stop_if_owned_terminates_only_when_started_by_app() -> None:
    mgr = OllamaManager(settings=Settings(stop_ollama_on_exit=True))

    # Case 1: Not started by app -> does not kill
    mock_proc = MagicMock()
    mgr._process = mock_proc
    mgr.started_by_app = False
    mgr.stop_if_owned()
    mock_proc.terminate.assert_not_called()

    # Case 2: Started by app -> terminates
    mgr.started_by_app = True
    mgr.stop_if_owned()
    mock_proc.terminate.assert_called_once()
    assert mgr.started_by_app is False
    assert mgr._process is None


def test_list_and_validate_models() -> None:
    mgr = OllamaManager(settings=Settings())
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"models": [{"name": "qwen3:30b"}, {"model": "llama3:latest"}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        models = mgr.list_available_models()
        assert "qwen3:30b" in models
        assert "llama3:latest" in models
        assert mgr.is_model_available("qwen3:30b") is True
        assert mgr.is_model_available("nonexistent_model") is False


def test_preload_model_uses_generous_timeout() -> None:
    settings = Settings(preload_model=True, ollama_timeout_seconds=300.0)
    mgr = OllamaManager(settings=settings)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        success = mgr.preload_model_if_requested("qwen3:30b")
        assert success is True
        assert mock_urlopen.call_count == 1
        args, kwargs = mock_urlopen.call_args
        assert kwargs["timeout"] >= 300.0

