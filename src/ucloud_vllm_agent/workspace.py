"""Export the packaged, credential-free remote workspace starter files locally."""
from importlib.resources import files
from pathlib import Path


def export_workspace(output: Path) -> dict:
    names = ("nginx.conf", ".env.example", "init_vllm.sh", "README.md", "job-templates.json")
    source = files("ucloud_vllm_agent").joinpath("data/ucloud-workspace")
    content = {name: source.joinpath(name).read_text(encoding="utf-8") for name in names}
    output.mkdir(parents=True, exist_ok=False)
    for name, text in content.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")
    return {"state": "template_exported", "path": str(output.resolve()), "files": list(names),
            "credentials_created": False, "uploaded": False, "job_submitted": False}
