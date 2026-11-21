"""Opt-in smoke tests against the real local AIOS and Ollama services."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from aios_incident.adapters.aios_client import AiosClient
from aios_incident.adapters.llm_adapter import ChatMessage, LlmAdapter
from aios_incident.config import load_config

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_AIOS_INTEGRATION") != "1",
        reason="set RUN_AIOS_INTEGRATION=1 to call the real local AIOS",
    ),
]


class SmokeOutput(BaseModel):
    ok: bool
    marker: str


def test_real_aios_health_text_and_json_smoke() -> None:
    config = load_config()
    client = AiosClient(config.aios)

    health = client.health_check()
    assert health["status"] == "ok"

    adapter = LlmAdapter(client, config.model)
    text_response = adapter.chat(
        [
            ChatMessage(
                role="user",
                content="Reply exactly W04_AIOS_OK and nothing else.",
            )
        ],
        agent_name="CoordinatorAgent",
        max_new_tokens=32,
    )
    assert text_response.finished is True
    assert text_response.response_message is not None
    assert "W04_AIOS_OK" in text_response.response_message
    assert text_response.token_usage.source in {"reported", "estimated"}

    structured = adapter.chat_json(
        [
            ChatMessage(
                role="user",
                content=('Return exactly this JSON object: {"ok": true, "marker": "W04_JSON_OK"}'),
            )
        ],
        output_model=SmokeOutput,
        agent_name="CoordinatorAgent",
        max_new_tokens=64,
    )
    assert structured.data == SmokeOutput(ok=True, marker="W04_JSON_OK")
    assert structured.response.json_output == {"ok": True, "marker": "W04_JSON_OK"}
