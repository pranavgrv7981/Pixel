"""Source candidate collector harvesting context items across all assistant subsystems."""

from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.models import (
    ContextItem,
    ContextSource,
    ProjectContext,
    TrustLevel,
    UserProfile,
)
from app.context.profile import UserProfileManager
from app.context.project import ProjectContextManager
from app.context.ranker import ContextRanker, estimate_tokens
from app.context.summarizer import ConversationSummarizer

logger = get_logger("context.sources")


class ContextSourceCollector:
    """Collects raw context candidate items from conversations, memory, knowledge, and system state."""

    def __init__(
        self,
        memory_manager: Optional[Any] = None,
        knowledge_manager: Optional[Any] = None,
        profile_manager: Optional[UserProfileManager] = None,
        project_manager: Optional[ProjectContextManager] = None,
        summarizer: Optional[ConversationSummarizer] = None,
        ranker: Optional[ContextRanker] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.profile_manager = profile_manager or UserProfileManager(settings=self.settings)
        self.project_manager = project_manager or ProjectContextManager(settings=self.settings)
        self.summarizer = summarizer or ConversationSummarizer(settings=self.settings)
        self.ranker = ranker or ContextRanker()

    def collect_current_prompt(self, prompt: str) -> ContextItem:
        """Create the mandatory current user prompt context item."""
        return ContextItem(
            source=ContextSource.CURRENT_MESSAGE,
            category="prompt",
            content=prompt,
            relevance_score=1.0,
            priority=1,
            trust_level=TrustLevel.USER,
            estimated_tokens=estimate_tokens(prompt),
            is_mandatory=True,
        )

    def collect_conversation_history(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> tuple[list[ContextItem], Optional[ContextItem]]:
        """Collect recent conversational turns and optional compact summary for older turns."""
        items: list[ContextItem] = []
        summary_item: Optional[ContextItem] = None

        if not messages:
            return items, summary_item

        recent_count = self.settings.recent_messages_count
        if len(messages) <= recent_count:
            recent_msgs = messages
            older_msgs = []
        else:
            recent_msgs = messages[-recent_count:]
            older_msgs = messages[:-recent_count]

        # 1. Recent messages
        for idx, m in enumerate(recent_msgs):
            content = m.get("content", "")
            if not content:
                continue
            role = m.get("role", "user")
            trust = TrustLevel.USER if role == "user" else TrustLevel.MODEL_GENERATED
            items.append(
                ContextItem(
                    source=ContextSource.RECENT_CONVERSATION,
                    category=f"turn_{role}",
                    content=f"[{role.upper()}]: {content}",
                    priority=5,
                    trust_level=trust,
                    estimated_tokens=estimate_tokens(content),
                    metadata={"index": idx, "role": role},
                )
            )

        # 2. Older messages summarization if beyond threshold
        if older_msgs and self.summarizer.should_summarize(len(messages)):
            try:
                rec = self.summarizer.get_summary_for_conversation(conversation_id)
                if not rec or rec.messages_summarized_count < len(older_msgs):
                    rec = self.summarizer.generate_summary(conversation_id, older_msgs, existing_summary=rec)

                if rec and rec.summary:
                    summary_item = ContextItem(
                        source=ContextSource.CONVERSATION_SUMMARY,
                        category="history_summary",
                        content=rec.summary,
                        relevance_score=0.45,
                        priority=7,
                        trust_level=TrustLevel.MODEL_GENERATED,
                        estimated_tokens=estimate_tokens(rec.summary),
                        metadata={"summarized_count": rec.messages_summarized_count},
                    )
            except Exception as err:
                logger.warning("Failed to collect/generate conversation summary for %s: %s", conversation_id, err)

        return items, summary_item

    def collect_memories(self, prompt: str) -> list[ContextItem]:
        """Harvest relevant long-term memories using bounded search tokens."""
        if not self.memory_manager:
            return []

        try:
            records = self.memory_manager.get_relevant_memories(prompt)
            if not records:
                return []

            items: list[ContextItem] = []
            for rec in records:
                content_str = f"MEMORY ({rec.category.value}): {rec.key} = {rec.value}"
                items.append(
                    ContextItem(
                        source=ContextSource.MEMORY,
                        category=rec.category.value.lower(),
                        content=content_str,
                        priority=4,
                        trust_level=TrustLevel.MEMORY,
                        estimated_tokens=estimate_tokens(content_str),
                        metadata={"key": rec.key, "importance": rec.importance},
                    )
                )
            return items
        except Exception as err:
            logger.warning("Failed to collect relevant memories: %s", err)
            return []

    def collect_knowledge(self, prompt: str) -> list[ContextItem]:
        """Harvest relevant RAG chunks if KnowledgeManager is enabled."""
        if not self.knowledge_manager or not hasattr(self.knowledge_manager, "retriever"):
            return []

        try:
            # Query top 3 chunks with minimum relevance threshold of 0.35
            scored_chunks = self.knowledge_manager.retriever.search(
                query=prompt,
                top_k=3,
                min_score=0.35,
            )
            if not scored_chunks:
                return []

            items: list[ContextItem] = []
            for sc in scored_chunks:
                chunk = sc.chunk
                chunk_txt = getattr(chunk, "text", None) or getattr(chunk, "content", "")
                content_str = f"[DOCUMENT CHUNK (doc_id={chunk.document_id}, chunk_id={chunk.chunk_id})]: {chunk_txt}"
                items.append(
                    ContextItem(
                        source=ContextSource.KNOWLEDGE,
                        category="rag_reference",
                        content=content_str,
                        relevance_score=sc.score,
                        priority=6,
                        trust_level=TrustLevel.KNOWLEDGE,
                        estimated_tokens=estimate_tokens(content_str),
                        metadata={"score": sc.score, "document_id": chunk.document_id},
                    )
                )
            return items
        except Exception as err:
            logger.warning("Failed to collect RAG knowledge: %s", err)
            return []

    def collect_system_metrics(self, prompt: str) -> Optional[ContextItem]:
        """Collect lightweight hardware/system state ONLY if query is system-related."""
        if not self.settings.auto_system_context_enabled:
            return None

        if not self.ranker.is_system_query(prompt):
            return None

        try:
            import psutil
            import platform

            ram = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.05)
            lines = [
                "SYSTEM STATE METRICS:",
                f"- OS: {platform.system()} {platform.release()} ({platform.machine()})",
                f"- CPU Usage: {cpu_percent}%",
                f"- Memory: {ram.used / (1024**3):.2f} GB used / {ram.total / (1024**3):.2f} GB total ({ram.percent}% used)",
            ]
            content_str = "\n".join(lines)
            return ContextItem(
                source=ContextSource.SYSTEM,
                category="system_metrics",
                content=content_str,
                relevance_score=0.90,
                priority=3,
                trust_level=TrustLevel.SYSTEM,
                estimated_tokens=estimate_tokens(content_str),
            )
        except Exception as err:
            logger.debug("System metrics collection skipped: %s", err)
            return None
