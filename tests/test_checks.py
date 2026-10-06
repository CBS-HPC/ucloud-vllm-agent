from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from ucloud_vllm_agent.checks import check_endpoint
from ucloud_vllm_agent.config import validate_base_url


@pytest.fixture
def api():
    class Handler(BaseHTTPRequestHandler):
        public_access = False
        incomplete_stream = False

        def log_message(self, *args):
            pass

        def respond(self, data, content_type="application/json", status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            if self.public_access or self.headers.get("Authorization") == "Bearer testing-key":
                return True
            self.respond(b"{}", status=401)
            return False

        def do_GET(self):
            if self.permitted():
                self.respond(json.dumps({"data": [{"id": "test-model"}]}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not self.permitted():
                return
            if body.get("stream"):
                content = b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
                if not self.incomplete_stream:
                    content += b"data: [DONE]\n\n"
                self.respond(content, "text/event-stream")
            else:
                self.respond(b'{"choices":[{"message":{"content":"OK"}}]}')

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
    assert len(result["checks"]) == 5
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


@pytest.mark.parametrize("url", ["http://public.example/v1", "https://user:secret@example/v1",
                               "https://example/v1?key=secret", "https://example/other"])
def test_invalid_endpoint_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)
