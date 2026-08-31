"""Conversation summarization and history compaction engine."""

import re
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.database import ContextDatabase
from app.context.models import ConversationSummaryRecord
from app.context.ranker import estimate_tokens

logger = get_logger("context.summarizer")


class ConversationSummarizer:
    """Extracts concise summaries and key topics from older conversational turns."""

    def __init__(
        self,
        db: Optional[ContextDatabase] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or ContextDatabase(settings=self.settings)

    def should_summarize(self, total_messages: int) -> bool:
        """Check if message count exceeds the summarization threshold."""
        return total_messages >= self.settings.summarization_threshold_messages

    def extract_key_points(self, messages: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
        """Extract key topics and explicit decisions deterministically from messages."""
        topics: list[str] = []
        decisions: list[str] = []

        decision_markers = ["prefer", "want", "decided", "use", "always", "never", "set", "configured", "project is"]

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue

            lines = [line.strip() for line in content.split("\n") if line.strip()]
            for line in lines:
                lower_line = line.lower()
                # Decision heuristics
                if any(marker in lower_line for marker in decision_markers):
                    clean_dec = re.sub(r"^[*\-•\d\.\s]+", "", line).strip()
                    if clean_dec and len(clean_dec) < 150 and clean_dec not in decisions:
                        decisions.append(clean_dec)

                # Question / Topic heuristics
                if "?" in line and len(line) < 120:
                    clean_q = line.strip()
                    if clean_q not in topics:
                        topics.append(clean_q)

        return topics[:5], decisions[:5]

    def generate_summary(
        self,
        conversation_id: str,
        older_messages: list[dict[str, Any]],
        existing_summary: Optional[ConversationSummaryRecord] = None,
    ) -> ConversationSummaryRecord:
        """Generate or update a compact summary representation of older conversation turns."""
        if not older_messages:
            if existing_summary:
                return existing_summary
            return ConversationSummaryRecord(
                conversation_id=conversation_id,
                summary="No previous conversation history.",
                messages_summarized_count=0,
                last_message_index=0,
                topics=[],
                decisions=[],
            )

        topics, decisions = self.extract_key_points(older_messages)

        # Build concise bullet points
        summary_lines: list[str] = ["CONVERSATION SUMMARY (Older turns):"]
        user_msgs = [m.get("content", "")[:100] for m in older_messages if m.get("role") == "user" and m.get("content")]
        if user_msgs:
            sample_topics = "; ".join(user_msgs[:4])
            summary_lines.append(f"- User inquired about: {sample_topics}")

        if decisions:
            summary_lines.append("- Key decisions / constraints: " + "; ".join(decisions[:3]))

        if topics:
            summary_lines.append("- Topics discussed: " + "; ".join(topics[:3]))

        summary_text = "\n".join(summary_lines)

        # Persist to database
        record = self.db.upsert_summary(
            conversation_id=conversation_id,
            summary=summary_text,
            messages_summarized_count=len(older_messages),
            last_message_index=len(older_messages) - 1,
            topics=topics,
            decisions=decisions,
        )
        logger.info("Generated conversation summary for %s (%d messages summarized)", conversation_id, len(older_messages))
        return record

    def get_summary_for_conversation(
        self,
        conversation_id: str,
    ) -> Optional[ConversationSummaryRecord]:
        """Retrieve stored summary from SQLite."""
        return self.db.get_summary(conversation_id)
