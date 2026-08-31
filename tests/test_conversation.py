"""Tests for app/agent/conversation.py with mocked OllamaClient."""

from unittest.mock import MagicMock
import pytest

from app.agent.conversation import Conversation, ConversationManager, Message, Role
from app.core.exceptions import (
    ConversationNotFoundError,
    InvalidMessageError,
    ModelAPIError,
    OllamaConnectionError,
)
from app.core.ollama_client import OllamaClient


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Fixture providing a mocked OllamaClient."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "llama3"
    client.check_connection.return_value = True
    client.model_exists.return_value = True
    client.chat.return_value = "Mocked assistant response"
    client.stream_chat.return_value = iter(["Mocked ", "streaming ", "response"])
    return client


def test_conversation_creation() -> None:
    """Verify Conversation initialization and default values."""
    conv = Conversation()
    assert conv.id is not None
    assert len(conv.id) > 10  # UUID format
    assert conv.created_at is not None
    assert conv.system_prompt is None
    assert conv.message_count() == 0
    assert conv.get_messages() == []


def test_conversation_id_unique() -> None:
    """Verify generated conversation IDs are distinct."""
    conv1 = Conversation()
    conv2 = Conversation()
    assert conv1.id != conv2.id


def test_system_prompt_configuration() -> None:
    """Verify system prompt is properly set and trimmed."""
    conv = Conversation(system_prompt="  You are a personal assistant.  ")
    assert conv.system_prompt == "You are a personal assistant."
    payload = conv.get_messages_for_llm()
    assert len(payload) == 1
    assert payload[0] == {"role": "system", "content": "You are a personal assistant."}


def test_message_insertion_and_ordering() -> None:
    """Verify user and assistant messages are recorded in sequence."""
    conv = Conversation(system_prompt="System instructions")
    msg1 = conv.add_user_message("First user turn")
    msg2 = conv.add_assistant_message("First assistant reply")
    msg3 = conv.add_user_message("Second user turn")

    assert conv.message_count() == 3
    messages = conv.get_messages()
    assert messages[0].role == Role.USER
    assert messages[0].content == "First user turn"
    assert messages[1].role == Role.ASSISTANT
    assert messages[1].content == "First assistant reply"
    assert messages[2].role == Role.USER
    assert messages[2].content == "Second user turn"

    # Verify LLM payload includes system message followed by history in order
    llm_msgs = conv.get_messages_for_llm()
    assert len(llm_msgs) == 4
    assert llm_msgs[0]["role"] == "system"
    assert llm_msgs[1]["role"] == "user"
    assert llm_msgs[2]["role"] == "assistant"
    assert llm_msgs[3]["role"] == "user"


def test_invalid_role_rejection() -> None:
    """Verify invalid roles are rejected with InvalidMessageError."""
    conv = Conversation()
    with pytest.raises(InvalidMessageError):
        conv.add_message("invalid_role", "Valid content")

    with pytest.raises(InvalidMessageError):
        conv.add_message(123, "Valid content")  # type: ignore


@pytest.mark.parametrize("bad_input", ["", "   ", "\n\t  \n"])
def test_empty_and_whitespace_user_message_rejection(bad_input: str) -> None:
    """Verify empty or whitespace-only messages raise InvalidMessageError."""
    conv = Conversation()
    with pytest.raises(InvalidMessageError):
        conv.add_user_message(bad_input)


def test_non_string_message_rejection() -> None:
    """Verify non-string content raises InvalidMessageError."""
    conv = Conversation()
    with pytest.raises(InvalidMessageError):
        conv.add_user_message(None)  # type: ignore

    with pytest.raises(InvalidMessageError):
        conv.add_user_message(12345)  # type: ignore


def test_defensive_history_copy() -> None:
    """Verify get_messages returns a copy that does not allow internal state corruption."""
    conv = Conversation()
    conv.add_user_message("Original message")

    msgs = conv.get_messages()
    msgs.clear()  # Mutating returned list
    assert conv.message_count() == 1

    # Mutating message object in returned list
    msgs2 = conv.get_messages()
    msgs2[0].content = "Tampered message"
    assert conv.get_messages()[0].content == "Original message"


def test_history_size_limiting() -> None:
    """Verify history trims oldest messages when exceeding max_messages limit."""
    conv = Conversation(system_prompt="System prompt", max_messages=4)
    conv.add_user_message("Msg 1")
    conv.add_assistant_message("Msg 2")
    conv.add_user_message("Msg 3")
    conv.add_assistant_message("Msg 4")
    assert conv.message_count() == 4

    # Add 5th message; Msg 1 should be dropped
    conv.add_user_message("Msg 5")
    assert conv.message_count() == 4
    contents = [m.content for m in conv.get_messages()]
    assert contents == ["Msg 2", "Msg 3", "Msg 4", "Msg 5"]


def test_system_prompt_retained_during_trimming() -> None:
    """Verify system prompt is never lost during message trimming."""
    conv = Conversation(system_prompt="Immortal System Prompt", max_messages=2)
    for i in range(10):
        conv.add_user_message(f"Message {i}")

    assert conv.message_count() == 2
    llm_msgs = conv.get_messages_for_llm()
    assert len(llm_msgs) == 3
    assert llm_msgs[0] == {"role": "system", "content": "Immortal System Prompt"}
    assert llm_msgs[1]["content"] == "Message 8"
    assert llm_msgs[2]["content"] == "Message 9"


def test_conversation_clear_and_reset() -> None:
    """Verify clear and reset remove all conversational turns while preserving system prompt."""
    conv = Conversation(system_prompt="Retained prompt")
    conv.add_user_message("Turn 1")
    conv.add_assistant_message("Turn 2")
    assert conv.message_count() == 2

    conv.clear()
    assert conv.message_count() == 0
    assert conv.system_prompt == "Retained prompt"
    assert len(conv.get_messages_for_llm()) == 1


# --- ConversationManager Tests ---


def test_conversation_manager_init(mock_ollama_client: MagicMock) -> None:
    """Verify ConversationManager initializes with active conversation."""
    manager = ConversationManager(client=mock_ollama_client, system_prompt="Test Assistant")
    assert manager.active_conversation is not None
    assert manager.active_conversation.system_prompt == "Test Assistant"


def test_conversation_manager_send_message_success(mock_ollama_client: MagicMock) -> None:
    """Verify send_message records user message, calls client, and records assistant response."""
    mock_ollama_client.chat.return_value = "I am an assistant."
    manager = ConversationManager(client=mock_ollama_client, system_prompt="Sys")

    reply = manager.send_message("Hello!")
    assert reply == "I am an assistant."

    conv = manager.active_conversation
    assert conv.message_count() == 2
    msgs = conv.get_messages()
    assert msgs[0].role == Role.USER and msgs[0].content == "Hello!"
    assert msgs[1].role == Role.ASSISTANT and msgs[1].content == "I am an assistant."


def test_conversation_manager_send_message_failure_preserves_user_no_fake_assistant(
    mock_ollama_client: MagicMock,
) -> None:
    """Verify when Ollama fails, user message is kept but no assistant message is recorded."""
    mock_ollama_client.chat.side_effect = OllamaConnectionError("Connection lost")
    manager = ConversationManager(client=mock_ollama_client)

    with pytest.raises(OllamaConnectionError):
        manager.send_message("Will fail")

    conv = manager.active_conversation
    # User message was recorded, but NO assistant message
    assert conv.message_count() == 1
    assert conv.get_messages()[0].role == Role.USER
    assert conv.get_messages()[0].content == "Will fail"


def test_conversation_manager_stream_message_success(mock_ollama_client: MagicMock) -> None:
    """Verify stream_message yields tokens and records assistant message exactly once."""
    mock_ollama_client.stream_chat.return_value = iter(["Chunk 1, ", "Chunk 2, ", "done."])
    manager = ConversationManager(client=mock_ollama_client)

    stream = manager.stream_message("Tell me a story")
    collected = list(stream)

    assert collected == ["Chunk 1, ", "Chunk 2, ", "done."]
    assert "".join(collected) == "Chunk 1, Chunk 2, done."

    conv = manager.active_conversation
    assert conv.message_count() == 2
    msgs = conv.get_messages()
    assert msgs[0].role == Role.USER and msgs[0].content == "Tell me a story"
    assert msgs[1].role == Role.ASSISTANT and msgs[1].content == "Chunk 1, Chunk 2, done."


def test_conversation_manager_stream_message_failure_handling(mock_ollama_client: MagicMock) -> None:
    """Verify stream_message failure mid-stream does not record misleading assistant message."""

    def broken_stream(*args: object, **kwargs: object) -> Iterator[str]:
        yield "Initial chunk"
        raise ModelAPIError("Stream disconnected abruptly")

    mock_ollama_client.stream_chat.side_effect = broken_stream
    manager = ConversationManager(client=mock_ollama_client)

    stream = manager.stream_message("Begin stream")
    assert next(stream) == "Initial chunk"

    with pytest.raises(ModelAPIError):
        next(stream)

    conv = manager.active_conversation
    # Only the user message should remain in history
    assert conv.message_count() == 1
    assert conv.get_messages()[0].role == Role.USER


def test_conversation_manager_multi_turn_history(mock_ollama_client: MagicMock) -> None:
    """Verify multi-turn history accumulates and passes full context to Ollama."""
    mock_ollama_client.chat.side_effect = ["Nice to meet you, Alex.", "Your name is Alex."]
    manager = ConversationManager(client=mock_ollama_client, system_prompt="Be concise.")

    reply1 = manager.send_message("My name is Alex.")
    assert reply1 == "Nice to meet you, Alex."

    reply2 = manager.send_message("What is my name?")
    assert reply2 == "Your name is Alex."

    assert manager.active_conversation.message_count() == 4
    # Check the payload sent to Ollama on turn 2
    last_call_args = mock_ollama_client.chat.call_args[0][0]
    assert len(last_call_args) == 4  # System + User1 + Assistant1 + User2
    assert last_call_args[0] == {"role": "system", "content": "Be concise."}
    assert last_call_args[1] == {"role": "user", "content": "My name is Alex."}
    assert last_call_args[2] == {"role": "assistant", "content": "Nice to meet you, Alex."}
    assert last_call_args[3] == {"role": "user", "content": "What is my name?"}


def test_conversation_manager_reset(mock_ollama_client: MagicMock) -> None:
    """Verify manager.reset() resets the active conversation history."""
    manager = ConversationManager(client=mock_ollama_client)
    manager.send_message("Hello")
    assert manager.active_conversation.message_count() == 2

    manager.reset()
    assert manager.active_conversation.message_count() == 0


def test_conversation_manager_invalid_id(mock_ollama_client: MagicMock) -> None:
    """Verify get_conversation with nonexistent ID raises ConversationNotFoundError."""
    manager = ConversationManager(client=mock_ollama_client)
    with pytest.raises(ConversationNotFoundError):
        manager.get_conversation("non-existent-uuid")
