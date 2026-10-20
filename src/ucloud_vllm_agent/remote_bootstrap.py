"""Standalone Linux bootstrap helper. No UCloud credentials or job control."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path("/work/vllm")
ASSETS = ("nginx.conf", "init_vllm.sh", "README.md", ".env.example")

# Executed before SCP: establish a private, owned staging directory on the mount.
STAGE_PROGRAM = r'''
import json,os,re,stat,subprocess,sys
from pathlib import Path
owner=sys.argv[1]
if not re.fullmatch(r"[a-f0-9]{32}",owner): raise ValueError("Invalid bootstrap identity")
root=Path("/work/vllm")
mount=json.loads(subprocess.check_output(["findmnt","-J","-T",str(root)],text=True))["filesystems"][0]
if root.is_symlink() or mount["target"]!=str(root) or mount["fstype"] in ("overlay","tmpfs"):
 raise ValueError("Persistent /work/vllm mount required")
if sys.version_info[:2]!=(3,12): raise ValueError("Reviewed Python 3.12 preparation image required")
control=root/".bootstrap"
control.mkdir(mode=0o700,exist_ok=True)
if control.is_symlink() or control.stat().st_uid!=os.getuid() or control.stat().st_mode&0o077:
 raise ValueError("Unsafe bootstrap control directory")
stage=control/owner
if not stage.exists():
 stage.mkdir(mode=0o700)
 with (stage/".owner").open("x") as marker: marker.write(owner)
marker=stage/".owner"
if stage.is_symlink() or stage.stat().st_uid!=os.getuid() or stage.stat().st_mode&0o077 or marker.is_symlink() or marker.read_text()!=owner:
 raise ValueError("Staging ownership mismatch")
print(json.dumps({"stage":str(stage),"mount_type":mount["fstype"]}))
'''


def verify_stage(stage: Path, owner: str, root: Path = ROOT) -> dict:
    mount = json.loads(subprocess.check_output(["findmnt", "-J", "-T", str(root)], text=True))["filesystems"][0]
    if root.is_symlink() or mount["target"] != str(root) or mount["fstype"] in ("overlay", "tmpfs"):
        raise ValueError("Persistent workspace mount required")
    if stage.is_symlink() or (stage / ".owner").is_symlink() or (stage / ".owner").read_text() != owner:
        raise ValueError("Staging ownership mismatch")
    control = root / ".bootstrap"
    if control.is_symlink() or control.stat().st_uid != os.getuid() or control.stat().st_mode & 0o077:
        raise ValueError("Unsafe bootstrap control directory")
    if stage.parent != root / ".bootstrap" or stage.name != owner or stage.stat().st_uid != os.getuid() or stage.stat().st_mode & 0o077:
        raise ValueError("Unsafe staging path or permissions")
    return {"mount_type": mount["fstype"], "mount_source": mount["source"]}


def install_assets(stage: Path, root: Path = ROOT) -> dict:
    manifest = json.loads((stage / "manifest.json").read_text())
    if set(manifest) != set(ASSETS):
        raise ValueError("Unexpected bootstrap asset manifest")
    payload = {}
    for name in ASSETS:
        source, target = stage / name, root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Invalid staged asset")
        payload[name] = source.read_bytes()
        if hashlib.sha256(payload[name]).hexdigest() != manifest[name]:
            raise ValueError("Staged asset checksum mismatch")
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_bytes() != payload[name])):
            raise ValueError("Existing workspace asset differs; preserved without replacement")
    for name, content in payload.items():
        target = root / name
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            target.chmod(0o755 if name.endswith(".sh") else 0o644)
    return {"state": "assets_ready", "files": manifest, "credentials_created": False}


def verify_credentials(expected_hash: str, root: Path = ROOT) -> dict:
    secret = root / ".env"
    if secret.is_symlink() or not secret.is_file():
        raise ValueError("Provision the remote workspace .env separately")
    info = secret.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Remote .env must be owner-only and owned by the job user")
    import remote
    env = remote.load_runtime_secrets({"hf_env_file": str(secret), "secret_file": str(secret), "cache_dir": str(root / ".cache/hf")})
    if hashlib.sha256(env["VLLM_API_KEY"].encode()).hexdigest() != expected_hash:
        raise ValueError("Local and remote serving keys differ")
    return {"state": "credentials_verified", "key_matches": True, "hf_token_present": bool(env.get("HF_TOKEN"))}


def provision_credentials(values: dict, root: Path = ROOT) -> dict:
    if (not isinstance(values, dict) or set(values) != {"VLLM_API_KEY", "HF_TOKEN"}
            or not isinstance(values["VLLM_API_KEY"], str) or not values["VLLM_API_KEY"]
            or any(not isinstance(v, str) or any(c in v for c in "\r\n\x00\"'") for v in values.values())):
        raise ValueError("Invalid selected credential values")
    secret = root / ".env"
    # Exclusive creation only. An uncertain partial write needs explicit inspection,
    # never an automatic overwrite or a second persistent credential file.
    descriptor = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("HF_TOKEN=" + values["HF_TOKEN"] + "\nVLLM_API_KEY=" + values["VLLM_API_KEY"] + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"state": "credentials_provisioned", "keys_written": ["HF_TOKEN", "VLLM_API_KEY"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("install", "verify-credentials", "provision-credentials"))
    parser.add_argument("--owner", required=True)
    parser.add_argument("--key-sha256")
    args = parser.parse_args()
    try:
        stage = Path(__file__).resolve().parent
        mount = verify_stage(stage, args.owner)
        if args.operation == "install":
            result = install_assets(stage)
        elif args.operation == "provision-credentials":
            result = provision_credentials(json.load(sys.stdin))
        else:
            result = verify_credentials(args.key_sha256 or "")
        print(json.dumps({**result, **mount}))
        return 0
    except Exception as error:
        # Never include input, environment, remote credential contents or raw errors.
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({"state": "bootstrap_failed", "reason": reason}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
