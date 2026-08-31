"""Data models for persistent SQLite memory and conversation history."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    """Categorization for structured persistent memories."""

    PREFERENCE = "PREFERENCE"
    PERSONAL_FACT = "PERSONAL_FACT"
    PROJECT = "PROJECT"
    WORKFLOW = "WORKFLOW"
    CONTEXT = "CONTEXT"


class MemorySource(str, Enum):
    """Source origin of a persistent memory."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    IMPORTED = "imported"


class MemoryRecord(BaseModel):
    """A structured persistent memory item stored in SQLite."""

    id: str = Field(description="Unique UUID identifying the memory")
    category: MemoryCategory = Field(description="Memory category")
    key: str = Field(description="Normalized key/identifier for the memory")
    value: str = Field(description="The persistent information/fact value")
    importance: int = Field(default=5, ge=1, le=10, description="Importance score from 1 (low) to 10 (critical)")
    source: MemorySource = Field(default=MemorySource.USER, description="Origin source of the memory")
    created_at: str = Field(description="ISO 8601 creation timestamp in UTC")
    updated_at: str = Field(description="ISO 8601 last update timestamp in UTC")


class ConversationRecord(BaseModel):
    """A persistent conversation session record."""

    id: str = Field(description="UUID identifying the conversation session")
    title: str = Field(default="New Conversation", description="Descriptive title or summary of conversation")
    created_at: str = Field(description="ISO 8601 creation timestamp in UTC")
    updated_at: str = Field(description="ISO 8601 last activity timestamp in UTC")


class MessageRecord(BaseModel):
    """A single persistent conversational turn message."""

    id: str = Field(description="UUID identifying the message")
    conversation_id: str = Field(description="ID of the parent conversation")
    role: str = Field(description="Message role: user, assistant, system, tool")
    content: str = Field(description="Message text or tool response content")
    sequence_number: int = Field(description="Sequential ordering number within the conversation")
    created_at: str = Field(description="ISO 8601 timestamp in UTC")
