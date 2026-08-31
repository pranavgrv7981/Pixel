"""Central ContextManager coordinating candidate collection, ranking, budgeting, and envelope assembly."""

from datetime import datetime, timezone
import time
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.budget import ContextBudgetCalculator
from app.context.cache import ContextCache
from app.context.database import ContextDatabase
from app.context.models import (
    ContextBudget,
    ContextDiagnostics,
    ContextItem,
    ContextSource,
    ProjectContext,
    ResponseStyle,
    TrustLevel,
    UserProfile,
)
from app.context.profile import UserProfileManager
from app.context.project import ProjectContextManager
from app.context.ranker import ContextRanker, estimate_tokens
from app.context.sources import ContextSourceCollector
from app.context.summarizer import ConversationSummarizer

logger = get_logger("context.manager")


class ContextManager:
    """Central orchestrator for intelligent context selection, token budgeting, and personalization."""

    def __init__(
        self,
        db: Optional[ContextDatabase] = None,
        memory_manager: Optional[Any] = None,
        knowledge_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or ContextDatabase(settings=self.settings)
        self.cache = ContextCache(settings=self.settings)

        self.profile_manager = UserProfileManager(db=self.db, settings=self.settings)
        self.project_manager = ProjectContextManager(db=self.db, settings=self.settings)
        self.summarizer = ConversationSummarizer(db=self.db, settings=self.settings)
        self.ranker = ContextRanker()
        self.budget_calc = ContextBudgetCalculator(settings=self.settings)

        self.collector = ContextSourceCollector(
            memory_manager=memory_manager,
            knowledge_manager=knowledge_manager,
            profile_manager=self.profile_manager,
            project_manager=self.project_manager,
            summarizer=self.summarizer,
            ranker=self.ranker,
            settings=self.settings,
        )

        self._last_diagnostics: Optional[ContextDiagnostics] = None

    def initialize(self) -> None:
        """Idempotently initialize context database tables."""
        self.db.initialize()

    def get_last_diagnostics(self) -> Optional[ContextDiagnostics]:
        """Return diagnostics from the most recent context build operation."""
        return self._last_diagnostics

    def build_context(
        self,
        prompt: str,
        conversation_id: str,
        messages: list[dict[str, Any]],
        model_name: str = "qwen3:30b",
        model_capacity: int = 16384,
        system_prompt: Optional[str] = None,
        tool_schemas: Optional[list[dict[str, Any]]] = None,
        extra_context_items: Optional[list[ContextItem]] = None,
    ) -> tuple[list[dict[str, str]], ContextDiagnostics]:
        """Assemble an optimized, budgeted, and trust-boundary-enforced LLM message payload.

        Returns:
            (payload_for_ollama, diagnostics)
        """
        start_time = time.perf_counter()
        warnings: list[str] = []
        candidates: list[ContextItem] = []

        try:
            # 1. Collect Mandatory Current User Prompt
            prompt_item = self.collector.collect_current_prompt(prompt)
            candidates.append(prompt_item)

            # 2. Collect Active User Profile Item
            profile_item = self.profile_manager.get_context_item()
            if profile_item:
                candidates.append(profile_item)

            # 3. Collect Active Project Context Item
            active_proj = self.project_manager.get_active_project()
            project_item = self.project_manager.get_context_item()
            if project_item:
                candidates.append(project_item)

            # 4. Collect Recent Turns & Older Turn Summaries
            recent_items, summary_item = self.collector.collect_conversation_history(conversation_id, messages)
            candidates.extend(recent_items)
            if summary_item:
                candidates.append(summary_item)

            # 5. Collect Relevant Long-Term Memories
            mem_items = self.collector.collect_memories(prompt)
            candidates.extend(mem_items)

            # 6. Collect Relevant Knowledge (RAG) Chunks
            rag_items = self.collector.collect_knowledge(prompt)
            candidates.extend(rag_items)

            # 7. Collect Dynamic System Metrics if Query is System-Related
            sys_item = self.collector.collect_system_metrics(prompt)
            if sys_item:
                candidates.append(sys_item)

            # 8. Add any external/explicit caller items (e.g. active plan/task results)
            if extra_context_items:
                candidates.extend(extra_context_items)

            # 9. Rank Candidates by Priority and Semantic Relevance
            ranked_items = self.ranker.rank_candidates(
                query=prompt,
                candidates=candidates,
                active_project=active_proj,
            )

            # 10. Compute Model-Aware Token Budget
            budget = self.budget_calc.calculate_budget(
                model_capacity=model_capacity,
                system_prompt=system_prompt,
                tool_schemas=tool_schemas,
            )

            # 11. Pack Candidates Enforcing Budget & Granular Source Ceilings
            included, excluded = self.budget_calc.pack_items(ranked_items, budget)

        except Exception as err:
            logger.error("Context assembly encountered error; falling back to direct history: %s", err)
            warnings.append(f"Context error: {err}")
            # Safe degradation fallback: Return basic messages without crashing
            payload: list[dict[str, str]] = []
            if system_prompt:
                payload.append({"role": "system", "content": system_prompt})
            for m in messages:
                if m.get("content"):
                    payload.append({"role": m.get("role", "user"), "content": m.get("content", "")})
            if not messages or messages[-1].get("content") != prompt:
                payload.append({"role": "user", "content": prompt})

            diag = ContextDiagnostics(
                total_candidates=len(messages) + 1,
                included_items_count=len(payload),
                excluded_items_count=0,
                estimated_tokens=estimate_tokens(str(payload)),
                budget_tokens=model_capacity,
                source_breakdown={"fallback": len(payload)},
                warnings=warnings,
                latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
            self._last_diagnostics = diag
            return payload, diag

        # 12. Assemble Final LLM Message Payload
        payload = self._format_messages_payload(
            system_prompt=system_prompt,
            included_items=included,
            prompt=prompt,
        )

        # 13. Compile Diagnostics
        source_counts: dict[str, int] = {}
        relevance_map: dict[str, float] = {}
        for it in included:
            src_name = it.source.value
            source_counts[src_name] = source_counts.get(src_name, 0) + 1
            relevance_map[it.id] = it.relevance_score

        diag = ContextDiagnostics(
            total_candidates=len(candidates),
            included_items_count=len(included),
            excluded_items_count=len(excluded),
            estimated_tokens=budget.used_tokens + budget.system_prompt_tokens,
            budget_tokens=budget.available_input_tokens,
            source_breakdown=source_counts,
            relevance_scores=relevance_map,
            warnings=warnings,
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )
        self._last_diagnostics = diag

        logger.debug(
            "Context assembled in %.2fms: %d candidates -> %d included (%d tokens, budget: %d)",
            diag.latency_ms,
            diag.total_candidates,
            diag.included_items_count,
            diag.estimated_tokens,
            diag.budget_tokens,
        )

        return payload, diag

    def _format_messages_payload(
        self,
        system_prompt: Optional[str],
        included_items: list[ContextItem],
        prompt: str,
    ) -> list[dict[str, str]]:
        """Format included context items into structured Ollama system & conversation turns."""
        payload: list[dict[str, str]] = []

        # Separate items by section
        system_blocks: list[str] = []
        if system_prompt and system_prompt.strip():
            system_blocks.append(system_prompt.strip())

        reference_blocks: list[str] = []
        conversation_turns: list[dict[str, str]] = []

        for item in included_items:
            # System / Preference / Project blocks
            if item.source in (ContextSource.USER_PROFILE, ContextSource.PROJECT_CONTEXT, ContextSource.SYSTEM):
                system_blocks.append(item.content.strip())

            # Memory blocks
            elif item.source == ContextSource.MEMORY:
                system_blocks.append(item.content.strip())

            # Reference data (RAG knowledge / Browser)
            elif item.source in (ContextSource.KNOWLEDGE, ContextSource.BROWSER):
                reference_blocks.append(item.to_formatted_context())

            # Plan / Task execution blocks
            elif item.source in (ContextSource.PLAN, ContextSource.TASK, ContextSource.TOOL_RESULT):
                system_blocks.append(item.content.strip())

            # Older summary blocks
            elif item.source == ContextSource.CONVERSATION_SUMMARY:
                system_blocks.append(item.content.strip())

            # Recent conversation turns
            elif item.source == ContextSource.RECENT_CONVERSATION:
                role = item.metadata.get("role", "user")
                # Remove prefix if added by collector
                clean_content = item.content
                if clean_content.startswith(f"[{role.upper()}]: "):
                    clean_content = clean_content[len(role) + 4:]
                conversation_turns.append({"role": role, "content": clean_content})

        # Append reference blocks into system context if any
        if reference_blocks:
            system_blocks.append("\n\n".join(reference_blocks))

        # 1. Prepend single consolidated system message
        if system_blocks:
            payload.append({"role": "system", "content": "\n\n".join(system_blocks)})

        # 2. Append recent conversational messages
        payload.extend(conversation_turns)

        # 3. Ensure current user prompt is final message
        if not payload or payload[-1].get("content") != prompt:
            payload.append({"role": "user", "content": prompt})

        return payload
