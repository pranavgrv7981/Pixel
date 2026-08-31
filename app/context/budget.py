"""Model-aware context budgeting and token reservation engine."""

import json
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.models import ContextBudget, ContextItem, ContextSource
from app.context.ranker import estimate_tokens

logger = get_logger("context.budget")


class ContextBudgetCalculator:
    """Calculates model-aware token budgets and enforces granular source envelopes."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def get_source_limit(self, source: ContextSource) -> int:
        """Get the configured maximum token ceiling for a specific context source."""
        limits = {
            ContextSource.CURRENT_MESSAGE: self.settings.max_conversation_context_tokens,
            ContextSource.RECENT_CONVERSATION: self.settings.max_conversation_context_tokens,
            ContextSource.CONVERSATION_SUMMARY: self.settings.max_conversation_context_tokens // 2,
            ContextSource.MEMORY: self.settings.max_memory_context_tokens,
            ContextSource.KNOWLEDGE: self.settings.max_knowledge_context_tokens,
            ContextSource.TOOL_RESULT: self.settings.max_tool_context_tokens,
            ContextSource.BROWSER: self.settings.max_tool_context_tokens,
            ContextSource.PLAN: self.settings.max_tool_context_tokens,
            ContextSource.TASK: self.settings.max_tool_context_tokens // 2,
            ContextSource.SYSTEM: self.settings.max_system_context_tokens,
            ContextSource.USER_PROFILE: 256,
            ContextSource.PROJECT_CONTEXT: 256,
        }
        return limits.get(source, 1024)

    def calculate_budget(
        self,
        model_capacity: int = 16384,
        system_prompt: Optional[str] = None,
        tool_schemas: Optional[list[dict[str, Any]]] = None,
    ) -> ContextBudget:
        """Calculate the available net token budget for context items."""
        # 1. System prompt tokens
        sys_tokens = estimate_tokens(system_prompt or "") if system_prompt else 0

        # 2. Tool schemas tokens
        tools_str = json.dumps(tool_schemas) if tool_schemas else ""
        tools_tokens = estimate_tokens(tools_str) if tools_str else 0

        # 3. Response reserve (min 512, default 2048)
        reserve = max(512, self.settings.response_token_reserve)

        # 4. Effective net input capacity
        net_capacity = max(512, model_capacity - sys_tokens - tools_tokens - reserve)
        # Bounded by global max_context_tokens ceiling if configured
        final_input_budget = min(net_capacity, self.settings.max_context_tokens)

        return ContextBudget(
            total_model_capacity=model_capacity,
            system_prompt_tokens=sys_tokens,
            tool_schemas_tokens=tools_tokens,
            response_reserve_tokens=reserve,
            available_input_tokens=final_input_budget,
            used_tokens=0,
            source_allocations={},
        )

    def pack_items(
        self,
        ranked_items: list[ContextItem],
        budget: ContextBudget,
    ) -> tuple[list[ContextItem], list[ContextItem]]:
        """Pack candidate items into the budget, enforcing source limits and mandatory items.

        Returns:
            (included_items, excluded_items)
        """
        included: list[ContextItem] = []
        excluded: list[ContextItem] = []

        source_usage: dict[str, int] = {}
        total_used = 0

        # Pass 1: Mandatory items always included regardless of soft limits
        non_mandatory: list[ContextItem] = []
        for item in ranked_items:
            tokens = item.estimated_tokens or estimate_tokens(item.content)
            item.estimated_tokens = tokens
            if item.is_mandatory:
                included.append(item)
                total_used += tokens
                source_usage[item.source.value] = source_usage.get(item.source.value, 0) + tokens
            else:
                non_mandatory.append(item)

        # Pass 2: Fill remaining budget with highest-ranked optional items
        for item in non_mandatory:
            tokens = item.estimated_tokens
            src_val = item.source.value
            src_limit = self.get_source_limit(item.source)
            current_src_usage = source_usage.get(src_val, 0)

            # Check global input budget
            if total_used + tokens > budget.available_input_tokens:
                logger.debug("Evicting item %s: exceeds global budget (%d + %d > %d)", item.id, total_used, tokens, budget.available_input_tokens)
                excluded.append(item)
                continue

            # Check source category limit
            if current_src_usage + tokens > src_limit:
                logger.debug("Evicting item %s: exceeds source %s limit (%d + %d > %d)", item.id, src_val, current_src_usage, tokens, src_limit)
                excluded.append(item)
                continue

            # Item accepted
            included.append(item)
            total_used += tokens
            source_usage[src_val] = current_src_usage + tokens

        budget.used_tokens = total_used
        budget.source_allocations = source_usage

        return included, excluded
