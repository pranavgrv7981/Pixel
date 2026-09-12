"""Ollama local model client and status layer."""

from collections.abc import Mapping
from enum import Enum
import time
from typing import Any, Iterator, Optional, Union

import httpx
import ollama
from pydantic import BaseModel, Field


from app.core.config import Settings, get_settings
from app.core.exceptions import ModelAPIError, ModelNotFoundError, OllamaConnectionError
from app.core.logging import get_logger

logger = get_logger("ollama")


class ServerStatus(str, Enum):
    """Status of the Ollama server connection."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class ModelStatus(str, Enum):
    """Availability status of the configured model."""

    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNKNOWN = "UNKNOWN"


class ChatMessage(BaseModel):
    """Structured message format for Ollama chat."""

    role: str = Field(description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(description="Message text content")
    images: Optional[list[str]] = Field(default=None, description="Optional base64 image strings for multimodal vision input")

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for Ollama API."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            d["images"] = self.images
        return d


class OllamaStatus(BaseModel):
    """Structured health and availability status for Ollama and models."""

    server_status: ServerStatus
    model_status: ModelStatus
    base_url: str
    model_name: str
    available_models: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        """Return True if the Ollama server is currently reachable."""
        return self.server_status == ServerStatus.CONNECTED

    @property
    def is_model_available(self) -> bool:
        """Return True if the configured model is installed on the server."""
        return self.model_status == ModelStatus.AVAILABLE


class ModelResponse(str):
    """Response string that also provides structured access to tool_calls."""

    def __new__(cls, content: str, tool_calls: Optional[list[dict[str, Any]]] = None) -> "ModelResponse":
        obj = super().__new__(cls, content or "")
        obj._content = content or ""
        obj._tool_calls = tool_calls or []
        return obj

    @property
    def content(self) -> str:
        return self._content

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self._tool_calls

    @property
    def has_tool_calls(self) -> bool:
        return len(self._tool_calls) > 0


class OllamaClient:
    """Client for interacting with local Ollama server and models."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        default_model: Optional[str] = None,
        num_ctx: Optional[int] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        if settings is None and (base_url is None or timeout is None or default_model is None):
            settings = get_settings()

        self.settings = settings or get_settings()
        self.base_url = base_url or self.settings.ollama_base_url
        self.timeout = timeout if timeout is not None else self.settings.ollama_timeout_seconds
        self.default_model = default_model or self.settings.default_model
        self.num_ctx = num_ctx if num_ctx is not None else self.settings.ollama_num_ctx

        # Use granular httpx timeout: quick connect check, generous read timeout for large models on CPU
        connect_t = getattr(self.settings, "ollama_connect_timeout_seconds", 10.0)
        read_t = max(self.timeout, getattr(self.settings, "ollama_generation_timeout_seconds", 600.0))
        http_timeout = httpx.Timeout(timeout=self.timeout, connect=connect_t, read=read_t, write=30.0)
        self._client = ollama.Client(host=self.base_url, timeout=http_timeout)


    def check_connection(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            self.list_models()
            return True
        except OllamaConnectionError:
            return False
        except Exception as e:
            logger.debug("Ollama check_connection failed: %s", e)
            return False

    def list_models(self) -> list[str]:
        """List all model names currently available in Ollama.

        Returns:
            List of model names installed on the Ollama host.

        Raises:
            OllamaConnectionError: If unable to reach Ollama server.
            ModelAPIError: If the API returns an unexpected error.
        """
        logger.debug("Querying available models from Ollama at %s", self.base_url)
        try:
            response = self._client.list()
            model_names: list[str] = []

            # Handle ListResponse or dict response structure
            models = getattr(response, "models", None)
            if models is None and isinstance(response, dict):
                models = response.get("models", [])

            if models:
                for item in models:
                    name = getattr(item, "model", None) or getattr(item, "name", None)
                    if name is None and isinstance(item, dict):
                        name = item.get("model") or item.get("name")
                    if name:
                        model_names.append(str(name))

            logger.debug("Retrieved %d models from Ollama", len(model_names))
            return model_names

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as err:
            msg = f"Could not connect to Ollama server at {self.base_url}: {err}"
            logger.warning(msg)
            raise OllamaConnectionError(msg, details={"base_url": self.base_url}) from err

        except httpx.TimeoutException as err:
            msg = f"Connection to Ollama server at {self.base_url} timed out: {err}"
            logger.warning(msg)
            raise OllamaConnectionError(msg, details={"base_url": self.base_url, "timeout": self.timeout}) from err

        except ollama.ResponseError as err:
            msg = f"Ollama API response error during model listing: {err}"
            logger.error(msg)
            raise ModelAPIError(msg, details={"status_code": getattr(err, "status_code", None)}) from err

        except Exception as err:
            msg = f"Unexpected error while communicating with Ollama: {err}"
            logger.error(msg)
            raise OllamaConnectionError(msg, details={"base_url": self.base_url}) from err

    def model_exists(self, model_name: Optional[str] = None) -> bool:
        """Check if the given model exists in the Ollama instance.

        Args:
            model_name: Name of the model. Defaults to self.default_model.

        Returns:
            True if the model is available, False otherwise.
        """
        target = model_name or self.default_model
        try:
            available_models = self.list_models()
        except OllamaConnectionError:
            return False

        if target in available_models:
            return True

        # Check with or without default ':latest' tag
        target_base = target.split(":")[0]
        for name in available_models:
            if name == target:
                return True
            name_base = name.split(":")[0]
            if name == f"{target}:latest" or target == f"{name}:latest":
                return True
            if ":" not in target and name_base == target_base:
                return True

        return False

    def get_status(self, model_name: Optional[str] = None) -> OllamaStatus:
        """Get structured status for Ollama server and the configured model."""
        target_model = model_name or self.default_model
        try:
            models = self.list_models()
            is_present = self._model_matches(target_model, models)
            return OllamaStatus(
                server_status=ServerStatus.CONNECTED,
                model_status=ModelStatus.AVAILABLE if is_present else ModelStatus.NOT_AVAILABLE,
                base_url=self.base_url,
                model_name=target_model,
                available_models=models,
            )
        except OllamaConnectionError as err:
            return OllamaStatus(
                server_status=ServerStatus.DISCONNECTED,
                model_status=ModelStatus.UNKNOWN,
                base_url=self.base_url,
                model_name=target_model,
                available_models=[],
                error_message=err.message,
            )
        except Exception as err:
            return OllamaStatus(
                server_status=ServerStatus.DISCONNECTED,
                model_status=ModelStatus.UNKNOWN,
                base_url=self.base_url,
                model_name=target_model,
                available_models=[],
                error_message=str(err),
            )

    def _model_matches(self, target: str, available_models: list[str]) -> bool:
        """Match target model against available model tags."""
        if target in available_models:
            return True
        target_base = target.split(":")[0]
        for name in available_models:
            if name == target:
                return True
            name_base = name.split(":")[0]
            if name == f"{target}:latest" or target == f"{name}:latest":
                return True
            if ":" not in target and name_base == target_base:
                return True
        return False

    def _normalize_messages(
        self, messages: list[Union[dict[str, Any], ChatMessage]]
    ) -> list[dict[str, Any]]:
        """Normalize messages to dict format for Ollama API."""
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                formatted.append(msg.to_dict())
            elif isinstance(msg, dict):
                entry = {"role": str(msg.get("role", "user")), "content": str(msg.get("content", ""))}
                if "tool_calls" in msg:
                    entry["tool_calls"] = msg["tool_calls"]
                if "name" in msg:
                    entry["name"] = msg["name"]
                formatted.append(entry)
            else:
                formatted.append({"role": "user", "content": str(msg)})
        return formatted

    def chat(
        self,
        messages: list[Union[dict[str, str], ChatMessage]],
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> ModelResponse:
        """Send a synchronous chat request to the Ollama model."""
        target_model = model or self.default_model
        formatted_messages = self._normalize_messages(messages)

        logger.info(
            "Sending chat request to model '%s' (%d messages, %d tools)",
            target_model,
            len(formatted_messages),
            len(tools) if tools else 0,
        )

        try:
            merged_options: dict[str, Any] = {}
            if self.num_ctx is not None:
                merged_options["num_ctx"] = self.num_ctx
            if options:
                merged_options.update(options)

            kwargs: dict[str, Any] = {
                "model": target_model,
                "messages": formatted_messages,
                "stream": False,
            }
            if merged_options:
                if "keep_alive" in merged_options:
                    kwargs["keep_alive"] = merged_options.pop("keep_alive")
                kwargs["options"] = merged_options
            if "keep_alive" not in kwargs and getattr(self.settings, "ollama_keep_alive", None):
                kwargs["keep_alive"] = self.settings.ollama_keep_alive
            if tools is not None:
                kwargs["tools"] = tools

            response = self._client.chat(**kwargs)


            # Extract response content and tool calls
            content: str = ""
            parsed_tool_calls: list[dict[str, Any]] = []

            msg = getattr(response, "message", None)
            if msg is not None:
                content = getattr(msg, "content", "") or ""
                raw_tool_calls = getattr(msg, "tool_calls", None) or []
            elif isinstance(response, dict):
                msg_dict = response.get("message", {})
                content = msg_dict.get("content", "") or ""
                raw_tool_calls = msg_dict.get("tool_calls", []) or []
            else:
                raw_tool_calls = []

            for tc in raw_tool_calls:
                fn = getattr(tc, "function", None)
                if fn is not None:
                    name = getattr(fn, "name", "")
                    arguments = getattr(fn, "arguments", {})
                elif isinstance(tc, dict):
                    fn_dict = tc.get("function", {})
                    name = fn_dict.get("name", "")
                    arguments = fn_dict.get("arguments", {})
                else:
                    name = getattr(tc, "name", "")
                    arguments = getattr(tc, "arguments", {})

                if name:
                    parsed_tool_calls.append({
                        "name": str(name),
                        "arguments": dict(arguments) if isinstance(arguments, Mapping) else {},
                    })

            logger.info(
                "Received response from model '%s' (%d chars, %d tool calls)",
                target_model,
                len(content),
                len(parsed_tool_calls),
            )
            return ModelResponse(content, parsed_tool_calls)


        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as err:
            msg = f"Failed to connect to Ollama at {self.base_url}: {err}"
            logger.error(msg)
            raise OllamaConnectionError(msg, details={"base_url": self.base_url}) from err

        except httpx.TimeoutException as err:
            msg = f"Chat request to Ollama timed out after {self.timeout}s: {err}"
            logger.error(msg)
            raise OllamaConnectionError(msg, details={"timeout": self.timeout}) from err

        except ollama.ResponseError as err:
            status = getattr(err, "status_code", None)
            error_text = str(err)
            if status == 404 or "not found" in error_text.lower():
                msg = f"Model '{target_model}' not found on Ollama server"
                logger.error(msg)
                raise ModelNotFoundError(msg, details={"model": target_model}) from err
            msg = f"Ollama API error: {err}"
            logger.error(msg)
            raise ModelAPIError(msg, details={"status_code": status}) from err

        except Exception as err:
            msg = f"Unexpected error during chat: {err}"
            logger.error(msg)
            raise ModelAPIError(msg, details={"model": target_model}) from err

    def stream_chat(
        self,
        messages: list[Union[dict[str, str], ChatMessage]],
        model: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
        think: bool = True,
    ) -> Iterator[str]:
        """Send a streaming chat request to the Ollama model with low-latency optimizations."""
        target_model = model or self.default_model
        formatted_messages = self._normalize_messages(messages)

        logger.info("CHAT START model=%s (messages=%d, think=%s)", target_model, len(formatted_messages), think)
        start_t = time.perf_counter()
        first_token_t: Optional[float] = None
        chunks_count = 0
        in_think_block = False

        try:
            merged_options: dict[str, Any] = {}
            if self.num_ctx is not None:
                merged_options["num_ctx"] = self.num_ctx
            if options:
                merged_options.update(options)

            kwargs: dict[str, Any] = {
                "model": target_model,
                "messages": formatted_messages,
                "stream": True,
            }
            if merged_options:
                if "keep_alive" in merged_options:
                    kwargs["keep_alive"] = merged_options.pop("keep_alive")
                kwargs["options"] = merged_options
            if "keep_alive" not in kwargs and getattr(self.settings, "ollama_keep_alive", None):
                kwargs["keep_alive"] = self.settings.ollama_keep_alive

            stream = self._client.chat(**kwargs)

            for chunk in stream:
                token = ""
                msg = getattr(chunk, "message", None)
                if msg is not None:
                    token = getattr(msg, "content", "") or ""
                elif isinstance(chunk, dict):
                    token = chunk.get("message", {}).get("content", "")
                if token:
                    # Filter out think tags when thinking is disabled
                    if not think:
                        if "<think>" in token:
                            in_think_block = True
                            token = token.replace("<think>", "")
                        if "</think>" in token:
                            in_think_block = False
                            token = token.split("</think>")[-1]
                        if in_think_block:
                            continue
                        if not token:
                            continue

                    if first_token_t is None:
                        first_token_t = time.perf_counter()
                        ttft = first_token_t - start_t
                        logger.info("FIRST TOKEN model=%s TTFT=%.2fs", target_model, ttft)
                    chunks_count += 1
                    yield token

            total_t = time.perf_counter() - start_t
            logger.info("CHAT COMPLETE model=%s chunks=%d elapsed=%.2fs", target_model, chunks_count, total_t)

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as err:
            msg = f"Failed to connect to Ollama during streaming at {self.base_url}: {err}"
            logger.error(msg)
            raise OllamaConnectionError(msg, details={"base_url": self.base_url}) from err

        except httpx.TimeoutException as err:
            elapsed = time.perf_counter() - start_t
            msg = f"Streaming chat to Ollama timed out after {elapsed:.1f}s (configured limit: {self.timeout}s): {err}"
            logger.error("CHAT TIMEOUT model=%s elapsed=%.1fs error=%s", target_model, elapsed, err)
            raise OllamaConnectionError(msg, details={"timeout": self.timeout, "elapsed": elapsed}) from err

        except ollama.ResponseError as err:
            status = getattr(err, "status_code", None)
            error_text = str(err)
            if status == 404 or "not found" in error_text.lower():
                msg = f"Model '{target_model}' not found on Ollama server"
                logger.error(msg)
                raise ModelNotFoundError(msg, details={"model": target_model}) from err
            msg = f"Ollama API error during streaming: {err}"
            logger.error(msg)
            raise ModelAPIError(msg, details={"status_code": status}) from err

        except Exception as err:
            msg = f"Unexpected error during streaming chat: {err}"
            logger.error(msg)
            raise ModelAPIError(msg, details={"model": target_model}) from err
