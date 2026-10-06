from __future__ import annotations

import json
import os
import time
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import validate_base_url


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class VerificationFailure(ValueError):
    """A stable, non-secret failure code suitable for verification reports."""


def check_endpoint(base_url: str, model: str, token: str | None = None) -> dict:
    base_url = validate_base_url(base_url)
    token = token or os.getenv("VLLM_API_KEY")
    if not token:
        raise ValueError("VLLM_API_KEY is required for endpoint verification")
    opener = build_opener(NoRedirects())
    checks = []

    def request(route: str, payload: dict | None = None, *, authenticated=True, api_key=None):
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + (token if api_key is None else api_key)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        return opener.open(Request(base_url + route, data=body, headers=headers), timeout=30)

    def record(name, function):
        try:
            details = function() or {}
            checks.append({"name": name, "passed": True, **details})
        except HTTPError as exc:
            checks.append({"name": name, "passed": False, "reason": f"HTTP {exc.code}"})
            exc.close()
        except VerificationFailure as exc:
            checks.append({"name": name, "passed": False, "reason": str(exc)})
        except (URLError, OSError, ValueError, KeyError, IndexError, TypeError):
            checks.append({"name": name, "passed": False, "reason": "invalid_response_or_transport_failure"})

    def decode(response):
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Oversized API response")
        return json.loads(raw)

    def models():
        with request("/models") as response:
            data = decode(response)
        if model not in [item["id"] for item in data["data"]]:
            raise VerificationFailure("expected_model_absent")

    payload = {"model": model, "messages": [{"role": "user", "content": "Reply with the word OK."}],
               "max_tokens": 32, "temperature": 0}

    def chat():
        with request("/chat/completions", payload) as response:
            data = decode(response)
        if data.get("model") != model:
            raise VerificationFailure("unexpected_response_model")
        content = data["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise VerificationFailure("missing_inference_content")
        if not data["choices"][0].get("finish_reason"):
            raise VerificationFailure("missing_finish_reason")

    def stream():
        start = time.monotonic()
        event_times = []
        complete = False
        finished = False
        with request("/chat/completions", {**payload, "stream": True}) as response:
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                raise ValueError("Streaming response is not SSE")
            for _ in range(1000):
                if time.monotonic() - start > 90:
                    raise ValueError("Streaming deadline exceeded")
                line = response.readline(65537)
                if len(line) > 65536:
                    raise ValueError("Oversized SSE event")
                if not line:
                    break
                if not line.startswith(b"data:"):
                    continue
                event = line[5:].strip()
                if event == b"[DONE]":
                    complete = True
                    break
                data = json.loads(event)
                if "error" in data:
                    raise VerificationFailure("stream_error")
                if not data.get("choices"):
                    continue
                if data.get("model") != model:
                    raise VerificationFailure("unexpected_response_model")
                choice = data["choices"][0]
                finished = finished or bool(choice.get("finish_reason"))
                content = choice.get("delta", {}).get("content")
                if content is not None and not isinstance(content, str):
                    raise VerificationFailure("invalid_stream_content")
                if content and content.strip():
                    event_times.append(round(time.monotonic() - start, 3))
        if not complete or not finished or not event_times:
            raise VerificationFailure("incomplete_stream")
        return {"content_events": len(event_times), "content_event_times_seconds": event_times,
                "note": "SSE delivery observed; timings alone do not prove absence of upstream buffering."}

    def reject(route, body=None, *, api_key=None):
        try:
            with request(route, body, authenticated=api_key is not None, api_key=api_key):
                pass
        except HTTPError as exc:
            if exc.code in (401, 403):
                exc.close()
                return {"http_status": exc.code}
            raise
        raise VerificationFailure("invalid_key_accepted" if api_key is not None else "anonymous_request_accepted")

    record("expected_model", models)
    record("chat_inference", chat)
    record("streaming_inference", stream)
    record("models_require_authentication", lambda: reject("/models"))
    record("chat_requires_authentication", lambda: reject("/chat/completions", payload))
    # Randomness makes accidental equality with any real configured key negligible;
    # the assertion is always the same: an invalid credential must be rejected.
    invalid_key = "connectivity-invalid-" + secrets.token_hex(32)
    while invalid_key == token:
        invalid_key = "connectivity-invalid-" + secrets.token_hex(32)
    record("models_reject_invalid_key", lambda: reject("/models", api_key=invalid_key))
    record("chat_rejects_invalid_key", lambda: reject("/chat/completions", payload, api_key=invalid_key))
    passed = all(item["passed"] for item in checks)
    return {"base_url": base_url, "model": model, "passed": passed, "checks": checks,
            "state": ("endpoint_verified" if passed else "verification_failed"),
            "note": "This verifies this endpoint only; job expiry, persistent mounts and allocation need separate records."}
