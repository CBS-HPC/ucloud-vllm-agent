"""Atomic deployment journals and a cross-process operation lock."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Windows sync/indexing tools can briefly hold the destination open.
    # Retry the same atomic replacement, never the preceding network operation.
    for attempt in range(6):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if os.name != "nt" or attempt == 5:
                raise
            time.sleep(0.1 * (attempt + 1))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class Journal:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "deployment.json"
        self.data = load(self.path)

    def update(self, state: str | None = None, **values) -> dict:
        if state is not None:
            self.data["state"] = state
        self.data.update(values)
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        save(self.path, self.data)
        return self.data

    def submitted(self, kind: str, client, specification: dict) -> str:
        """Persist intent before a request; ambiguous responses always block retry."""
        key = kind + "_job_id"
        if self.data.get(key):
            return self.data[key]
        outcome = self.data.get(kind + "_submission")
        if outcome in ("pending", "unknown"):
            raise ValueError("Submission outcome is unknown; recover the existing request before retry")
        self.update(kind + "_submitting", **{kind + "_submission": "pending",
                                              kind + "_submission_name": specification["name"]})
        try:
            from ucloud_workflow.jobs import extract_job_id
            job_id = extract_job_id(client.submit_job(specification))
        except Exception:
            # HTTP errors can include sensitive bodies; never persist their text.
            self.update("submission_unknown", **{kind + "_submission": "unknown"})
            raise RuntimeError("Submission outcome recorded as unknown; no automatic retry") from None
        self.update(kind + "_submitted", **{key: job_id, kind + "_submission": "known"})
        return job_id


@contextmanager
def operation_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Another lifecycle operation is already running") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
