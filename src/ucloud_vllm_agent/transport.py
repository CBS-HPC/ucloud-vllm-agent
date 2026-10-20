"""Bounded preparation SSH and nginx interactive-shell transport."""
from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4


class PreparationSSH:
    def __init__(self, settings, job: dict, root: Path):
        from ucloud_workflow.jobs import extract_ssh_command, update_ssh_config
        self.alias = settings.ssh_alias + "-vllm-prep-" + str(job["id"])
        self.config = root / "preparation-ssh.config"
        self.config.parent.mkdir(parents=True, exist_ok=True)
        command = extract_ssh_command(job)
        if not command:
            raise ValueError("Preparation job has no SSH endpoint")
        update_ssh_config(command, alias=self.alias, config_path=self.config,
                          identity_files=settings.resolved_ssh_identity_files())
        text = self.config.read_text().replace("StrictHostKeyChecking no", "StrictHostKeyChecking accept-new")
        text = text.replace("UserKnownHostsFile /dev/null", 'UserKnownHostsFile "' +
                            (root / "known_hosts").resolve().as_posix() + '"')
        self.config.write_text(text)

    def run(self, arguments: list[str], timeout: float = 60, *, input: str | None = None) -> str:
        from ucloud_workflow.transfer import ssh_command
        try:
            result = subprocess.run(ssh_command(self.alias, shlex.join(arguments), config_path=self.config),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, input=input)
            if result.returncode:
                raise RuntimeError("Preparation command failed; inspect the deployment's remote evidence")
            return result.stdout
        except subprocess.SubprocessError:
            raise RuntimeError("Preparation SSH operation timed out") from None

    def upload(self, local: Path, remote: str) -> None:
        from ucloud_workflow.transfer import scp_upload
        try:
            scp_upload(self.alias, local, remote, config_path=self.config, timeout_seconds=300)
        except Exception:
            raise RuntimeError("Preparation upload failed") from None

    def download(self, remote: str, local: Path) -> None:
        from ucloud_workflow.transfer import scp_download
        try:
            scp_download(self.alias, remote, local, config_path=self.config, timeout_seconds=60)
        except Exception:
            raise RuntimeError("Preparation evidence download failed") from None


def register_web_route(client, job_id: str, expected_url: str) -> dict:
    response = client.request("POST", "/api/jobs/interactiveSession",
                              json={"items": [{"id": job_id, "rank": 0, "sessionType": "WEB"}]}).json()
    items = response.get("responses", [])
    if len(items) != 1:
        raise ValueError("UCloud did not return one web session")
    parsed = urlsplit(items[0].get("session", {}).get("redirectClientTo", ""))
    expected = urlsplit(expected_url)
    if (parsed.scheme != "https" or parsed.netloc != expected.netloc or parsed.query
            or parsed.username or parsed.password):
        raise ValueError("Web session is not the configured public URL or requires a browser cookie")
    return {"registered": True, "hostname": parsed.hostname}


class ServingShell:
    def __init__(self, client, job: dict):
        self.client = client
        self.job = job

    def run(self, arguments: list[str], timeout: float = 60) -> str:
        import websocket
        result = self.client.request("POST", "/api/jobs/interactiveSession",
                                     json={"items": [{"id": self.job["id"], "rank": 0, "sessionType": "SHELL"}]}).json()
        item = result["responses"][0]
        session = item["session"]["sessionIdentifier"]
        provider = item["providerId"]
        domain = urlsplit(item["providerDomain"])
        if domain.scheme not in ("https", "wss") or not domain.hostname or domain.username or domain.password or domain.query or domain.fragment or domain.path not in ("", "/"):
            raise ValueError("UCloud returned an invalid secure shell provider URL")
        username = base64.b64encode(self.job["owner"]["createdBy"].encode()).decode()
        url = "wss://" + domain.netloc + "/ucloud/" + provider + "/websocket?" + urlencode({
            "session": session, "usernameHint": username})
        call = "jobs.compute." + provider + ".shell.open"
        marker = "VLLM_DONE_" + uuid4().hex
        command = shlex.join(arguments)
        payload = "stty -echo; " + command + "; vllm_result=$?; printf '\\n" + marker + ":%s\\n' \"$vllm_result\"; stty echo\n"
        output = ""
        try:
            ws = websocket.create_connection(url, timeout=15)
            try:
                ws.send(json.dumps({"call": call, "streamId": "0", "payload": {
                    "type": "initialize", "sessionIdentifier": session, "cols": 200, "rows": 40}}))
                ws.send(json.dumps({"call": call, "streamId": "1", "payload": {"type": "input", "data": payload}}))
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    ws.settimeout(min(15, max(0.1, deadline - time.monotonic())))
                    try:
                        frame = json.loads(ws.recv())
                    except websocket.WebSocketTimeoutException:
                        continue
                    output += frame.get("payload", {}).get("data", "")
                    if len(output) > 1_000_000:
                        raise ValueError("Shell output exceeds its bounded size")
                    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
                    match = re.search(r"(?m)^" + marker + r":(\d+)\r?$", cleaned)
                    if match:
                        if int(match[1]):
                            raise RuntimeError("Serving command failed; inspect the owned deployment logs")
                        return cleaned[:match.start()]
                raise RuntimeError("Serving shell operation timed out")
            finally:
                ws.close()
        except (OSError, websocket.WebSocketException):
            raise RuntimeError("Serving shell transport failed") from None

    def json(self, arguments: list[str], timeout: float = 60) -> dict:
        output = self.run(arguments, timeout)
        for line in reversed(output.splitlines()):
            if line.startswith("{"):
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        return value
                except ValueError:
                    pass
        raise ValueError("Serving helper returned no structured result")
