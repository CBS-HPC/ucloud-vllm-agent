# UCloud vLLM runtime workspace

Both the CPU preparation job and GPU nginx serving job mount this persistent
folder at `/work/vllm`. It belongs to one operator/project and one active
deployment. Source: https://github.com/CBS-HPC/ucloud-vllm-agent.

| Path | Purpose |
| --- | --- |
| `nginx.conf` | Reviewed proxy config: job port 8080 to loopback 8000, preserving `/v1/` and streaming. |
| `.env.example` | Credential-free remote environment template. |
| `.env` | Operator-created HF_TOKEN and VLLM_API_KEY, mode 0600. Never print, commit or overwrite implicitly. |
| `init_vllm.sh` | nginx initialization entry point; uploaded by the CLI during activation. |
| `.venv/` | Prepared Python 3.12 environment with vLLM 0.31.0 and reviewed CUDA packages. |
| `deployments/<name>/<run>/` | Generated model-specific helpers, configuration, logs and verification evidence. |
| `active` | Agent-managed symlink selecting the reviewed deployment. |
| `cache/huggingface/` | Pinned model weights retained between allocations. |
| `cache/kernels/` | Runtime/hardware-specific compilation caches. |

CPU preparation must finish and `active` must exist before initialization starts
serving. Installing system packages in a CPU container does not update the GPU
image. Use compatible application images and the recorded runtime baseline.

The local deployment CLI generates runtime.json, remote helpers and endpoint
probes from tracked Python sources. Do not copy helpers from unrelated deployments
or hand-edit generated files. Weights, environments, caches, secrets and journals
are operator/generated state, not Git templates.

Manage deployments through the local project and preserve its journals. nginx
running or a submitted job is not readiness: verify authentication and the actual
task through loopback, nginx and public HTTPS. A successful hosting job remains
allocated until explicitly released or expired. Stopping the model does not
release its GPU. Renewal replaces the allocation with downtime; the operator owns
expiry and resource use.

This is a generic starter template, not evidence of live deployment. Validate
nginx.conf with `nginx -t` in the selected image and endpoint tests before use.
First-time setup: docs/ucloud-workspace-template.md in the source repository.
