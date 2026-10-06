"""Standalone CPU preparation; no allocation or secret provisioning."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import remote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-sha256", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = remote.read_runtime(root)
    result = {"state": "preparation_failed"}
    with (Path('/work/vllm') / '.preparation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            mount = json.loads(subprocess.check_output(['findmnt', '-J', '-T', '/work/vllm'], text=True))['filesystems'][0]
            if mount['target'] != '/work/vllm' or mount['fstype'] in ('overlay', 'tmpfs'):
                raise ValueError('Preparation requires the persistent shared /work/vllm mount')
            if sys.version_info[:2] != (3, 12):
                raise ValueError('Preparation image must provide Python 3.12')
            secret = Path(config['secret_file'])
            if not secret.is_file() or secret.stat().st_mode & 0o077:
                raise ValueError('Provision the workspace .env with owner-only permissions first')
            env = remote.load_runtime_secrets(config)
            if hashlib.sha256(env['VLLM_API_KEY'].encode()).hexdigest() != args.key_sha256:
                raise ValueError('Local verification key differs from the provisioned serving key')
            python = remote.interpreter(config)
            if not python.exists():
                with (root / 'installation.log').open('w') as log:
                    subprocess.run([sys.executable, '-m', 'venv', config['venv_dir']], check=True, stdout=log, stderr=log, timeout=120)
                    subprocess.run([str(python), '-m', 'pip', 'install', 'vllm==0.31.0',
                                    'nvidia-cuda-nvcc==13.0.88', 'nvidia-cuda-crt==13.0.88', 'nvidia-nvvm==13.0.88'],
                                   check=True, stdout=log, stderr=log, timeout=2400)
            # Existing environments are validated, never changed during another job's serving.
            probe = "from importlib.metadata import version; assert version('vllm')=='0.31.0'; assert all(version(p)=='13.0.88' for p in ['nvidia-cuda-nvcc','nvidia-cuda-crt','nvidia-nvvm'])"
            subprocess.run([str(python), '-c', probe], check=True, capture_output=True, timeout=60)
            subprocess.run([str(python), '-m', 'pip', 'check'], check=True, capture_output=True, timeout=60)
            cache_code = """import json,os,sys
from pathlib import Path
from huggingface_hub import snapshot_download
import remote
root=Path(sys.argv[1]);c=remote.read_runtime(root);env=remote.load_runtime_secrets(c)
path=snapshot_download(c['model'],revision=c['revision'],cache_dir=str(Path(c['cache_dir'])/'hub'),token=env.get('HF_TOKEN') or None,
 allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken','*.jinja'],max_workers=2)
(root/'cache-result.json').write_text(json.dumps({'state':'model_cached','model':c['model'],'revision':c['revision']}))
"""
            with (root / 'cache-download.log').open('w') as log:
                subprocess.run([str(python), '-c', cache_code, str(root)], cwd=root,
                               check=True, stdout=log, stderr=log, timeout=1800)
            result = {'state': 'prepared', 'mount_source': mount['source'], 'mount_type': mount['fstype'],
                      'model': config['model'], 'revision': config['revision'], 'key_matches': True,
                      'environment': config['venv_dir']}
        except Exception as error:
            result['reason'] = str(error) if isinstance(error, ValueError) else type(error).__name__
        finally:
            temporary = root / 'preparation-result.tmp'
            temporary.write_text(json.dumps(result, indent=2)); temporary.replace(root / 'preparation-result.json')
    return 0 if result['state'] == 'prepared' else 1


if __name__ == '__main__':
    raise SystemExit(main())
