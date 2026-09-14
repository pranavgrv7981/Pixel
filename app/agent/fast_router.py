"""Confidence-based fast intent router directing user requests to direct execution or model tiers."""

import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger("agent.fast_router")


class FastRouteDecision(BaseModel):
    """Routing decision with confidence score and sub-tier activation flags."""

    intent: str = Field(description="Detected high-level intent category")
    confidence: float = Field(default=0.0, description="Confidence score from 0.0 to 1.0")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Parsed arguments from prompt")
    is_deterministic: bool = Field(default=False, description="Whether prompt can be resolved without LLM")
    requires_tools: bool = Field(default=False, description="Whether LLM tool calling schema is required")
    requires_memory: bool = Field(default=False, description="Whether long-term persistent memory lookup is needed")
    requires_rag: bool = Field(default=False, description="Whether knowledge vector database lookup is needed")
    suggested_tier: str = Field(default="FAST_MODEL", description="DIRECT, FAST_MODEL, STANDARD, or HEAVY")


class FastRouter:
    """Fast rule-and-pattern router evaluated in < 1 ms before context assembly or LLM invocation."""

    @classmethod
    def route(cls, prompt: str) -> FastRouteDecision:
        text = prompt.strip()
        if not text:
            return FastRouteDecision(
                intent="empty",
                confidence=1.0,
                is_deterministic=True,
                suggested_tier="DIRECT",
            )

        lower = text.lower().strip("?.! \t\n")

        # 1. Deterministic Time & Date (Confidence: 1.0)
        time_patterns = {"what time is it", "time", "current time", "tell me the time", "what is the time", "what's the time"}
        if lower in time_patterns:
            return FastRouteDecision(
                intent="time",
                confidence=1.0,
                is_deterministic=True,
                suggested_tier="DIRECT",
            )

        date_patterns = {"what is today's date", "what is the date", "what's the date", "today's date", "current date", "date", "what day is it", "what day is today"}
        if lower in date_patterns:
            return FastRouteDecision(
                intent="date",
                confidence=1.0,
                is_deterministic=True,
                suggested_tier="DIRECT",
            )

        # 2. Deterministic Math & Calculation (Confidence: 0.98)
        math_prefixes = (r"^calculate\s+", r"^what\s+is\s+", r"^what's\s+", r"^calc\s+", r"^math:\s*", r"^eval\s+", r"^evaluate\s+")
        candidate_math = text
        for p in math_prefixes:
            m = re.search(p, candidate_math, re.IGNORECASE)
            if m:
                candidate_math = candidate_math[m.end():]
                break
        candidate_math = candidate_math.strip("?.! \t\n")

        has_math_chars = bool(re.search(r"[\+\-\*\/\%\^]|\b(sqrt|sin|cos|abs|round)\b", candidate_math))
        has_invalid_words = bool(re.search(r"[a-zA-Z]{4,}", candidate_math) and not re.search(r"\b(sqrt|round|abs)\b", candidate_math))
        # Ensure digits exist
        has_digits = bool(re.search(r"\d", candidate_math))

        if has_math_chars and has_digits and not has_invalid_words:
            return FastRouteDecision(
                intent="math",
                confidence=0.98,
                arguments={"expression": candidate_math},
                is_deterministic=True,
                suggested_tier="DIRECT",
            )

        # 3. Deterministic App Launch (Confidence: 0.95)
        app_match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9_\-\. ]+)$", text.strip(), re.IGNORECASE)
        if app_match:
            target_app = app_match.group(1).strip().lower()
            known_apps = {"notepad", "calculator", "calc", "vscode", "code", "chrome", "edge", "paint", "mspaint", "explorer"}
            if target_app in known_apps:
                return FastRouteDecision(
                    intent="app_launch",
                    confidence=0.95,
                    arguments={"app_name": target_app},
                    is_deterministic=True,
                    suggested_tier="DIRECT",
                )

        # 4. Deterministic Memory Store (Confidence: 0.95)
        store_match = re.match(r"^remember\s+(?:that\s+)?(.+)$", text.strip(), re.IGNORECASE)
        if store_match:
            mem = store_match.group(1).strip()
            if mem:
                return FastRouteDecision(
                    intent="memory_store",
                    confidence=0.95,
                    arguments={"content": mem},
                    is_deterministic=True,
                    requires_memory=True,
                    suggested_tier="DIRECT",
                )

        # 5. Deterministic Memory Recall (Confidence: 0.95)
        recall_match = re.match(r"^(?:recall|what\s+do\s+you\s+remember\s+about)\s+([a-zA-Z0-9_\- ]+)\??$", text.strip(), re.IGNORECASE)
        if recall_match:
            query = recall_match.group(1).strip()
            if query:
                return FastRouteDecision(
                    intent="memory_recall",
                    confidence=0.95,
                    arguments={"query": query},
                    is_deterministic=True,
                    requires_memory=True,
                    suggested_tier="DIRECT",
                )

        # 6. System Status / Battery (Confidence: 0.95)
        if lower in ("battery", "battery status", "what is my battery level", "check battery", "battery percent", "disk usage", "disk space", "check disk", "storage usage"):
            return FastRouteDecision(
                intent="system_status",
                confidence=0.95,
                arguments={"query": lower},
                is_deterministic=True,
                suggested_tier="DIRECT",
            )

        # 7. Conversational Turn (Greetings / Small Talk) -> Fast Model, NO tools, NO RAG, NO long-term memory lookup
        norm_text = re.sub(r"[^\w\s]", " ", lower).strip()
        norm_words = norm_text.split()
        casual_greetings = {
            "hi", "hello", "hey", "howdy", "good morning", "good afternoon", "good evening",
            "how are you", "how are you doing", "what s up", "whats up", "who are you", "what is your name",
            "thank you", "thanks", "bye", "goodbye", "see you", "help", "what can you do"
        }
        is_greeting = (
            norm_text in casual_greetings
            or (len(norm_words) <= 7 and any(w in norm_words for w in ("hi", "hello", "hey", "howdy", "thanks", "thank")) and not any(w in norm_words for w in ("file", "code", "run", "open", "calculate", "search", "test")))
            or ("how are you" in norm_text and not any(w in norm_words for w in ("file", "code", "run", "execute")))
        )
        if is_greeting:
            return FastRouteDecision(
                intent="casual_chat",
                confidence=0.90,
                is_deterministic=False,
                requires_tools=False,
                requires_memory=False,
                requires_rag=False,
                suggested_tier="FAST_MODEL",
            )

        # 8. Complex Tasks / Tool Invocation / Coding / Planning
        requires_tools = bool(re.search(r"\b(file|folder|create|delete|search|browse|click|task|trigger|plan|code|execute|run|read|write)\b", lower))
        requires_rag = bool(re.search(r"\b(document|knowledge|index|pdf|summarize document|notes)\b", lower))
        requires_memory = bool(re.search(r"\b(remember|preference|profile|recall|favorite)\b", lower))
        is_complex = bool(re.search(r"\b(plan|workflow|architect|refactor|debug|analyze deep)\b", lower))

        tier = "HEAVY" if is_complex else "STANDARD"

        return FastRouteDecision(
            intent="general_request",
            confidence=0.80,
            is_deterministic=False,
            requires_tools=requires_tools,
            requires_memory=requires_memory,
            requires_rag=requires_rag,
            suggested_tier=tier,
        )
