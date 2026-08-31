"""Intent analysis and structured request interpretation."""

import re
from typing import Any, Optional
from app.agent.intelligence_models import ActionType, RequestIntent
from app.core.logging import get_logger

logger = get_logger("agent.intent")


class IntentAnalyzer:
    """Performs deterministic intent understanding, entity extraction, and action routing."""

    GREETINGS = {"hi", "hello", "hey", "good morning", "good evening", "howdy", "sup", "thanks", "thank you", "bye", "goodbye"}

    EXPLANATORY_PATTERNS = [
        r"^explain\b",
        r"^what is\s+(a|an|the)?\s+(recursion|pointer|class|interface|decorator|generator|algorithm|concept|metaphor|difference between)\b",
        r"^how does\s+.+\s+work\b",
        r"^why is\s+.+\s+(used|important|faster|better)\b",
        r"^tell me about\b",
        r"^describe\s+.+\s+(concept|pattern|paradigm)\b",
    ]

    AMBIGUOUS_PATTERNS = [
        (r"^(fix|run|do|delete|remove|open|modify|update)\s+this$", "Could you clarify specifically which file, process, or project you would like me to work on?"),
        (r"^delete\s+(the\s+)?(report|file|document)$", "Which specific file or report would you like me to delete? Please specify the file name or path."),
        (r"^open\s+(the\s+)?(app|application|project)$", "Which specific application or project would you like me to open?"),
    ]

    def analyze(self, prompt: str, active_project: Optional[str] = None, context_history: Optional[list[dict[str, str]]] = None) -> RequestIntent:
        """Analyze prompt structure, conversational context, and entities to determine action routing."""
        norm = prompt.strip().lower()

        # 1. Greetings & Simple Conversational Turns -> ANSWER
        if norm in self.GREETINGS or (len(norm) < 25 and any(norm.startswith(g) for g in ["hello", "hi ", "hey ", "thanks", "thank you"])):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Greeting or conversational acknowledgment",
                action_type=ActionType.ANSWER,
                category="simple_chat",
                confidence=1.0,
                requires_tools=False,
            )

        # 2. Check for Ambiguity requiring Clarification -> CLARIFICATION
        for pat, question in self.AMBIGUOUS_PATTERNS:
            if re.search(pat, norm):
                return RequestIntent(
                    raw_prompt=prompt,
                    normalized_goal="Ambiguous request needing clarification",
                    action_type=ActionType.CLARIFICATION,
                    category="ambiguous_request",
                    ambiguity_score=0.9,
                    clarification_prompt=question,
                    confidence=0.95,
                    requires_tools=False,
                )

        # 3. Pure Explanatory & Educational Questions -> ANSWER (Strict "Don't use tool" rule)
        if any(re.search(p, norm) for p in self.EXPLANATORY_PATTERNS):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Explain concept or terminology",
                action_type=ActionType.ANSWER,
                category="explanation",
                confidence=0.95,
                requires_tools=False,
            )

        # 4. Multi-Step Complex Planning Goals -> PLAN
        planning_keywords = [
            "prepare my project",
            "plan and execute",
            "create a plan",
            "plan to",
            "multi-step",
            "inspect, compile, test",
            "compile the project and run tests",
            "build and test",
            "step by step workflow",
            "step by step",
            "refactor and verify",
        ]
        if any(kw in norm for kw in planning_keywords) or (len(norm.split()) > 20 and "compile" in norm and "test" in norm):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Multi-step development or verification plan",
                action_type=ActionType.PLAN,
                category="planning",
                confidence=0.95,
                requires_planning=True,
                requires_tools=True,
                suggested_tool_groups=["terminal", "filesystem", "system"],
            )

        # 5. Arithmetic & Calculations -> TOOL (demo)
        if any(op in norm for op in ["*", "+", "/", "-", "^"]) and any(c.isdigit() for c in norm) and any(w in norm for w in ["what is", "calculate", "compute", "solve", "*", "+", "/"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Perform mathematical calculation",
                action_type=ActionType.TOOL,
                category="direct_tool",
                confidence=0.95,
                requires_tools=True,
                suggested_tool_groups=["demo"],
            )

        # 6. Persistent Memory Operations -> TOOL (memory)
        if any(w in norm for w in ["remember that", "remember my", "recall my", "what is my favorite", "what is my main project", "forget my"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Access or update persistent memory",
                action_type=ActionType.TOOL,
                category="memory_task",
                confidence=0.95,
                requires_tools=True,
                requires_memory=True,
                suggested_tool_groups=["memory"],
            )

        # 7. Personal Knowledge / Document Search -> TOOL (knowledge)
        if any(w in norm for w in ["in my documents", "from my notes", "search knowledge", "indexed file", "pdf document", "codename of the project", "time dilation"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Retrieve information from personal knowledge documents",
                action_type=ActionType.TOOL,
                category="knowledge_query",
                confidence=0.95,
                requires_tools=True,
                requires_knowledge=True,
                suggested_tool_groups=["knowledge"],
            )

        # 8. Real-time System Metrics -> TOOL (system)
        if any(w in norm for w in ["ram usage", "cpu usage", "battery", "uptime", "hardware specs", "memory usage", "running processes"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Query real-time host system metrics",
                action_type=ActionType.TOOL,
                category="system_query",
                confidence=0.95,
                requires_tools=True,
                suggested_tool_groups=["system"],
            )

        # 9. Application Management -> TOOL (apps)
        if any(w in norm for w in ["open notepad", "launch notepad", "close notepad", "open vs code", "open calculator"]):
            app_match = "notepad" if "notepad" in norm else "code" if "code" in norm else "calc"
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal=f"Manage application '{app_match}'",
                action_type=ActionType.TOOL,
                category="application_task",
                entities={"application": app_match},
                confidence=0.95,
                requires_tools=True,
                suggested_tool_groups=["system"],
            )

        # 10. Web Browser Automation -> TOOL (browser)
        if any(w in norm for w in ["browser", "navigate to", "open url", "google search", "web search"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Automate web browser interaction",
                action_type=ActionType.TOOL,
                category="browser_task",
                confidence=0.90,
                requires_tools=True,
                suggested_tool_groups=["browser"],
            )

        # 11. Filesystem & Code Tasks -> TOOL (filesystem / terminal)
        if any(w in norm for w in ["read file", "write file", "create directory", "compile", "run test", "git status", "git diff"]):
            return RequestIntent(
                raw_prompt=prompt,
                normalized_goal="Perform filesystem or terminal development action",
                action_type=ActionType.TOOL,
                category="code_task",
                confidence=0.90,
                requires_tools=True,
                suggested_tool_groups=["filesystem", "terminal"],
            )

        # Default fallback: standard answer
        return RequestIntent(
            raw_prompt=prompt,
            normalized_goal="General user inquiry",
            action_type=ActionType.ANSWER,
            category="general_chat",
            confidence=0.75,
            requires_tools=False,
        )
