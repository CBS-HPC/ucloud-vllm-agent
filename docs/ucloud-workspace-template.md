# Reusable UCloud workspace and job templates

The repository includes all starter configuration and the Python sources used
by the automated remote workflow. No file needs to be recovered from the original
operator's UCloud folder. The packaged starter assets live in
[`src/ucloud_vllm_agent/data/ucloud-workspace/`](../src/ucloud_vllm_agent/data/ucloud-workspace/).

## Export locally

From this checkout's installed environment:

```powershell
vllm-agent workspace-template --output artifacts/ucloud-workspace
```

This command is offline, does not load .env and refuses an existing destination.
It exports `nginx.conf`, `.env.example`, `init_vllm.sh`, a generic `README.md`
and `job-templates.json`. These assets are included in built wheels and source
archives. It does not create real credentials, upload files, create templates,
submit jobs or change an existing nginx server.

## First-time UCloud setup

These steps combine optional [Link/public-key resource setup](resource-setup.md)
with manual shared-folder, credentials and template setup. Resource setup uses
released ucloud-api v0.1.7 and starts no jobs. Template creation and shared-folder
setup remain separate; Link support alone does not automate them. See the
[onboarding roadmap](../TODO.md#researcher-onboarding-roadmap) for bootstrap limits.

1. Obtain a UCloud project with the required CPU/GPU allocation and permissions,
   register your SSH public key, and reserve your own public URL. The operator
   owns these resources. You can plan/apply your own Link and optional public-key
   registration using the resource setup guide. Never reuse another researcher's
   project/token/job IDs.
2. Create a persistent UCloud Files folder named `vllm`, mounted at `/work/vllm`
   by both templates. Preserve the same Files folder identity across jobs.
   Upload the reviewed nginx.conf, init_vllm.sh and generic README.md there.
   Keep job-templates.json locally as the setup checklist; it is not an API request.
3. On UCloud, create `/work/vllm/.env` using the remote `.env.example` as a guide.
   Enter HF_TOKEN if needed and a strong VLLM_API_KEY in an editor. Restrict the
   real file to its owner (`chmod 600 /work/vllm/.env`). Do not overwrite an
   existing file, paste credentials into commands, or upload the local project .env.
   Work through an authorized setup session; creating one consumes resources.
4. Create/select an SSH-capable **CPU preparation** job in that project with
   Python 3.12, venv/pip and findmnt, mounting that folder writable. Historical
   baseline: coder-python 1.89.1. Record its ID as UCLOUD_PREPARATION_TEMPLATE_JOB_ID.
5. Create/select the **GPU nginx serving** job using nginx 1.31.2, the same writable
   folder and your reserved public URL. Select nginx.conf in its configuration
   field and init_vllm.sh in its Initialization script field. Use UCloud Files
   picker paths here, not invented `/work` paths: the CLI preserves the config
   selection and derives the initialization file beside it. SSH is disabled for
   this serving application. Record UCLOUD_TEMPLATE_JOB_ID.
6. Fill the local project's root `.env` from its separate root `.env.example`:
   project UUID, both template IDs, UCloud token and token ID, SSH settings,
   public URL, and the same VLLM_API_KEY. UCloud API credentials stay local.
   Review a hosting profile, then run the read-only checks and preview described
   in [deterministic hosting](deterministic-hosting.md).

The initialization script needs the CLI's prepared `active` symlink and runtime
bundle. A first template setup job may therefore lack a working model; this is
not endpoint validation. Creating templates may allocate resources. Do not leave
temporary setup allocations running unintentionally; release only exact jobs you
own and intend to stop. Retain their IDs for the template-based workflow.

This guide records the existing supported baseline, not permission to allocate
jobs. New image versions require compatibility validation. Both images must
support the same shared Python environment; the GPU image additionally needs
the runtime's CUDA libraries and tmux.

## Configuration and code inventory

| Needed artifact | Tracked source / how it reaches UCloud |
| --- | --- |
| Local environment template | Root `.env.example`; stays local. |
| Remote environment template | Packaged `data/ucloud-workspace/.env.example`; real values supplied on UCloud. |
| nginx proxy | Packaged `data/ucloud-workspace/nginx.conf`; reviewed/uploaded once by operator. |
| Initialization script | Packaged `data/ucloud-workspace/init_vllm.sh`; same source used by prepare-profile and export. Uploaded on activation. |
| CPU/GPU job requirements | Packaged `data/ucloud-workspace/job-templates.json`; operator setup recipe, no credentials or real IDs. Generic submission stays in ucloud-api. |
| Runtime workspace context | Packaged `data/ucloud-workspace/README.md`; generic template with no original job IDs/URL. |
| Chat and PII profiles | `config/hosting.qwen-small.json`, `config/hosting.pii-tracer.json`; edit a local copy for the chosen project/workload. |
| Request and machine examples | `config/request.example.json`, packaged `data/machines.json`; illustrative until verified against your project. |
| Model-specific runtime.json | Generated by planner.py and hosting.py from a reviewed profile and pinned model metadata. Never hand-copy another deployment. |
| Runtime/environment/cache helpers | `src/ucloud_vllm_agent/remote.py` and `remote_prepare.py`; copied into each prepared bundle. |
| PII adapter | `src/ucloud_vllm_agent/pii_service.py`; copied for the PII task only. |
| Remote endpoint probes | `config.py`, `checks.py`, `pii_checks.py`; copied into the bundle's endpoint_probe package. |
| Upload checksums/job settings | Generated payload-manifest.json and job-settings.json; owned by the reviewed deployment. |
| Client verification examples | `notebooks/test_model.ipynb`, `notebooks/test_pii_tracer.ipynb`; stay local. |

The existing `scripts/provision_environment.py` is a historical/manual diagnostic
helper. Automated CPU provisioning uses remote_prepare.py; do not run both setup
paths or maintain another bootstrap implementation. Dated operator-specific
history remains in docs/workspace-readme.md and docs/live-validation.md; it is not
part of the generic workspace template.

## nginx behavior and validation

The starter is a full nginx configuration, not a conf.d fragment. It listens on
UCloud's HTTP port 8080 and forwards `/v1/` unchanged to loopback port 8000. The
PII profile exposes its authenticated adapter there; its backend stays internal.
Bearer authentication is enforced by the serving application. Proxy buffering
and caching are disabled for streaming; body size is limited to 16 MiB and proxy
read/send timeouts are 600 seconds. Review these limits for the workload.

Public HTTPS is provided by UCloud routing, not this internal HTTP server. This
new generic config has not been validated in a live UCloud job. Before adoption,
run `nginx -t -c /work/vllm/nginx.conf` inside the selected image and the real
task/authentication/streaming checks through the public endpoint. Preserve an
existing working config unless its replacement is explicitly requested.

Sources: [UCloud nginx configuration and port](https://docs.cloud.sdu.dk/Apps/nginx.html),
[nginx proxy URI, buffering and timeouts](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
