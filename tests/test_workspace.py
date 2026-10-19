import json

from ucloud_vllm_agent.cli import main
from ucloud_vllm_agent.hosting import INIT_SCRIPT


def test_workspace_export_is_offline_complete_and_never_overwrites(tmp_path, monkeypatch, capsys):
    def forbidden():
        raise AssertionError("Must not load credentials")
    monkeypatch.setattr("ucloud_vllm_agent.cli.load_env", forbidden)
    output = tmp_path / "workspace"
    assert main(["workspace-template", "--output", str(output)]) == 0
    assert {p.name for p in output.iterdir()} == {"nginx.conf", ".env.example", "init_vllm.sh", "README.md", "job-templates.json"}
    recipes = json.loads((output / "job-templates.json").read_text())
    assert recipes["serving"]["application"] == {"name": "nginx", "version": "1.31.2"}
    assert (output / "init_vllm.sh").read_text() == INIT_SCRIPT
    assert all(b"\r" not in path.read_bytes() for path in output.iterdir())
    values = [line for line in (output / ".env.example").read_text().splitlines() if line and not line.startswith("#")]
    assert values == ["HF_TOKEN=", "VLLM_API_KEY="]
    (output / ".env").write_text("operator-owned sentinel")
    assert main(["workspace-template", "--output", str(output)]) == 1
    assert (output / ".env").read_text() == "operator-owned sentinel"
    assert '"job_submitted": false' in capsys.readouterr().out
