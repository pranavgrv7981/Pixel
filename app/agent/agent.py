from typing import Any, Iterator, Optional
import uuid

from app.agent.conversation import Conversation, Role
from app.agent.intelligence_models import (
    ActionType,
    AgentState,
    AgentTelemetryRecord,
    AutonomyLevel,
    RequestIntent,
)
from app.agent.intent import IntentAnalyzer
from app.agent.quality import ResponseQualityEvaluator
from app.agent.recovery import FailureRecoveryManager
from app.agent.telemetry import AgentQualityTracker
from app.agent.tool_selector import CapabilityToolSelector
from app.agent.verifier import ActionVerifier
from app.agent.fast_path import FastPathEngine
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidMessageError,
    ToolRoundLimitError,
    ToolValidationError,
)
from app.core.logging import get_logger
from app.core.ollama_client import ModelResponse, OllamaClient
from app.models.profiles import ModelRole
from app.models.selector import RequestCategory
from app.security.manager import PermissionManager
from app.security.permissions import ExecutionContext
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

logger = get_logger("agent")


class Agent:
    """Orchestrates multi-turn conversation, intelligent intent understanding, tool discovery, security permissions, and response synthesis."""

    def __init__(
        self,
        conversation: Optional[Conversation] = None,
        client: Optional[OllamaClient] = None,
        registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        memory_manager: Optional[Any] = None,
        planner: Optional[Any] = None,
        plan_executor: Optional[Any] = None,
        router: Optional[Any] = None,
        context_manager: Optional[Any] = None,
        intent_analyzer: Optional[IntentAnalyzer] = None,
        tool_selector: Optional[CapabilityToolSelector] = None,
        verifier: Optional[ActionVerifier] = None,
        recovery_manager: Optional[FailureRecoveryManager] = None,
        quality_evaluator: Optional[ResponseQualityEvaluator] = None,
        telemetry: Optional[AgentQualityTracker] = None,
        autonomy_level: Optional[AutonomyLevel] = None,
        metrics_tracker: Optional[Any] = None,
        max_rounds: Optional[int] = None,
        settings: Optional[Settings] = None,
        on_tool_start: Optional[Any] = None,
        on_tool_end: Optional[Any] = None,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        self.client: OllamaClient = client or OllamaClient(settings=self.settings)
        self.registry: ToolRegistry = registry or ToolRegistry()
        self.permission_manager: PermissionManager = permission_manager or PermissionManager(settings=self.settings)
        self.memory_manager = memory_manager
        self.planner = planner
        self.plan_executor = plan_executor
        self.router = router
        self.context_manager = context_manager
        self.metrics_tracker = metrics_tracker
        self.last_routing_decision: Optional[Any] = None
        self.last_intent: Optional[RequestIntent] = None
        self.fast_path: FastPathEngine = FastPathEngine(
            registry=self.registry,
            memory_manager=self.memory_manager,
            permission_manager=self.permission_manager,
        )

        # Phase 18 Intelligence Subsystems
        self.intent_analyzer: IntentAnalyzer = intent_analyzer or IntentAnalyzer()
        self.tool_selector: CapabilityToolSelector = tool_selector or CapabilityToolSelector(registry=self.registry)
        self.verifier: ActionVerifier = verifier or ActionVerifier()
        self.recovery_manager: FailureRecoveryManager = recovery_manager or FailureRecoveryManager(
            max_retries=getattr(self.settings, "max_tool_retries", 2),
            max_repetitions=getattr(self.settings, "max_repetition_count", 2),
        )
        self.quality_evaluator: ResponseQualityEvaluator = quality_evaluator or ResponseQualityEvaluator()
        self.telemetry: AgentQualityTracker = telemetry or AgentQualityTracker(settings=self.settings)
        try:
            self.telemetry.initialize()
        except Exception:
            pass

        raw_autonomy = getattr(self.settings, "autonomy_level", "confirm_actions")
        self.autonomy_level: AutonomyLevel = autonomy_level or AutonomyLevel(raw_autonomy)

        self.conversation: Conversation = conversation or Conversation(
            system_prompt=self.settings.system_prompt,
            max_messages=self.settings.max_conversation_messages,
            repository=memory_manager.conversations if memory_manager else None,
        )

        self.max_rounds: int = max_rounds or self.settings.max_tool_call_rounds
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end

    def plan_and_execute(self, goal: str, interactive: bool = True) -> Any:
        """Decompose a complex goal into a multi-step plan and sequentially execute it."""
        if not self.planner or not self.plan_executor:
            raise ValueError("Planning subsystem is not configured on this Agent.")
        plan = self.planner.create_plan(goal)
        return self.plan_executor.execute_plan(plan, interactive=interactive)




    def _process_tool_call(self, tc: dict[str, Any], interactive: bool = False) -> tuple[str, ToolResult]:
        """Validate, evaluate security permissions for, and execute a tool call."""
        tool_name = tc.get("name", "")
        args = tc.get("arguments", {})

        logger.info("Evaluating tool call '%s' with args: %s", tool_name, args)

        # 1. Tool lookup in registry
        if not self.registry.has(tool_name):
            logger.warning("Requested tool '%s' not found in registry", tool_name)
            return tool_name, ToolResult(success=False, error=f"Tool '{tool_name}' not found in registry")

        tool = self.registry.get(tool_name)

        # 2. Parameter validation
        try:
            validated_args = tool.validate_args(args)
        except ToolValidationError as err:
            logger.warning("Argument validation failed for tool '%s': %s", tool_name, err)
            return tool_name, ToolResult(success=False, error=f"Argument validation failed: {err}")

        # 3. Centralized Permission & Security Check
        ctx = ExecutionContext(
            tool_name=tool.name,
            arguments=validated_args,
            risk_level=tool.risk_level,
            source="agent",
            interactive=interactive,
        )
        allowed, reason, _ = self.permission_manager.request_permission(tool, validated_args, ctx)
        if not allowed:
            logger.warning("Execution of tool '%s' denied by security: %s", tool_name, reason)
            return tool_name, ToolResult(
                success=False,
                error=f"Tool execution denied by safety policy: {reason}",
            )

        # 4. Safe Execution (only permitted if validation and security policy allow)
        if callable(self.on_tool_start):
            try:
                self.on_tool_start(tool_name, validated_args)
            except Exception as err:
                logger.warning("Error in on_tool_start callback: %s", err)

        result = tool.execute(validated_args)

        if callable(self.on_tool_end):
            try:
                self.on_tool_end(tool_name, result)
            except Exception as err:
                logger.warning("Error in on_tool_end callback: %s", err)

        return tool_name, result


    def run(self, prompt: str, model: Optional[str] = None, interactive: bool = False, images: Optional[list[Any]] = None) -> str:
        """Process a user prompt through the intelligence decision pipeline."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidMessageError("User prompt cannot be empty or whitespace-only")

        import time
        start_time = time.perf_counter()
        interaction_id = str(uuid.uuid4())
        total_tool_calls = 0
        total_retries = 0
        tool_executions_log: list[dict[str, Any]] = []
        false_completion_prevented = False

        self.recovery_manager.clear_history()
        self.conversation.add_user_message(prompt)

        # 0. FAST PATH: Deterministic Execution Bypass
        if not images and self.fast_path and getattr(self.settings, "enable_fast_path", True):
            fast_res = self.fast_path.try_execute(prompt)
            if fast_res is not None:
                self.conversation.add_assistant_message(fast_res)
                latency = time.perf_counter() - start_time
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category="fast_path",
                        action_type="fast_path",
                        model_name="pixel-fast-path",
                        tool_count=0,
                        retries_count=0,
                        success=True,
                        goal_achieved=True,
                        latency_seconds=latency,
                        false_completion_prevented=False,
                    )
                )
                logger.info("FastPath executed for prompt '%s' in %.2fms", prompt[:40], latency * 1000)
                return fast_res

        # 1. UNDERSTAND & CLASSIFY INTENT
        intent = self.intent_analyzer.analyze(prompt)
        self.last_intent = intent
        logger.info("Analyzed intent: goal='%s', action_type=%s, category=%s", intent.normalized_goal, intent.action_type.value, intent.category)

        # 2. DECIDE: Direct Clarification Path
        if intent.action_type == ActionType.CLARIFICATION and not images:
            clarification_msg = intent.clarification_prompt or "Could you please clarify your request?"
            self.conversation.add_assistant_message(clarification_msg)
            latency = time.perf_counter() - start_time
            self.telemetry.record(
                AgentTelemetryRecord(
                    interaction_id=interaction_id,
                    intent_category=intent.category,
                    action_type=intent.action_type.value,
                    model_name=model or self.client.default_model,
                    tool_count=0,
                    retries_count=0,
                    success=True,
                    goal_achieved=True,
                    latency_seconds=latency,
                    false_completion_prevented=False,
                )
            )
            return clarification_msg

        # 3. DECIDE: Multi-Step Autonomous Planning Path
        if intent.action_type == ActionType.PLAN and self.planner and self.plan_executor:
            try:
                plan_result = self.plan_and_execute(prompt, interactive=interactive)
                plan_summary = f"Execution plan completed.\n\n{plan_result}"
                self.conversation.add_assistant_message(plan_summary)
                latency = time.perf_counter() - start_time
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category=intent.category,
                        action_type=intent.action_type.value,
                        model_name=model or self.client.default_model,
                        tool_count=1,
                        retries_count=0,
                        success=True,
                        goal_achieved=True,
                        latency_seconds=latency,
                        false_completion_prevented=False,
                    )
                )
                return plan_summary
            except Exception as plan_err:
                logger.warning("Planning execution failed: %s; continuing with standard agent loop", plan_err)

        # 4. MEMORY & CONTEXT RESOLUTION
        extra_context = None
        if self.memory_manager and (intent.requires_memory or getattr(self.settings, "context_management_enabled", True)):
            try:
                relevant_mems = self.memory_manager.get_relevant_memories(prompt)
                if relevant_mems:
                    extra_context = self.memory_manager.format_memories_for_prompt(relevant_mems)
                    logger.info("Injected %d relevant persistent memories into context", len(relevant_mems))
            except Exception as err:
                logger.warning("Could not retrieve relevant memories: %s", err)

        # 5. MODEL ROUTING
        target_model = model
        routing_decision = None
        if self.router:
            raw_ctx = " ".join(
                m.get("content", "")
                for m in self.conversation.get_messages_for_llm(extra_system_context=extra_context)
            )
            ctx_bytes = len(raw_ctx.encode("utf-8"))
            routing_decision = self.router.route_request(
                prompt,
                has_images=bool(images),
                explicit_mode=model,
                context_bytes=ctx_bytes,
            )
            target_model = routing_decision.selected_model
            self.last_routing_decision = routing_decision

        # If images were provided but no vision model is available, gracefully inform user
        if images and not target_model:
            no_vision_msg = "Vision analysis is unavailable: No vision-capable local model (e.g. LLaVA, MiniCPM-V, or Qwen2.5-VL) is installed on your local Ollama server."
            self.conversation.add_assistant_message(no_vision_msg)
            return no_vision_msg

        # 6. CAPABILITY-AWARE TOOL SELECTION
        all_schemas = self.registry.get_schemas() if self.registry.list() else None
        tools_schema, tool_decision = self.tool_selector.select_tools(intent, all_schemas)

        round_idx = 0
        while round_idx < self.max_rounds:
            round_idx += 1

            if self.context_manager and getattr(self.settings, "context_management_enabled", True):
                raw_msgs = [m.to_dict() for m in self.conversation.get_messages()]
                payload, diag = self.context_manager.build_context(
                    prompt=prompt,
                    conversation_id=self.conversation.id,
                    messages=raw_msgs,
                    model_name=target_model or self.client.default_model,
                    model_capacity=getattr(routing_decision, "model_capacity", 16384) if routing_decision else 16384,
                    system_prompt=self.settings.system_prompt,
                    tool_schemas=tools_schema,
                )
            else:
                payload = self.conversation.get_messages_for_llm(extra_system_context=extra_context)

            if images and payload and round_idx == 1:
                b64_list = [
                    img.base64_data if hasattr(img, "base64_data") and img.base64_data else str(img)
                    for img in images
                ]
                payload[-1]["images"] = b64_list

            logger.debug(
                "Round %d: requesting model response with %d messages and %d tools (model=%s)",
                round_idx,
                len(payload),
                len(tools_schema) if tools_schema else 0,
                target_model,
            )

            response: ModelResponse = self.client.chat(payload, model=target_model, tools=tools_schema)

            # Check if model returned direct response
            if not response.has_tool_calls:
                content = str(response)

                # 7. RESPONSE QUALITY EVALUATION & FALSE COMPLETION PROTECTION
                eval_res = self.quality_evaluator.evaluate(
                    response_text=content,
                    tool_executions=tool_executions_log,
                    goal=prompt,
                )
                final_content = eval_res.sanitized_content or content
                self.conversation.add_assistant_message(final_content)

                # Record Telemetry
                latency = time.perf_counter() - start_time
                if self.metrics_tracker and routing_decision:
                    self.metrics_tracker.record_usage(
                        model_name=target_model or self.client.default_model,
                        role=routing_decision.role,
                        category=routing_decision.category,
                        latency_seconds=latency,
                        tool_calls_count=total_tool_calls,
                        success=True,
                        is_fallback=routing_decision.is_fallback,
                    )
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category=intent.category,
                        action_type=intent.action_type.value,
                        model_name=target_model or self.client.default_model,
                        tool_count=total_tool_calls,
                        retries_count=total_retries,
                        success=True,
                        goal_achieved=True,
                        latency_seconds=latency,
                        false_completion_prevented=eval_res.false_completion_detected,
                    )
                )

                return final_content

            # Handle Tool Calls
            logger.info("Round %d: model requested %d tool calls", round_idx, len(response.tool_calls))
            self.conversation.add_assistant_message(content=response.content, tool_calls=response.tool_calls)

            for tc in response.tool_calls:
                total_tool_calls += 1
                tool_name = tc.get("name", "")
                args = tc.get("arguments", {})

                # Check Argument Plausibility
                is_plausible, plaus_reason = self.tool_selector.validate_argument_plausibility(tool_name, args)
                if not is_plausible:
                    err_msg = f"Argument plausibility check failed: {plaus_reason}"
                    self.conversation.add_tool_message(content=err_msg, name=tool_name)
                    tool_executions_log.append({"tool": tool_name, "success": False, "error": err_msg})
                    continue

                tool_name, result = self._process_tool_call(tc, interactive=interactive)

                # Check Repetition & Loop Prevention
                err_text = result.error or ""
                is_loop = self.recovery_manager.record_and_check_repetition(tool_name, args, err_text)
                if is_loop:
                    loop_err = f"Repeated tool execution loop detected for '{tool_name}'. Halting retries."
                    self.conversation.add_tool_message(content=loop_err, name=tool_name)
                    tool_executions_log.append({"tool": tool_name, "success": False, "error": loop_err})
                    continue

                # Action Verification
                verification = self.verifier.verify_tool_action(tool_name, args, result)
                tool_executions_log.append({
                    "tool": tool_name,
                    "success": result.success and verification.goal_achieved,
                    "error": result.error if not result.success else "",
                    "verified": verification.verified,
                })

                if not result.success:
                    assessment = self.recovery_manager.assess_failure(tool_name, args, err_text)
                    if assessment.is_retryable:
                        total_retries += 1

                # Record tool result in conversation
                self.conversation.add_tool_message(
                    content=result.to_llm_content(),
                    name=tool_name,
                )

        logger.error("Agent reached maximum tool call rounds limit (%d)", self.max_rounds)
        raise ToolRoundLimitError(
            f"Exceeded maximum tool-call rounds limit ({self.max_rounds}) without final response"
        )

    def stream_run(self, prompt: str, model: Optional[str] = None, interactive: bool = False, images: Optional[list[Any]] = None) -> Iterator[str]:
        """Stream final response tokens after completing any intermediate tool rounds."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidMessageError("User prompt cannot be empty or whitespace-only")

        import time
        start_time = time.perf_counter()
        interaction_id = str(uuid.uuid4())
        total_tool_calls = 0
        total_retries = 0
        tool_executions_log: list[dict[str, Any]] = []
        false_completion_prevented = False

        self.recovery_manager.clear_history()
        self.conversation.add_user_message(prompt)

        # 0. FAST PATH: Deterministic Execution Bypass
        if not images and self.fast_path and getattr(self.settings, "enable_fast_path", True):
            fast_res = self.fast_path.try_execute(prompt)
            if fast_res is not None:
                self.conversation.add_assistant_message(fast_res)
                latency = time.perf_counter() - start_time
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category="fast_path",
                        action_type="fast_path",
                        model_name="pixel-fast-path",
                        tool_count=0,
                        retries_count=0,
                        success=True,
                        goal_achieved=True,
                        latency_seconds=latency,
                        false_completion_prevented=False,
                    )
                )
                logger.info("FastPath executed for prompt '%s' in %.2fms", prompt[:40], latency * 1000)
                yield fast_res
                return

        # 1. UNDERSTAND & CLASSIFY INTENT
        intent = self.intent_analyzer.analyze(prompt)
        self.last_intent = intent
        logger.debug("stream_run intent: goal='%s', action=%s", intent.normalized_goal, intent.action_type.value)

        # 2. DECIDE: Direct Clarification Path
        if intent.action_type == ActionType.CLARIFICATION and not images:
            clarification_msg = intent.clarification_prompt or "Could you please clarify your request?"
            self.conversation.add_assistant_message(clarification_msg)
            latency = time.perf_counter() - start_time
            self.telemetry.record(
                AgentTelemetryRecord(
                    interaction_id=interaction_id,
                    intent_category=intent.category,
                    action_type=intent.action_type.value,
                    model_name=model or self.client.default_model,
                    tool_count=0,
                    retries_count=0,
                    success=True,
                    goal_achieved=True,
                    latency_seconds=latency,
                    false_completion_prevented=False,
                )
            )
            yield clarification_msg
            return

        # 3. MEMORY & CONTEXT RESOLUTION
        extra_context = None
        if self.memory_manager and (intent.requires_memory or getattr(self.settings, "context_management_enabled", True)):
            try:
                relevant_mems = self.memory_manager.get_relevant_memories(prompt)
                if relevant_mems:
                    extra_context = self.memory_manager.format_memories_for_prompt(relevant_mems)
                    logger.info("Injected %d relevant persistent memories into context", len(relevant_mems))
            except Exception as err:
                logger.warning("Could not retrieve relevant memories: %s", err)

        # 4. MODEL ROUTING
        target_model = model
        routing_decision = None
        if self.router:
            raw_ctx = " ".join(
                m.get("content", "")
                for m in self.conversation.get_messages_for_llm(extra_system_context=extra_context)
            )
            ctx_bytes = len(raw_ctx.encode("utf-8"))
            routing_decision = self.router.route_request(
                prompt,
                has_images=bool(images),
                explicit_mode=model,
                context_bytes=ctx_bytes,
            )
            target_model = routing_decision.selected_model
            self.last_routing_decision = routing_decision

        # If images were provided but no vision model is available, gracefully inform user
        if images and not target_model:
            no_vision_msg = "Vision analysis is unavailable: No vision-capable local model (e.g. LLaVA, MiniCPM-V, or Qwen2.5-VL) is installed on your local Ollama server."
            self.conversation.add_assistant_message(no_vision_msg)
            yield no_vision_msg
            return

        # 5. CAPABILITY-AWARE TOOL SELECTION
        all_schemas = self.registry.get_schemas() if self.registry.list() else None
        tools_schema, tool_decision = self.tool_selector.select_tools(intent, all_schemas)

        round_idx = 0
        while round_idx < self.max_rounds:
            round_idx += 1

            if self.context_manager and getattr(self.settings, "context_management_enabled", True):
                raw_msgs = [m.to_dict() for m in self.conversation.get_messages()]
                payload, diag = self.context_manager.build_context(
                    prompt=prompt,
                    conversation_id=self.conversation.id,
                    messages=raw_msgs,
                    model_name=target_model or self.client.default_model,
                    model_capacity=getattr(routing_decision, "model_capacity", 16384) if routing_decision else 16384,
                    system_prompt=self.settings.system_prompt,
                    tool_schemas=tools_schema,
                )
            else:
                payload = self.conversation.get_messages_for_llm(extra_system_context=extra_context)

            if images and payload and round_idx == 1:
                b64_list = [
                    img.base64_data if hasattr(img, "base64_data") and img.base64_data else str(img)
                    for img in images
                ]
                payload[-1]["images"] = b64_list

            # Optimization for direct answers with no tools:
            # Stream directly token-by-token from Ollama for lowest TTFT
            if tools_schema is None or intent.action_type == ActionType.ANSWER:
                accumulated_tokens: list[str] = []
                is_fast_role = (routing_decision and routing_decision.role == ModelRole.FAST) or intent.action_type == ActionType.ANSWER
                fast_options = {"num_ctx": 2048, "num_predict": 256, "temperature": 0.3} if is_fast_role else None
                use_think = False if is_fast_role else True

                try:
                    for token in self.client.stream_chat(payload, model=target_model, options=fast_options, think=use_think):
                        accumulated_tokens.append(str(token))
                        yield str(token)
                except Exception as stream_err:
                    logger.warning("Streaming chat error: %s; falling back to non-streaming chat()", stream_err)

                # If stream_chat yielded nothing (e.g. mocked client only configured with chat()), fallback to chat()
                if not accumulated_tokens:
                    try:
                        resp_obj = self.client.chat(payload, model=target_model)
                        resp_str = str(resp_obj)
                        if resp_str:
                            accumulated_tokens.append(resp_str)
                            yield resp_str
                    except Exception as chat_err:
                        logger.error("Fallback chat() failed: %s", chat_err)
                        err_notice = f"I was unable to complete the request: {chat_err}"
                        accumulated_tokens.append(err_notice)
                        yield err_notice

                content = "".join(accumulated_tokens)
                eval_res = self.quality_evaluator.evaluate(response_text=content, tool_executions=[], goal=prompt)
                final_content = eval_res.sanitized_content or content
                self.conversation.add_assistant_message(final_content)

                # Record Telemetry
                latency = time.perf_counter() - start_time
                if self.metrics_tracker and routing_decision:
                    self.metrics_tracker.record_usage(
                        model_name=target_model or self.client.default_model,
                        role=routing_decision.role,
                        category=routing_decision.category,
                        latency_seconds=latency,
                        tool_calls_count=total_tool_calls,
                        success=True,
                        is_fallback=routing_decision.is_fallback,
                    )
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category=intent.category,
                        action_type=intent.action_type.value,
                        model_name=target_model or self.client.default_model,
                        tool_count=0,
                        retries_count=0,
                        success=True,
                        goal_achieved=True,
                        latency_seconds=latency,
                        false_completion_prevented=False,
                    )
                )
                return

            response: ModelResponse = self.client.chat(payload, model=target_model, tools=tools_schema)

            if not response.has_tool_calls:
                # Final response reached: evaluate quality and yield content
                content = str(response)
                eval_res = self.quality_evaluator.evaluate(
                    response_text=content,
                    tool_executions=tool_executions_log,
                    goal=prompt,
                )
                final_content = eval_res.sanitized_content or content
                if eval_res.false_completion_detected:
                    false_completion_prevented = True

                self.conversation.add_assistant_message(final_content)

                latency = time.perf_counter() - start_time
                if self.metrics_tracker and routing_decision:
                    self.metrics_tracker.record_usage(
                        model_name=target_model or self.client.default_model,
                        role=routing_decision.role,
                        category=routing_decision.category,
                        latency_seconds=latency,
                        tool_calls_count=total_tool_calls,
                        success=True,
                        is_fallback=routing_decision.is_fallback,
                    )
                self.telemetry.record(
                    AgentTelemetryRecord(
                        interaction_id=interaction_id,
                        intent_category=intent.category,
                        action_type=intent.action_type.value,
                        model_name=target_model or self.client.default_model,
                        tool_count=total_tool_calls,
                        retries_count=total_retries,
                        success=True,
                        goal_achieved=eval_res.passed,
                        latency_seconds=latency,
                        false_completion_prevented=false_completion_prevented,
                    )
                )
                yield final_content
                return

            # Execute Tool Calls
            logger.debug("Round %d: executing %d tool calls", round_idx, len(response.tool_calls))
            self.conversation.add_assistant_message(content=response.content, tool_calls=response.tool_calls)

            for tc in response.tool_calls:
                total_tool_calls += 1
                tool_name = tc.get("name", "")
                args = tc.get("arguments", {})

                is_plausible, plaus_reason = self.tool_selector.validate_argument_plausibility(tool_name, args)
                if not is_plausible:
                    err_msg = f"Argument plausibility check failed: {plaus_reason}"
                    self.conversation.add_tool_message(content=err_msg, name=tool_name)
                    tool_executions_log.append({"tool": tool_name, "success": False, "error": err_msg})
                    continue

                tool_name, result = self._process_tool_call(tc, interactive=interactive)

                err_text = result.error or ""
                is_loop = self.recovery_manager.record_and_check_repetition(tool_name, args, err_text)
                if is_loop:
                    loop_err = f"Repeated tool execution loop detected for '{tool_name}'. Halting retries."
                    self.conversation.add_tool_message(content=loop_err, name=tool_name)
                    tool_executions_log.append({"tool": tool_name, "success": False, "error": loop_err})
                    continue

                verification = self.verifier.verify_tool_action(tool_name, args, result)
                tool_executions_log.append({
                    "tool": tool_name,
                    "success": result.success and verification.goal_achieved,
                    "error": result.error if not result.success else "",
                    "verified": verification.verified,
                })

                if not result.success:
                    assessment = self.recovery_manager.assess_failure(tool_name, args, err_text)
                    if assessment.is_retryable:
                        total_retries += 1

                self.conversation.add_tool_message(
                    content=result.to_llm_content(),
                    name=tool_name,
                )

        raise ToolRoundLimitError(f"Exceeded maximum tool-call rounds limit ({self.max_rounds})")

