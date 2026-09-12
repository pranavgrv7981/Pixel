"""Background QThread worker executing the Agent loop without freezing the Qt UI thread."""

import time
from typing import Any, Optional
from PySide6.QtCore import QThread, Signal

from app.agent.agent import Agent
from app.core.exceptions import AssistantError
from app.core.logging import get_logger
from app.tools.base import ToolResult
from app.ui.models import TurnMetrics

logger = get_logger("ui.worker")


class AgentWorker(QThread):
    """Worker thread running Agent.stream_run() asynchronously with fine-grained latency telemetry."""

    # Signals emitted to the Qt UI thread
    chunk_received = Signal(str)
    tool_started = Signal(str, dict)
    tool_finished = Signal(str, bool, str)
    metrics_ready = Signal(object)
    finished = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        agent: Agent,
        prompt: str,
        model: Optional[str] = None,
        images: Optional[list[Any]] = None,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.agent = agent
        self.prompt = prompt
        self.model = model
        self.images = images
        self._is_cancelled = False

    def cancel(self) -> None:
        """Flag cancellation to stop streaming cleanly."""
        self._is_cancelled = True
        logger.info("AgentWorker received cancellation request.")

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def _handle_tool_start(self, tool_name: str, args: dict[str, Any]) -> None:
        """Callback from agent when a tool begins execution."""
        safe_args = {k: ("******" if "password" in k.lower() or "token" in k.lower() or "secret" in k.lower() else v)
                     for k, v in args.items()}
        self.tool_started.emit(tool_name, safe_args)

    def _handle_tool_end(self, tool_name: str, result: ToolResult) -> None:
        """Callback from agent when a tool completes execution."""
        summary = result.message or (f"Success ({result.error or ''})") if result.success else (result.error or "Failed")
        self.tool_finished.emit(tool_name, result.success, summary)

    def run(self) -> None:
        """Execute the agent streaming loop on this background thread with telemetry capture."""
        logger.info("AgentWorker starting execution for prompt: '%s' (model=%s, images=%d)",
                    self.prompt[:50], self.model, len(self.images) if self.images else 0)
        self.agent.on_tool_start = self._handle_tool_start
        self.agent.on_tool_end = self._handle_tool_end

        t_start = time.perf_counter()
        t_first_chunk: Optional[float] = None
        accumulated_response: list[str] = []
        chunks_count = 0

        try:
            for chunk in self.agent.stream_run(self.prompt, model=self.model, interactive=True, images=self.images):
                if self._is_cancelled:
                    logger.info("Streaming interrupted by user cancellation.")
                    break
                if t_first_chunk is None:
                    t_first_chunk = time.perf_counter()
                chunks_count += 1
                accumulated_response.append(chunk)
                self.chunk_received.emit(chunk)

            t_end = time.perf_counter()
            full_text = "".join(accumulated_response)

            # Build fine-grained turn metrics
            ttft = (t_first_chunk - t_start) if t_first_chunk else None
            total_duration = t_end - t_start
            gen_duration = (t_end - t_first_chunk) if t_first_chunk else total_duration
            tokens_per_sec = (chunks_count / max(0.01, gen_duration)) if chunks_count > 1 else 0.0

            # Determine routing decision model info if available
            decision = getattr(self.agent, "last_routing_decision", None)
            model_name = getattr(decision, "selected_model", self.model or getattr(self.agent.client, "default_model", "qwen3:30b"))
            role_val = getattr(getattr(decision, "role", None), "value", "standard")
            is_fb = getattr(decision, "is_fallback", False)

            # Determine execution tier
            is_fastpath = getattr(getattr(self.agent, "last_intent", None), "action_type", None) == "fast_path" or chunks_count <= 1 and total_duration < 0.05
            tier_label = "DIRECT" if is_fastpath else (role_val.upper() if role_val else "FAST_MODEL")

            metrics = TurnMetrics(
                ttft=ttft,
                total_time=total_duration,
                chunks_count=chunks_count,
                chars_count=len(full_text),
                tokens_per_second=tokens_per_sec,
                model_name=model_name if not is_fastpath else "pixel-fast-path",
                role=role_val if not is_fastpath else "direct",
                is_fallback=is_fb,
                tier=tier_label,
                ttft_ms=ttft * 1000 if ttft is not None else None,
                t_generation_ms=gen_duration * 1000,
                t_total_ms=total_duration * 1000,
                input_tokens=max(1, len(self.prompt) // 4),
                output_tokens=max(1, len(full_text) // 4),
            )

            self.metrics_ready.emit(metrics)
            self.finished.emit(full_text)

        except AssistantError as err:
            logger.error("Domain assistant error in worker: %s", err)
            self.error_occurred.emit(str(err))
        except Exception as err:
            logger.exception("Unexpected exception in worker thread: %s", err)
            self.error_occurred.emit(f"Internal error: {err}")
        finally:
            self.agent.on_tool_start = None
            self.agent.on_tool_end = None
