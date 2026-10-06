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
- UCLOUD_WORK_FOLDER=/work/vllm is the mounted working root.
- /work/vllm/nginx.conf is configured and loaded by the template.
- /work/vllm/.env supplies HF_TOKEN and remains read-only to the runtime helper.
- /work/vllm/secrets/vllm.env supplies VLLM_API_KEY separately before launch.
- A bare public hostname is normalized to https://HOST/v1 for plans; actual TLS,
  route, authentication and inference still need an endpoint check.

## Hosting lifecycle still pending
deploy exits before network calls until automated provisioning and recovery are
implemented/tested. A released product API alone is not a complete deployment.
Reviewed runtime bundles can be used in an existing explicitly authorized job.

Before enabling automated deployment:
1. Persist the submitted job ID immediately and block duplicates on unknown outcomes.
2. Reuse upstream SSH transport with explicit configuration and verified host keys.
   Review released transport behavior rather than adopting unsafe defaults.
3. Verify template mounts, nginx port, secret sources and allocated GPU visibility.
4. Provision/start vLLM in the owned session, then run local/proxy/external checks.
5. Keep the job alive after success and local exit; add explicit recovery/status/release.
6. Validate a real authorized template deployment with a pinned model/runtime.

Do not edit dependency source or duplicate generic UCloud product/transport logic
here. Route generic improvements to the owning ucloud-api project.
