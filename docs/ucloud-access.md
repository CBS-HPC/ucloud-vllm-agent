# Upstream integration boundary

Reference: the operator's moody_agent uses released ucloud-workflow, explicit
UCLOUD_TEMPLATE_JOB_ID, persistent environments and isolated case artifacts.
Here the workload is an ongoing HTTP model service; it must not inherit the batch
runner's automatic job termination after outputs are collected.

The optional dependency is currently pinned to v0.1.5 for read-only template
inspection. That release's build_job_specification and submit helper generate a
CPU product. GPU/product selection is being implemented in the owning ucloud-api
project and will arrive in a release. Do not copy an interim submit client here.

vllm-agent deploy is a release gate, not a partially working submit command. It
always exits before network calls. This keeps preparation/test work useful while
avoiding accidental CPU allocations. The CLI's inspect-template uses the existing
client and returns only selected non-secret metadata and resource types.

## After the upstream release
1. Inspect released documentation/source and the exact product-selection API.
2. Update the pyproject optional dependency pin to that release.
3. Add the thin adapter using the released API and require explicit template ID.
4. Verify template application, parameters, mounts and URL resources are preserved
   when selecting a GPU/MIG product. Detect public links already attached to another
   active job; preserve the requested topology rather than silently replacing it.
5. Persist submitted job ID immediately; block duplicate submissions on unknown
   outcomes. Use upstream SSH helpers with explicit configuration and host checks.
6. Keep the job alive on successful setup and local agent exit. Add explicit
   status/recovery/stop/release operations with owned deployment identifiers.
7. Test with a real authorized GPU template and record the endpoint results.

Host-key behavior is part of release review: the older update_ssh_config helper
disables verification. Do not adopt it blindly. Do not change dependency source
here; route generic transport improvements to its owner.
