"""LLM query protocol and AIOS-backed text/JSON adapter."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

from ..config import ModelConfig
from ..exceptions import (
    AdapterProtocolError,
    InputValidationError,
    ModelResponseError,
)
from ..models import StrictModel, TokenUsage
from ..validation import get_json_schema, validate_json_schema, validate_model
from .aios_client import AiosClient

OutputModelT = TypeVar("OutputModelT", bound=BaseModel)


class ChatMessage(StrictModel):
    """One chat message accepted by the AIOS LLM query protocol."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None


class LLMQuery(StrictModel):
    """Task-level LLM query independent of an AIOS SDK object."""

    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_new_tokens: int = Field(default=512, gt=0, le=4096)
    message_return_type: Literal["text", "json"] = "text"
    response_format: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_json_request(self) -> LLMQuery:
        if self.message_return_type == "json" and self.response_format is None:
            raise ValueError("JSON LLMQuery requires response_format")
        return self


class LLMResponse(StrictModel):
    """Normalized model response exposed to Agents."""

    response_class: Literal["llm"] = "llm"
    response_message: str | None = None
    json_output: dict[str, Any] | None = None
    tool_calls: tuple[dict[str, Any], ...] = ()
    finished: bool
    error: str | None = None
    status_code: int
    token_usage: TokenUsage
    duration_ms: int
    attempts: int


@dataclass(frozen=True, slots=True)
class StructuredLLMResponse(Generic[OutputModelT]):
    """Validated typed object plus its normalized transport response."""

    response: LLMResponse
    data: OutputModelT


class LlmAdapter:
    """Text and strict JSON calls routed exclusively through AIOS `/query`."""

    def __init__(self, client: AiosClient, model_config: ModelConfig) -> None:
        self.client = client
        self.model_config = model_config

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        agent_name: str = "CoordinatorAgent",
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        user_id: str | None = None,
    ) -> LLMResponse:
        """Return a normalized plain-text model response."""

        query = LLMQuery(
            messages=tuple(messages),
            temperature=self.model_config.temperature if temperature is None else temperature,
            max_new_tokens=self.model_config.max_tokens
            if max_new_tokens is None
            else max_new_tokens,
            message_return_type="text",
        )
        return self._invoke(query, agent_name=agent_name, user_id=user_id)

    def chat_json(
        self,
        messages: Sequence[ChatMessage],
        *,
        output_model: type[OutputModelT],
        agent_name: str = "CoordinatorAgent",
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        user_id: str | None = None,
    ) -> StructuredLLMResponse[OutputModelT]:
        """Return strict JSON validated against a task-level Pydantic schema."""

        schema = get_json_schema(output_model)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "schema": schema,
                "strict": True,
            },
        }
        query = LLMQuery(
            messages=tuple(messages),
            temperature=self.model_config.temperature if temperature is None else temperature,
            max_new_tokens=self.model_config.max_tokens
            if max_new_tokens is None
            else max_new_tokens,
            message_return_type="json",
            response_format=response_format,
        )
        normalized = self._invoke(query, agent_name=agent_name, user_id=user_id)
        if normalized.response_message is None:
            raise AdapterProtocolError("AIOS JSON response did not include response_message")
        try:
            payload = json.loads(normalized.response_message)
        except json.JSONDecodeError as exc:
            raise InputValidationError(
                f"model response is not valid JSON at column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise InputValidationError("model JSON response root must be an object")

        validate_json_schema(payload, output_model)
        data = validate_model(payload, output_model)
        normalized_with_output = normalized.model_copy(
            update={"json_output": data.model_dump(mode="json")}
        )
        return StructuredLLMResponse(response=normalized_with_output, data=data)

    def _invoke(
        self,
        query: LLMQuery,
        *,
        agent_name: str,
        user_id: str | None,
    ) -> LLMResponse:
        query_data: dict[str, Any] = {
            "query_class": "llm",
            "llms": [
                {
                    "name": self.model_config.served_model_name,
                    "temperature": query.temperature,
                    "max_tokens": query.max_new_tokens,
                }
            ],
            "messages": [message.model_dump(exclude_none=True) for message in query.messages],
            "tools": [],
            "action_type": "chat_with_json_output"
            if query.message_return_type == "json"
            else "chat",
            "message_return_type": query.message_return_type,
        }
        if query.response_format is not None:
            query_data["response_format"] = query.response_format

        result = self.client.query(
            agent_name=agent_name,
            query_type="llm",
            query_data=query_data,
            user_id=user_id,
        )
        raw_response = result.payload.get("response")
        if not isinstance(raw_response, Mapping):
            raise AdapterProtocolError("AIOS query response is missing the response object")

        response_message = raw_response.get("response_message")
        if response_message is not None and not isinstance(response_message, str):
            raise AdapterProtocolError("AIOS response_message must be a string or null")
        error = raw_response.get("error")
        finished = raw_response.get("finished")
        status_code = raw_response.get("status_code")
        if not isinstance(finished, bool):
            raise AdapterProtocolError("AIOS response.finished must be a boolean")
        if not isinstance(status_code, int):
            raise AdapterProtocolError("AIOS response.status_code must be an integer")
        if error is not None or not finished or status_code >= 400:
            raise ModelResponseError(
                f"AIOS model response failed: {error or 'unfinished response'}",
                status_code=status_code,
            )
        if response_message is None:
            raise ModelResponseError("AIOS model response message is empty")

        prompt_text = "\n".join(message.content for message in query.messages)
        token_usage = _extract_token_usage(
            result.payload,
            raw_response,
            prompt_text=prompt_text,
            completion_text=response_message,
        )
        tool_calls = raw_response.get("tool_calls")
        if tool_calls is None:
            normalized_tool_calls: tuple[dict[str, Any], ...] = ()
        elif isinstance(tool_calls, list) and all(isinstance(item, dict) for item in tool_calls):
            normalized_tool_calls = tuple(tool_calls)
        else:
            raise AdapterProtocolError("AIOS response.tool_calls must be a list or null")

        return LLMResponse(
            response_message=response_message,
            tool_calls=normalized_tool_calls,
            finished=finished,
            error=None,
            status_code=status_code,
            token_usage=token_usage,
            duration_ms=result.duration_ms,
            attempts=result.attempts,
        )


def _extract_token_usage(
    outer_payload: Mapping[str, Any],
    raw_response: Mapping[str, Any],
    *,
    prompt_text: str,
    completion_text: str,
) -> TokenUsage:
    for candidate in (
        raw_response.get("usage"),
        raw_response.get("token_usage"),
        outer_payload.get("usage"),
        outer_payload.get("token_usage"),
    ):
        reported = _parse_reported_usage(candidate)
        if reported is not None:
            return reported
    return TokenUsage(
        prompt=_estimate_tokens(prompt_text),
        completion=_estimate_tokens(completion_text),
        source="estimated",
    )


def _parse_reported_usage(value: Any) -> TokenUsage | None:
    if not isinstance(value, Mapping):
        return None
    prompt = value.get("prompt_tokens", value.get("prompt"))
    completion = value.get("completion_tokens", value.get("completion"))
    if (
        isinstance(prompt, int)
        and not isinstance(prompt, bool)
        and prompt >= 0
        and isinstance(completion, int)
        and not isinstance(completion, bool)
        and completion >= 0
    ):
        return TokenUsage(prompt=prompt, completion=completion, source="reported")
    return None


def _estimate_tokens(text: str) -> int:
    """Estimate tokens without claiming exact tokenizer accuracy."""

    cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    latin_non_whitespace = len(re.sub(r"\s", "", text)) - cjk_count
    return cjk_count + math.ceil(latin_non_whitespace / 4)
