# Upstream integration boundary

The operator's moody_agent uses released ucloud-workflow, explicit template IDs,
persistent environments and isolated case artifacts. Here the workload is an
ongoing HTTP service and must not inherit automatic batch-job termination.

## Released product adapter
The optional dependency is pinned to v0.1.6. preview_job_specification calls the
released build_job_specification with a complete product reference or preserves
the template product. It never generates a CPU product from a GPU name. The
adapter preserves template application parameters, mounts and public-link resources.
CLI preview-job performs read-only lookup through UCLOUD_TEMPLATE_JOB_ID and
returns a sanitized preview, not raw application parameters or credentials.

token-status selects UCLOUD_TOKEN_ID from API metadata. Expiry must cover the
requested hours plus a one-hour margin. The operator must supply the matching
ID; the agent cannot infer it from the credential. No tokens are created/rotated.

## Operator template contract
- UCLOUD_SSH_ALIAS=ucloud is the upstream SSH alias setting (also its default).
  UCLOUD_SSH_CONFIG_PATH selects the SSH config file; neither setting enables deployment by itself.
- UCLOUD_WORK_FOLDER=/work/vllm is the mounted working root.
- /work/vllm/nginx.conf is configured and loaded by the template.
- /work/vllm/.env supplies HF_TOKEN and remains read-only to the runtime helper.
- /work/vllm/.env supplies both HF_TOKEN and VLLM_API_KEY, with mode 0600.
  The local project .env is retained and never uploaded.
- A bare public hostname is normalized to https://HOST/v1 for plans; actual TLS,
  route, authentication and inference still need an endpoint check.

## Hosting lifecycle
Live preparation on 2026-10-06 established that the nginx 1.31.2 application
rejects SSH-enabled submission (HTTP 400: application does not support SSH).
Use a separate SSH-capable CPU preparation template, identified by
UCLOUD_PREPARATION_TEMPLATE_JOB_ID, with the same writable /work/vllm mount.
UCLOUD_TEMPLATE_JOB_ID continues to identify the nginx serving template. The CLI consumes both explicit IDs and journals preparation/hosting separately. Preparing files is separate from starting vLLM: the serving
application must expose a verified startup mechanism. UCloud documents an
[Initialization bash script](https://docs.cloud.sdu.dk/hands-on/init-sh.html)
for [nginx](https://docs.cloud.sdu.dk/Apps/nginx.html); validate this against the
pinned serving application version before wiring it into submission.
A mounted virtual environment
also requires compatible OS libraries, Python and CPU architecture across images;
system packages installed in the preparation container do not update the serving image.

Live hosting on 2026-10-06 confirmed that the nginx initialization script can
launch the prepared runtime. For the pinned CUDA 13 environment, expose
`.venv/bin` (including `ninja`) and the installed `nvidia/cu13/bin` (`nvcc`) on
PATH, and set CUDA_HOME to the installed CUDA toolkit. `scripts/init_vllm.sh`
validates those paths before launch; it does not modify drivers or nginx.
Compiler, CRT and NVVM packages are pinned to 13.0.88 to match torch cu130.
FlashInfer links against a deployment-local libcudart.so alias to the installed
libcudart.so.13; package and system library directories are unchanged.
The nginx image also provides a UCloud interactive SHELL session despite lacking
SSH. This is useful for bounded recovery; the CLI uses it for bounded verification and managed-session recovery.

Register the public web route after the serving job starts using
`POST /api/jobs/interactiveSession` with the job ID, rank 0 and sessionType WEB.
The live public-link session returned the configured hostname without a cookie
authorization redirect. Before registration, requests returned HTTP 449 or the
gateway's JWT-format rejection for the vLLM bearer key. Verify the returned host
and then test the actual public API; HTTP 200 from session creation is not model
readiness. This behavior was checked against the
[UCloud session implementation](https://github.com/SDU-eScience/UCloud/blob/master/provider-integration/im2/pkg/controller/jobs.go).

deploy implements the full workflow; live CLI deployment/replacement passed on 2026-10-06.
See automated-lifecycle.md for commands, ownership checks and recovery limitations.

Implemented invariants, exercised on the B200 MIG baseline:
1. Persist the submitted job ID immediately and block duplicates on unknown outcomes.
2. Reuse upstream SSH transport with explicit configuration and verified host keys.
   Review released transport behavior rather than adopting unsafe defaults.
3. Verify template mounts, nginx port, secret sources and allocated GPU visibility.
4. Provision/start vLLM in the owned session, then run local/proxy/external checks.
5. Keep the job alive after success and local exit; add explicit recovery/status/release.
6. Validate a real authorized template deployment with a pinned model/runtime.

Do not edit dependency source or duplicate generic UCloud product/transport logic
here. Route generic improvements to the owning ucloud-api project.
