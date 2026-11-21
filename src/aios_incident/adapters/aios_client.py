"""HTTP client for the locked AIOS kernel query interface."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..config import AIOSConfig
from ..exceptions import (
    AdapterHTTPError,
    AdapterInvocationError,
    AdapterProtocolError,
    AdapterTimeoutError,
    AdapterTransportError,
)

RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class AiosQueryResult:
    """Normalized result metadata for one successful AIOS query."""

    payload: dict[str, Any]
    attempts: int
    duration_ms: int


class AiosClient:
    """Bounded-retry AIOS client that never calls a model vendor directly."""

    def __init__(
        self,
        config: AIOSConfig,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        self.config = config
        self._sleep = sleep_func
        self._retry_backoff_seconds = retry_backoff_seconds

    def health_check(self) -> dict[str, Any]:
        """Read the AIOS root health endpoint."""

        return self._request_with_retries("GET", "/status", None).payload

    def query(
        self,
        *,
        agent_name: str,
        query_type: str,
        query_data: Mapping[str, Any],
        user_id: str | None = None,
    ) -> AiosQueryResult:
        """Send one bounded-retry query to AIOS `/query`."""

        payload: dict[str, Any] = {
            "agent_name": agent_name,
            "query_type": query_type,
            "query_data": dict(query_data),
        }
        if user_id is not None:
            payload["user_id"] = user_id
        return self._request_with_retries("POST", "/query", payload)

    def _request_with_retries(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> AiosQueryResult:
        started = time.perf_counter()
        max_attempts = self.config.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response_payload = self._request_once(method, path, payload)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                return AiosQueryResult(
                    payload=response_payload,
                    attempts=attempt,
                    duration_ms=elapsed_ms,
                )
            except AdapterInvocationError as exc:
                if not exc.retryable or attempt == max_attempts:
                    raise
                self._sleep(self._retry_backoff_seconds * (2 ** (attempt - 1)))
        raise AssertionError("retry loop must return or raise")

    def _request_once(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                status_code = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in RETRYABLE_HTTP_STATUS_CODES
            message = _build_http_error_message(exc.code, body)
            raise AdapterHTTPError(
                message,
                retryable=retryable,
                status_code=exc.code,
            ) from exc
        except TimeoutError as exc:
            raise AdapterTimeoutError(
                f"AIOS request timed out after {self.config.timeout_seconds:g}s"
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise AdapterTimeoutError(
                    f"AIOS request timed out after {self.config.timeout_seconds:g}s"
                ) from exc
            raise AdapterTransportError(f"cannot reach AIOS at {url}: {exc.reason}") from exc
        except OSError as exc:
            raise AdapterTransportError(f"AIOS transport failure at {url}: {exc}") from exc

        if status_code < 200 or status_code >= 300:
            retryable = status_code in RETRYABLE_HTTP_STATUS_CODES
            raise AdapterHTTPError(
                _build_http_error_message(status_code, body),
                retryable=retryable,
                status_code=status_code,
            )

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterProtocolError(
                f"AIOS returned invalid JSON: {exc.msg} at column {exc.colno}"
            ) from exc
        if not isinstance(parsed, dict):
            raise AdapterProtocolError("AIOS response root must be a JSON object")
        return parsed


def _build_http_error_message(status_code: int, body: str) -> str:
    snippet = body.strip().replace("\n", " ")[:500]
    return f"AIOS returned HTTP {status_code}: {snippet or '<empty response>'}"
