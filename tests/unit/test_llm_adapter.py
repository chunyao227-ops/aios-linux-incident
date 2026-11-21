"""W04 AIOS client and LLM adapter tests without a real model."""

from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from aios_incident.adapters import aios_client as aios_client_module
from aios_incident.adapters.aios_client import AiosClient, AiosQueryResult
from aios_incident.adapters.llm_adapter import (
    ChatMessage,
    LlmAdapter,
    LLMQuery,
)
from aios_incident.config import AIOSConfig, load_config
from aios_incident.exceptions import (
    AdapterHTTPError,
    AdapterInvocationError,
    AdapterProtocolError,
    AdapterTimeoutError,
    AdapterTransportError,
    InputValidationError,
    ModelResponseError,
)


class StubAiosClient:
    def __init__(self, payloads: list[dict[str, Any] | Exception]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def query(
        self,
        *,
        agent_name: str,
        query_type: str,
        query_data: Mapping[str, Any],
        user_id: str | None = None,
    ) -> AiosQueryResult:
        self.calls.append(
            {
                "agent_name": agent_name,
                "query_type": query_type,
                "query_data": dict(query_data),
                "user_id": user_id,
            }
        )
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return AiosQueryResult(payload=payload, attempts=1, duration_ms=123)


class DiagnosisOutput(BaseModel):
    root_cause: str
    confidence: float = Field(ge=0, le=1)


class FakeHttpResponse:
    def __init__(self, payload: str, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return self.payload.encode("utf-8")

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def make_response(
    message: str,
    *,
    error: str | None = None,
    finished: bool = True,
    status_code: int = 200,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "response_class": "llm",
        "response_message": message,
        "tool_calls": None,
        "finished": finished,
        "error": error,
        "status_code": status_code,
    }
    if usage is not None:
        response["usage"] = usage
    return {
        "response": response,
        "start_times": [],
        "end_times": [],
        "waiting_times": [],
        "turnaround_times": [],
    }


def make_adapter(payloads: list[dict[str, Any] | Exception]) -> tuple[LlmAdapter, StubAiosClient]:
    config = load_config()
    client = StubAiosClient(payloads)
    return LlmAdapter(client, config.model), client  # type: ignore[arg-type]


def test_chat_uses_aios_query_and_normalizes_response() -> None:
    adapter, client = make_adapter([make_response("W04_OK")])
    result = adapter.chat(
        [ChatMessage(role="user", content="Reply exactly W04_OK")],
        agent_name="LogAgent",
        user_id="tester",
    )

    assert result.response_message == "W04_OK"
    assert result.finished is True
    assert result.duration_ms == 123
    assert result.token_usage.source == "estimated"
    assert client.calls[0]["agent_name"] == "LogAgent"
    assert client.calls[0]["query_type"] == "llm"
    assert client.calls[0]["user_id"] == "tester"
    query_data = client.calls[0]["query_data"]
    assert query_data["action_type"] == "chat"
    assert query_data["message_return_type"] == "text"
    assert query_data["llms"][0]["name"] == "qwen2:7b-instruct"


def test_chat_json_returns_typed_schema_validated_output() -> None:
    payload = json.dumps({"root_cause": "database stopped", "confidence": 0.88})
    adapter, client = make_adapter([make_response(payload)])
    result = adapter.chat_json(
        [ChatMessage(role="user", content="Return the diagnosis JSON.")],
        output_model=DiagnosisOutput,
    )

    assert result.data == DiagnosisOutput(root_cause="database stopped", confidence=0.88)
    assert result.response.json_output == {
        "root_cause": "database stopped",
        "confidence": 0.88,
    }
    query_data = client.calls[0]["query_data"]
    assert query_data["action_type"] == "chat_with_json_output"
    assert query_data["message_return_type"] == "json"
    assert query_data["response_format"]["type"] == "json_schema"
    assert query_data["response_format"]["json_schema"]["name"] == "DiagnosisOutput"
    assert query_data["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    "message",
    [
        "not json",
        '```json\n{"root_cause":"x","confidence":0.5}\n```',
        '["root_cause", 0.5]',
    ],
)
def test_chat_json_does_not_guess_or_repair_output(message: str) -> None:
    adapter, _ = make_adapter([make_response(message)])
    with pytest.raises(InputValidationError):
        adapter.chat_json(
            [ChatMessage(role="user", content="JSON only")],
            output_model=DiagnosisOutput,
        )


def test_chat_json_rejects_schema_mismatch() -> None:
    adapter, _ = make_adapter([make_response(json.dumps({"root_cause": "x", "confidence": 2.0}))])
    with pytest.raises(InputValidationError, match="JSON Schema validation failed"):
        adapter.chat_json(
            [ChatMessage(role="user", content="JSON only")],
            output_model=DiagnosisOutput,
        )


@pytest.mark.parametrize(
    "response",
    [
        make_response("", error="generation failed", finished=False, status_code=500),
        {"response": {"response_message": "missing fields"}},
        {"not_response": {}},
    ],
)
def test_failed_or_malformed_aios_response_is_normalized(response: dict[str, Any]) -> None:
    adapter, _ = make_adapter([response])
    with pytest.raises(AdapterInvocationError):
        adapter.chat([ChatMessage(role="user", content="hello")])


def test_finished_false_response_uses_model_response_error() -> None:
    adapter, _ = make_adapter([make_response("partial", error="generation failed", finished=False)])
    with pytest.raises(ModelResponseError, match="generation failed"):
        adapter.chat([ChatMessage(role="user", content="hello")])


def test_reported_token_usage_is_preferred_over_estimation() -> None:
    adapter, _ = make_adapter(
        [make_response("W04_OK", usage={"prompt_tokens": 10, "completion_tokens": 3})]
    )
    result = adapter.chat([ChatMessage(role="user", content="hello")])
    assert result.token_usage.prompt == 10
    assert result.token_usage.completion == 3
    assert result.token_usage.source == "reported"


def test_json_query_contract_requires_response_format() -> None:
    with pytest.raises(ValidationError, match="requires response_format"):
        LLMQuery(
            messages=(ChatMessage(role="user", content="JSON"),),
            message_return_type="json",
        )


def test_aios_client_retries_only_to_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    client = AiosClient(
        AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=2),
        sleep_func=sleeps.append,
        retry_backoff_seconds=0.1,
    )
    attempts = 0

    def fake_request(
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise AdapterTimeoutError("temporary timeout")
        return {"status": "ok"}

    monkeypatch.setattr(client, "_request_once", fake_request)
    result = client.query(
        agent_name="CoordinatorAgent",
        query_type="llm",
        query_data={"messages": []},
    )
    assert result.payload == {"status": "ok"}
    assert result.attempts == 3
    assert sleeps == [0.1, 0.2]


def test_aios_client_does_not_retry_non_retryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AiosClient(
        AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=3),
        sleep_func=lambda _: None,
    )
    attempts = 0

    def fake_request(
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise AdapterHTTPError(
            "AIOS returned HTTP 400: invalid payload",
            retryable=False,
            status_code=400,
        )

    monkeypatch.setattr(client, "_request_once", fake_request)
    with pytest.raises(AdapterHTTPError) as raised:
        client.query(
            agent_name="CoordinatorAgent",
            query_type="llm",
            query_data={"messages": []},
        )
    assert attempts == 1
    assert raised.value.status_code == 400


def test_aios_client_raises_after_retry_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AiosClient(
        AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=1),
        sleep_func=lambda _: None,
    )
    attempts = 0

    def fake_request(
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise AdapterTimeoutError("timeout")

    monkeypatch.setattr(client, "_request_once", fake_request)
    with pytest.raises(AdapterTimeoutError, match="timeout"):
        client.query(
            agent_name="CoordinatorAgent",
            query_type="llm",
            query_data={"messages": []},
        )
    assert attempts == 2


def test_non_object_aios_response_is_protocol_error() -> None:
    adapter, _ = make_adapter([AdapterProtocolError("AIOS response root must be an object")])
    with pytest.raises(AdapterProtocolError):
        adapter.chat([ChatMessage(role="user", content="hello")])


def test_transport_converts_http_error_to_normalized_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AiosClient(AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=0))
    error = urllib.error.HTTPError(
        url="http://aios.test/query",
        code=503,
        msg="Service Unavailable",
        hdrs=None,
        fp=io.BytesIO(b'{"detail":"model warming up"}'),
    )

    def raise_http_error(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(aios_client_module.urllib.request, "urlopen", raise_http_error)
    with pytest.raises(AdapterHTTPError) as raised:
        client._request_once("POST", "/query", {"query_type": "llm"})
    assert raised.value.status_code == 503
    assert raised.value.retryable is True
    assert "model warming up" in str(raised.value)


def test_transport_converts_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AiosClient(AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=0))

    def raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr(aios_client_module.urllib.request, "urlopen", raise_url_error)
    with pytest.raises(AdapterTransportError, match="cannot reach AIOS"):
        client._request_once("GET", "/status", None)


def test_transport_rejects_invalid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AiosClient(AIOSConfig(base_url="http://aios.test", timeout_seconds=1, max_retries=0))
    monkeypatch.setattr(
        aios_client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeHttpResponse("{not-json"),
    )
    with pytest.raises(AdapterProtocolError, match="invalid JSON"):
        client._request_once("GET", "/status", None)
