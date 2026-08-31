"""Response quality evaluation, false completion protection, and clean formatting."""

import json
import re
from typing import Any, Optional
from app.agent.intelligence_models import QualityEvaluation
from app.core.logging import get_logger

logger = get_logger("agent.quality")


class ResponseQualityEvaluator:
    """Evaluates final model responses to prevent false completions, hallucinations, and raw JSON dumping."""

    FALSE_COMPLETION_PATTERNS = [
        r"\b(i have (created|deleted|written|modified|opened|compiled|executed)|done\!|successfully (created|deleted|written|opened))\b",
        r"\bthe file (has been|was) (created|written|deleted)\b",
        r"\ball tasks (are|were) completed successfully\b",
    ]

    def evaluate(
        self,
        response_text: str,
        tool_executions: Optional[list[dict[str, Any]]] = None,
        goal: Optional[str] = None,
    ) -> QualityEvaluation:
        """Run deterministic quality checks against generated assistant response."""
        issues: list[str] = []
        sanitized = response_text.strip()
        false_completion = False

        # 1. Empty / Whitespace check
        if not sanitized:
            return QualityEvaluation(
                passed=False,
                issues=["Empty response generated"],
                sanitized_content="I processed your request, but no textual output was generated. Please let me know how you would like to proceed.",
                quality_score=0.0,
            )

        # 2. False Completion Check when tool failed
        failed_tools = [
            t for t in (tool_executions or [])
            if not t.get("success", True)
        ]
        if failed_tools:
            norm_resp = sanitized.lower()
            if any(re.search(p, norm_resp) for p in self.FALSE_COMPLETION_PATTERNS):
                false_completion = True
                issues.append("False completion detected: response claimed success despite tool failure")
                first_err = failed_tools[0].get("error", "The requested operation failed.")
                sanitized = f"I was unable to complete the requested action because the operation failed: {first_err}"
                logger.warning("False completion intercepted and replaced with accurate error explanation.")

        # 3. System Prompt & Internal Directive Leakage Protection
        raw_markers = [
            "you are a helpful, secure, and precise local ai personal assistant",
            "security invariants: the llm is never a security authority",
            "tools_summary = self._format_tools_summary()",
        ]
        if any(marker in sanitized.lower() for marker in raw_markers):
            issues.append("Internal system prompt leakage prevented")
            sanitized = "I am a local AI personal assistant configured to help you safely with daily computing, development, and productivity tasks while strictly enforcing security policies."

        # 4. Clean raw tool JSON dumps if detected
        if sanitized.startswith("{") and sanitized.endswith("}"):
            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, dict):
                    # Format into key-value pairs rather than raw JSON
                    lines = [f"- **{k}**: {v}" for k, v in parsed.items()]
                    sanitized = "\n".join(lines)
                    issues.append("Raw JSON response converted to structured text")
            except Exception:
                pass

        # 4. Repetition detection (e.g. repeated identical sentences >= 3 times)
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", sanitized) if len(s.strip()) > 15]
        for s in set(sentences):
            if sentences.count(s) >= 3:
                issues.append(f"Repetitive sentence detected: '{s[:30]}...'")
                # Deduplicate repeated sentences
                pattern = re.escape(s) + r"(?:[\.\!\?]?\s*" + re.escape(s) + r")+"
                sanitized = re.sub(pattern, s + ".", sanitized)

        score = 1.0 - (len(issues) * 0.2)
        score = max(0.0, min(1.0, score))

        return QualityEvaluation(
            passed=len(issues) == 0,
            issues=issues,
            sanitized_content=sanitized,
            false_completion_detected=false_completion,
            quality_score=score,
        )
