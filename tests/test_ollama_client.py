"""Tests for app/core/ollama_client.py with mocked Ollama API responses."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import httpx
import ollama
import pytest

from app.core.exceptions import ModelAPIError, ModelNotFoundError, OllamaConnectionError
from app.core.ollama_client import ChatMessage, OllamaClient


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Fixture providing a mocked ollama.Client."""
    with patch("app.core.ollama_client.ollama.Client") as mock_cls:
        client_instance = MagicMock()
        mock_cls.return_value = client_instance
        yield client_instance


def test_client_init_defaults() -> None:
    """Verify default initialization parameters."""
    with patch("app.core.ollama_client.ollama.Client") as mock_cls:
        client = OllamaClient(base_url="http://mockhost:11434", default_model="qwen:7b", timeout=45.0)
        assert client.base_url == "http://mockhost:11434"
        assert client.default_model == "qwen:7b"
        assert client.timeout == 45.0
        assert mock_cls.call_count == 1
        args, kwargs = mock_cls.call_args
        assert kwargs["host"] == "http://mockhost:11434"
        assert kwargs["timeout"].connect == 10.0


def test_check_connection_success(mock_ollama_client: MagicMock) -> None:
    """Verify check_connection returns True when list succeeds."""
    mock_ollama_client.list.return_value = SimpleNamespace(models=[SimpleNamespace(model="llama3:latest")])
    client = OllamaClient(base_url="http://localhost:11434")

    assert client.check_connection() is True


def test_check_connection_failure(mock_ollama_client: MagicMock) -> None:
    """Verify check_connection returns False when connection is refused."""
    mock_ollama_client.list.side_effect = httpx.ConnectError("Connection refused")
    client = OllamaClient(base_url="http://localhost:11434")

    assert client.check_connection() is False


def test_list_models_parsing(mock_ollama_client: MagicMock) -> None:
    """Verify list_models extracts model names correctly from attributes and dicts."""
    mock_ollama_client.list.return_value = SimpleNamespace(
        models=[
            SimpleNamespace(model="llama3:latest"),
            SimpleNamespace(name="mistral:7b"),
            {"model": "qwen2.5:3b"},
        ]
    )
    client = OllamaClient()
    models = client.list_models()

    assert models == ["llama3:latest", "mistral:7b", "qwen2.5:3b"]


def test_list_models_connection_error(mock_ollama_client: MagicMock) -> None:
    """Verify list_models translates connect error to OllamaConnectionError."""
    mock_ollama_client.list.side_effect = httpx.ConnectError("Network is unreachable")
    client = OllamaClient()

    with pytest.raises(OllamaConnectionError) as exc_info:
        client.list_models()
    assert "Could not connect to Ollama server" in str(exc_info.value)


def test_list_models_timeout_error(mock_ollama_client: MagicMock) -> None:
    """Verify list_models translates timeout to OllamaConnectionError."""
    mock_ollama_client.list.side_effect = httpx.TimeoutException("Read timed out")
    client = OllamaClient()

    with pytest.raises(OllamaConnectionError) as exc_info:
        client.list_models()
    assert "timed out" in str(exc_info.value)


def test_list_models_response_error(mock_ollama_client: MagicMock) -> None:
    """Verify list_models translates ResponseError to ModelAPIError."""
    err = ollama.ResponseError("Internal Server Error", status_code=500)
    mock_ollama_client.list.side_effect = err
    client = OllamaClient()

    with pytest.raises(ModelAPIError) as exc_info:
        client.list_models()
    assert "Ollama API response error" in str(exc_info.value)


@pytest.mark.parametrize(
    "query,available,expected",
    [
        ("llama3", ["llama3:latest", "phi3:mini"], True),
        ("llama3:latest", ["llama3:latest"], True),
        ("llama3:latest", ["llama3"], True),
        ("mistral", ["llama3:latest", "phi3:mini"], False),
        ("qwen2.5", ["qwen2.5:7b"], True),
    ],
)
def test_model_exists_matching(
    mock_ollama_client: MagicMock, query: str, available: list[str], expected: bool
) -> None:
    """Verify model_exists matches exact names and tag variants."""
    mock_ollama_client.list.return_value = SimpleNamespace(
        models=[SimpleNamespace(model=name) for name in available]
    )
    client = OllamaClient()
    assert client.model_exists(query) is expected


def test_model_exists_when_server_offline(mock_ollama_client: MagicMock) -> None:
    """Verify model_exists returns False if the server is offline."""
    mock_ollama_client.list.side_effect = httpx.ConnectError("Offline")
    client = OllamaClient()
    assert client.model_exists("any-model") is False


def test_chat_success(mock_ollama_client: MagicMock) -> None:
    """Verify chat returns generated message content."""
    mock_response = SimpleNamespace(
        message=SimpleNamespace(role="assistant", content="Hello! How can I assist you?")
    )
    mock_ollama_client.chat.return_value = mock_response

    client = OllamaClient(default_model="llama3")
    messages = [
        ChatMessage(role="user", content="Hi"),
        {"role": "user", "content": "Another message"},
    ]
    result = client.chat(messages)

    assert result == "Hello! How can I assist you?"
    mock_ollama_client.chat.assert_called_once_with(
        model="llama3",
        messages=[
            {"role": "user", "content": "Hi"},
            {"role": "user", "content": "Another message"},
        ],
        stream=False,
        options={"num_ctx": 4096},
    )



def test_chat_connection_error(mock_ollama_client: MagicMock) -> None:
    """Verify chat translates connection failure to OllamaConnectionError."""
    mock_ollama_client.chat.side_effect = httpx.ConnectError("Connection refused")
    client = OllamaClient()

    with pytest.raises(OllamaConnectionError):
        client.chat([{"role": "user", "content": "Hello"}])


def test_chat_model_not_found(mock_ollama_client: MagicMock) -> None:
    """Verify chat translates 404 ResponseError to ModelNotFoundError."""
    mock_ollama_client.chat.side_effect = ollama.ResponseError("model 'missing' not found", status_code=404)
    client = OllamaClient()

    with pytest.raises(ModelNotFoundError):
        client.chat([{"role": "user", "content": "Hello"}], model="missing")


def test_chat_general_api_error(mock_ollama_client: MagicMock) -> None:
    """Verify chat translates generic ResponseError to ModelAPIError."""
    mock_ollama_client.chat.side_effect = ollama.ResponseError("Failed inference", status_code=500)
    client = OllamaClient()

    with pytest.raises(ModelAPIError):
        client.chat([{"role": "user", "content": "Hello"}])


def test_stream_chat_success(mock_ollama_client: MagicMock) -> None:
    """Verify stream_chat yields string tokens incrementally."""
    chunks = [
        SimpleNamespace(message=SimpleNamespace(content="Hello")),
        SimpleNamespace(message=SimpleNamespace(content=" world")),
        SimpleNamespace(message=SimpleNamespace(content="!")),
    ]
    mock_ollama_client.chat.return_value = iter(chunks)

    client = OllamaClient(default_model="llama3")
    stream = client.stream_chat([{"role": "user", "content": "Say hello"}])
    tokens = list(stream)

    assert tokens == ["Hello", " world", "!"]
    assert "".join(tokens) == "Hello world!"


def test_stream_chat_connection_error(mock_ollama_client: MagicMock) -> None:
    """Verify stream_chat handles connection error during streaming."""
    mock_ollama_client.chat.side_effect = httpx.ConnectError("Network dropped")

    client = OllamaClient()
    stream = client.stream_chat([{"role": "user", "content": "Hi"}])

    with pytest.raises(OllamaConnectionError):
        next(stream)
