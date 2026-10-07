from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from ucloud_vllm_agent.checks import check_endpoint
from ucloud_vllm_agent.config import validate_base_url


def test_managed_service_checks_without_models_route(api):
    url, handler = api
    result = check_endpoint(url, "test-model", "testing-key", include_models=False, timeout=300)
    assert result["passed"]
    assert [item["name"] for item in result["checks"]] == [
        "chat_inference", "streaming_inference", "chat_requires_authentication", "chat_rejects_invalid_key"]


@pytest.fixture
def api():
    class Handler(BaseHTTPRequestHandler):
        public_access = False
        incomplete_stream = False
        accept_any_key = False
        response_model = "test-model"
        chat_content = "OK"
        stream_finish_reason = True
        stream_error = False
        listed_model = "test-model"

        def log_message(self, *args):
            pass

        def respond(self, data, content_type="application/json", status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            authorization = self.headers.get("Authorization")
            if self.public_access or authorization == "Bearer testing-key" or (self.accept_any_key and authorization):
                return True
            self.respond(b"{}", status=401)
            return False

        def do_GET(self):
            if self.permitted():
                self.respond(json.dumps({"data": [{"id": self.listed_model}]}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not self.permitted():
                return
            if body.get("stream"):
                event = {"model": self.response_model, "choices": [{"delta": {"content": "OK"}}]}
                content = b"data: " + json.dumps(event).encode() + b"\n\n"
                if self.stream_error:
                    content += b'data: {"error":{"message":"private backend details"}}\n\n'
                if self.stream_finish_reason:
                    event["choices"] = [{"delta": {}, "finish_reason": "stop"}]
                    content += b"data: " + json.dumps(event).encode() + b"\n\n"
                if not self.incomplete_stream:
                    content += b"data: [DONE]\n\n"
                self.respond(content, "text/event-stream")
            else:
                self.respond(json.dumps({"model": self.response_model, "choices": [
                    {"message": {"content": self.chat_content}, "finish_reason": "stop"}]}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", Handler
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_real_http_chat_streaming_and_authentication(api):
    url, _ = api
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["passed"]
    assert len(result["checks"]) == 7
    assert "testing-key" not in json.dumps(result)


def test_accepting_anonymous_inference_fails(api):
    url, handler = api
    handler.public_access = True
    result = check_endpoint(url, "test-model", token="testing-key")
    assert not result["passed"]
    assert not result["checks"][-1]["passed"]


def test_incomplete_stream_fails(api):
    url, handler = api
    handler.incomplete_stream = True
    result = check_endpoint(url, "test-model", token="testing-key")
    assert not result["passed"]
    assert not result["checks"][2]["passed"]


def test_accepting_arbitrary_bearer_keys_fails(api):
    url, handler = api
    handler.accept_any_key = True
    result = check_endpoint(url, "test-model", token="testing-key")
    assert not result["passed"]
    assert all(check["passed"] for check in result["checks"][:5])
    assert all(check.get("reason") == "invalid_key_accepted" for check in result["checks"][5:])


@pytest.mark.parametrize("content", ["", "   ", None, {"text": "OK"}])
def test_empty_or_invalid_inference_content_fails(api, content):
    url, handler = api
    handler.chat_content = content
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["checks"][1]["reason"] == "missing_inference_content"


def test_response_from_wrong_model_fails(api):
    url, handler = api
    handler.response_model = "wrong-model"
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["checks"][1]["reason"] == "unexpected_response_model"
    assert result["checks"][2]["reason"] == "unexpected_response_model"


def test_expected_model_absent_fails(api):
    url, handler = api
    handler.listed_model = "other-model"
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["checks"][0]["reason"] == "expected_model_absent"


def test_done_without_finish_reason_fails(api):
    url, handler = api
    handler.stream_finish_reason = False
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["checks"][2]["reason"] == "incomplete_stream"


def test_stream_error_does_not_leak_backend_details(api):
    url, handler = api
    handler.stream_error = True
    result = check_endpoint(url, "test-model", token="testing-key")
    assert result["checks"][2]["reason"] == "stream_error"
    assert "private backend details" not in json.dumps(result)


@pytest.mark.parametrize("public_access,expected_exit", [(False, 0), (True, 1)])
def test_cli_exit_code_and_json_report(api, tmp_path, monkeypatch, capsys, public_access, expected_exit):
    from ucloud_vllm_agent.cli import main
    url, handler = api
    handler.public_access = public_access
    monkeypatch.setenv("VLLM_API_KEY", "testing-key")
    monkeypatch.setattr("ucloud_vllm_agent.cli.load_env", lambda: None)
    output = tmp_path / "checks.json"
    code = main(["check", "--base-url", url, "--model", "test-model", "--output", str(output)])
    assert code == expected_exit
    report = json.loads(output.read_text())
    assert report["passed"] == (expected_exit == 0)
    assert len(report["checks"]) == 7
    assert "testing-key" not in output.read_text() + capsys.readouterr().out


@pytest.mark.parametrize("url", ["http://public.example/v1", "https://user:secret@example/v1",
                               "https://example/v1?key=secret", "https://example/other"])
def test_invalid_endpoint_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)
