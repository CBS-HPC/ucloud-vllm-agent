"""Offline installed-layout smoke check; run after python -m build."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

wheel = max(Path("dist").glob("*.whl"), key=lambda path: path.stat().st_mtime_ns)
with tempfile.TemporaryDirectory(prefix="vllm-wheel-smoke-") as temporary:
    root = Path(temporary)
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(root / "package")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("UCLOUD_", "VLLM_", "HF_"))}
    env["PYTHONPATH"] = str(root / "package")
    result = subprocess.run([sys.executable, "-S", "-m", "ucloud_vllm_agent", "workspace-template", "--output", str(root / "export")],
                            cwd=root, env=env, capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert not report["uploaded"] and not report["job_submitted"]
    assert (root / "export/.env.example").is_file() and not (root / "export/.env").exists()
    assert {path.name for path in (root / "export").iterdir()} == set(report["files"])
    print("Wheel templates exported offline without optional dependencies or credentials.")
