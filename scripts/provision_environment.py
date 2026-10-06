"""One-job environment preparation; no secret reads or model server launch."""
import argparse, hashlib, json, re, subprocess, sys, time
from pathlib import Path

root=Path('/work/vllm'); evidence=Path(__file__).resolve().parent
# Place this script and the built agent wheel in a unique /work/vllm/bootstrap/
# directory before running it. Logs/evidence belong to that preparation run.
venv=root/'.venv'; version='0.31.0'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify-cuda',action='store_true',help='Require CUDA devices and tensor execution (GPU jobs only)')
args=parser.parse_args()
def run(args,timeout=1800):
    subprocess.run(args,check=True,timeout=timeout)
def fingerprint(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
sources=[root/'.env',root/'nginx.conf']
before={str(p):fingerprint(p) for p in sources}
result={'state':'preparing','vllm_version':version,'venv':str(venv),'started_at':time.time()}
def save():
    tmp=evidence/'result.tmp'; tmp.write_text(json.dumps(result,indent=2)); tmp.replace(evidence/'result.json')
save()
try:
    if sys.platform!='linux' or not root.is_dir(): raise RuntimeError('Expected mounted Linux workspace')
    mount=subprocess.check_output(['findmnt','-J','-T',str(root)],text=True)
    result['mount']=json.loads(mount)['filesystems'][0]
    if result['mount']['target']!='/work/vllm': raise RuntimeError('Expected dedicated mounted folder')
    missing=[]
    for package in ['python3-venv','ca-certificates','curl','tmux']:
        probe=subprocess.run(['dpkg-query','-W','-f=${Status}',package],capture_output=True,text=True)
        if probe.returncode or 'install ok installed' not in probe.stdout: missing.append(package)
    sudo=subprocess.run(['sudo','-n','true'],capture_output=True)
    if sudo.returncode==0:
        run(['sudo','-n','apt-get','update'],timeout=300)
        if missing: run(['sudo','-n','apt-get','install','-y','--no-install-recommends',*missing],timeout=300)
        result['system_packages']={'indexes_updated':True,'installed_missing':missing}
    else:
        result['system_packages']={'indexes_updated':False,'missing':missing,'reason':'No noninteractive sudo'}
    python=venv/'bin/python'
    if venv.exists(): raise RuntimeError('Existing .venv must be reviewed; refusing replacement')
    run([sys.executable,'-m','venv',str(venv)],timeout=120)
    run([str(python),'-m','pip','install','--upgrade','pip'],timeout=180)
    run([str(python),'-m','pip','install','vllm=='+version],timeout=2400)
    # vLLM's cu130 torch wheel fixes runtime headers at 13.0, while loose
    # compiler dependencies otherwise resolve to newer incompatible toolkits.
    run([str(python),'-m','pip','install','nvidia-cuda-nvcc==13.0.88',
         'nvidia-cuda-crt==13.0.88','nvidia-nvvm==13.0.88'],timeout=600)
    wheels=list(evidence.glob('ucloud_vllm_agent-*.whl'))
    if len(wheels)!=1: raise RuntimeError('Expected exactly one local agent wheel')
    run([str(python),'-m','pip','install','--no-deps',str(wheels[0])],timeout=120)
    run([str(python),'-m','pip','check'],timeout=120)
    freeze=subprocess.check_output([str(python),'-m','pip','freeze'],text=True)
    (evidence/'installed-requirements.txt').write_text(freeze)
    probe='''import json,torch
from importlib.metadata import version
devices=[]
for i in range(torch.cuda.device_count()):
 free,total=torch.cuda.mem_get_info(i)
 x=torch.ones(16,device=f"cuda:{i}"); ok=float((x+x).sum().cpu())==32
 devices.append({"name":torch.cuda.get_device_name(i),"capability":torch.cuda.get_device_capability(i),"free_bytes":free,"total_bytes":total,"tensor_test":ok})
import vllm
print(json.dumps({"torch":torch.__version__,"cuda_runtime":torch.version.cuda,"vllm":version("vllm"),"devices":devices}))'''
    completed=subprocess.run([str(python),'-c',probe],capture_output=True,text=True,timeout=180)
    if completed.returncode:
        (evidence/'gpu-probe-error.log').write_text(completed.stderr)
        raise RuntimeError('GPU import/probe failed; inspect gpu-probe-error.log')
    result['runtime']=json.loads(completed.stdout.strip().splitlines()[-1])
    if args.verify_cuda and (not result['runtime']['devices'] or not all(d['tensor_test'] for d in result['runtime']['devices'])):
        raise RuntimeError('CUDA execution validation failed')
    cfg=(root/'nginx.conf').read_text()
    result['nginx_local_upstream_ports']=sorted(set(re.findall(r'(?:127\.0\.0\.1|localhost):([0-9]+)',cfg)))
    result['serving_key_file_present']=(root/'.env').is_file()
    result['state']='environment_ready' if args.verify_cuda else 'environment_installed'
    result['cuda_verification_required']=not args.verify_cuda
except Exception as exc:
    result['state']='preparation_failed'; result['reason']=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
finally:
    result['template_files_unchanged']=all(fingerprint(p)==before[str(p)] for p in sources)
    result['finished_at']=time.time(); save()
print(json.dumps(result,indent=2))
sys.exit(0 if result['state'] in {'environment_ready','environment_installed'} else 1)
