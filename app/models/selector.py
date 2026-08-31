"""Request classification and deterministic role selector for intelligent model routing."""

from enum import Enum
import re
from typing import Optional
from app.core.config import Settings, get_settings
from app.models.profiles import ModelRole


class RequestCategory(str, Enum):
    """Categorization of an incoming user request to drive model selection."""

    DIRECT_TOOL = "direct_tool"
    SIMPLE_CHAT = "simple_chat"
    KNOWLEDGE_QUERY = "knowledge_query"
    CODE_TASK = "code_task"
    COMPLEX_REASONING = "complex_reasoning"
    PLANNING = "planning"
    BROWSER_TASK = "browser_task"
    MEMORY_TASK = "memory_task"
    SYSTEM_QUERY = "system_query"
    AUTOMATION_EVENT = "automation_event"


class RequestClassifier:
    """Classifies user requests into typed RequestCategory based on deterministic semantic heuristics."""

    GREETINGS = {"hi", "hello", "hey", "good morning", "good evening", "howdy", "sup", "thanks", "thank you", "bye", "goodbye"}

    @classmethod
    def classify(cls, prompt: str, is_planning: bool = False, is_background: bool = False) -> RequestCategory:
        """Categorize a prompt into a RequestCategory."""
        if is_planning:
            return RequestCategory.PLANNING

        if is_background:
            return RequestCategory.AUTOMATION_EVENT

        norm = prompt.strip().lower()

        # 1. Simple Greetings & Conversational Turns
        if norm in cls.GREETINGS or (len(norm) < 30 and any(norm.startswith(g) for g in ["hello", "hi ", "hey "])):
            return RequestCategory.SIMPLE_CHAT

        # 2. Multi-Step Planning / Complex Workflow triggers
        if any(w in norm for w in ["plan and execute", "multi-step", "create a plan to", "prepare my project", "step by step"]):
            return RequestCategory.PLANNING

        # 3. Code, C project, Compilation & Debugging Tasks
        if any(w in norm for w in ["compile", "debug", "pytest", "refactor", "segfault", "git diff", "git status", ".c file", ".py file"]):
            return RequestCategory.CODE_TASK

        # 4. Web Browser Automation Tasks
        if any(w in norm for w in ["browser", "navigate to", "click on", "web search", "open webpage", "google "]):
            return RequestCategory.BROWSER_TASK

        # 5. Personal Knowledge / RAG queries
        if any(w in norm for w in ["in my documents", "from my notes", "search knowledge", "indexed file", "pdf document", "according to my"]):
            return RequestCategory.KNOWLEDGE_QUERY

        # 6. Persistent Memory Tasks
        if any(w in norm for w in ["remember that", "recall my", "what did i say about", "forget my", "what is my favorite"]):
            return RequestCategory.MEMORY_TASK

        # 7. System Information Queries
        if any(w in norm for w in ["cpu usage", "ram usage", "battery", "system info", "running processes", "uptime", "free memory"]):
            return RequestCategory.SYSTEM_QUERY

        # 8. Complex Reasoning / Long Prompts
        if len(norm.split()) > 60 or any(w in norm for w in ["analyze", "evaluate", "compare and contrast", "architectural trade-offs", "mathematical proof"]):
            return RequestCategory.COMPLEX_REASONING

        # Default standard conversation
        return RequestCategory.SIMPLE_CHAT


class ModelSelector:
    """Maps RequestCategory, context size, and tool requirements to the target ModelRole."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def select_role(
        self,
        category: RequestCategory,
        context_bytes: int = 0,
        requires_tools: bool = False,
    ) -> tuple[ModelRole, str]:
        """Determine the optimal ModelRole and diagnostic explanation for a given request."""
        # 1. Planning & Complex Reasoning strictly requires HEAVY model
        if category in {RequestCategory.PLANNING, RequestCategory.COMPLEX_REASONING}:
            return ModelRole.HEAVY, f"Heavy model selected for {category.value} (expert reasoning required)."

        # 2. Heavy context size forcing larger model
        if context_bytes > self.settings.max_context_bytes_for_standard:
            return ModelRole.HEAVY, f"Heavy model selected due to large context length ({context_bytes} bytes)."

        # 3. Standard Tasks: Code, Browser, RAG
        if category in {RequestCategory.CODE_TASK, RequestCategory.BROWSER_TASK, RequestCategory.KNOWLEDGE_QUERY}:
            return ModelRole.STANDARD, f"Standard model selected for {category.value}."

        # 4. Light / Fast Tasks: Simple Chat, System Query, Memory Lookup, Direct Tool
        if category in {RequestCategory.SIMPLE_CHAT, RequestCategory.SYSTEM_QUERY, RequestCategory.DIRECT_TOOL, RequestCategory.MEMORY_TASK}:
            if context_bytes > self.settings.max_context_bytes_for_fast:
                return ModelRole.STANDARD, f"Standard model selected for {category.value} (context exceeds fast limit)."
            return ModelRole.FAST, f"Fast model selected for {category.value} (lightweight response)."

        # 5. Background / Automation Events
        if category == RequestCategory.AUTOMATION_EVENT:
            return ModelRole.FAST, "Fast model selected for background event processing."

        return ModelRole.STANDARD, f"Standard model selected for generic task."
