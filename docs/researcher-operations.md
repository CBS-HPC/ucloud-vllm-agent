# Researcher operations and troubleshooting

Keep the exact deployment directory returned by deploy. Its deployment.json owns
job identity, stage, submission intent and expiry; run/current.json points to the
current bundle. Files and caches in UCloud persist independently of local agent
processes. Historical benchmark/catalog entries do not establish current uptime.

| Need | Command / interpretation |
| --- | --- |
| Current deployment state | `vllm-agent status --deployment deployments/NAME/RUN` |
| Startup failure or interrupted CLI | Inspect the saved state and use `recover --deployment ...`. Recovery may allocate a replacement CPU preparation job. |
| Unknown submission acknowledgement | Identify the exact existing job, then `recover --deployment ... --kind hosting --submission-job-id ID` (or preparation). Never submit a second copy. |
| Restart the owned process | `restart --deployment ...` reuses the allocation. |
| Stop serving but keep the machine | `stop --deployment ...`; GPU time remains allocated. |
| Finish using the allocation | `release --deployment ...`; stops exact recorded owned jobs, preserves caches/files and operator templates. |
| Need more time | `renew --deployment ... --hours N`; a replacement allocation, with downtime, not in-place extension or scheduling. |
| Change model/settings | Reviewed `deploy --profile ... --replace deployments/NAME/RUN`; explicit downtime and new allocation. |
| Restore predecessor after failed replacement | Explicit `rollback --deployment ...`; can allocate a new job and requires recorded predecessor evidence. |

Never run release merely to get a clean doctor result. Before release/replacement,
verify that the target is your intended deployment. Do not stop by process name,
port, latest-job selection or broad project filters. An expired allocation cannot
be made durable by a successful endpoint test. Renewal remains the operator's
responsibility; no automatic cron renewal is provided.

## Common setup failures

| Symptom | Next action |
| --- | --- |
| Git/pip cannot access a dependency | Verify CLI GitHub authorization for the private repositories; never paste a token into a URL. |
| doctor reports missing requirements | Follow each remedy; local settings belong in the provider workspace, not the wrapper. Use absolute SSH key paths. |
| Online preflight fails | Check both job IDs/project ownership, token coverage, application versions, shared mount and reserved URL. Inspect-template/preview-profile are read-only. |
| Public URL occupied | Find the existing deployment and its operator. Explicitly replace only an owned record; do not delete/recreate the link. |
| CPU preparation fails | Inspect the recorded preparation result and private remote logs locally; verify Python 3.12, mount persistence, .env permissions and matching serving key. |
| GPU is RUNNING but endpoint fails | Inspect init/runtime evidence and WEB route; RUNNING is not model readiness. Preserve the allocation for diagnosis or explicitly release it. |
| Different project appears selected | Check inherited UCLOUD_* variables: they override .env. Use a clean subprocess environment for that workspace. |
| Model fits estimate but is slow/fails startup | Recheck supported architecture/runtime, actual per-device VRAM, context/concurrency and workload evidence; memory fit is not throughput validation. |

CPU preparation and GPU serving consume project resources. A stopped process or
failed verification can leave an allocated job consuming the project's allowance.
No monetary price is inferred by the estimator. Confirm accounting units, duration
and cleanup responsibility with the project owner before deployment. Inspect
logs yourself without exposing prompts, credentials or private responses to the
agent; report sanitized error context.

For support, provide package versions, OS, command name, sanitized doctor output,
state/error code and an approved redacted description of the failure. Do not send
.env, private SSH keys, full deployment bundles, raw authenticated responses or
notebook outputs containing research data. Generic API/resource issues belong to
ucloud-api; hosting/task/runtime issues belong to this provider; provider selection
and harness delegation belong to CBS Model Agent.
