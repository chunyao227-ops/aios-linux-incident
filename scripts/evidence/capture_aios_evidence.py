"""Capture one real AIOS-backed text and JSON smoke response."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from aios_incident.adapters.aios_client import AiosClient
from aios_incident.adapters.llm_adapter import ChatMessage, LlmAdapter
from aios_incident.config import load_config

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "submission" / "evidence" / "terminal"


class SmokeOutput(BaseModel):
    ok: bool
    marker: str


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    client = AiosClient(config.aios)
    adapter = LlmAdapter(client, config.model)
    health = client.health_check()
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
    json_response = adapter.chat_json(
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
    payload = {
        "environment": {
            "aios_base_url": config.aios.base_url,
            "model": config.model.served_model_name,
            "backend": config.model.backend,
        },
        "health": health,
        "text": text_response.model_dump(mode="json"),
        "json": {
            "data": json_response.data.model_dump(mode="json"),
            "response": json_response.response.model_dump(mode="json"),
        },
    }
    (OUTPUT_DIR / "W04_aios_responses.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("real AIOS text and JSON responses captured")


if __name__ == "__main__":
    main()
