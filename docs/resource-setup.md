# First-time Link and optional public-key setup

This workflow consumes released [ucloud-api v0.1.7](https://github.com/CBS-HPC/ucloud-api/releases/tag/v0.1.7).
It reserves/reuses a Public Link and can register a selected SSH **public** key.
It does not start CPU/GPU jobs, attach a Link, create shared folders, upload files,
configure nginx, create secrets or modify `.env`. Those remain separate steps in
[workspace setup](ucloud-workspace-template.md) or explicit [bootstrap](bootstrap.md).
Template mode requires both existing IDs; bootstrap uses its finalized source
artifact. Reserving a Link is not a working public endpoint.

## Plan

Install this provider's `[ucloud]` extra. Set `UCLOUD_TOKEN` and the exact project
UUID in the local project `.env` or inherited environment. Setup does not need
template IDs or a VLLM_API_KEY. Keep the normal deployment prerequisites for later.

Discover the actual provider product and hostname pattern with the released CLI:

```powershell
ucloud links products --json
```

Copy `config/resource-setup.example.json` to ignored `config/local.setup.json`.
Replace the project UUID, hostname and complete product reference with your own
values. `existing_id: null` means reuse the uniquely matching visible hostname,
or plan creation if none exists. Set an exact ID to select an existing Link.
Foreign-project resources, conflicting products, unknown bindings, bound Links
and non-READY existing Links block setup. Never take over another route.

`ssh_public_key: null` leaves account keys alone. For explicit registration or
matching-fingerprint reuse, replace it with:

```json
{
  "path": "C:/Users/YOUR_USER/.ssh/id_ed25519.pub",
  "title": "UCloud model hosting",
  "register_if_missing": true
}
```

Only a selected `.pub` file is read; it is validated with `ssh-keygen`. The plan
stores its absolute path and fingerprint, never the key contents. The private
key remains local. `register_if_missing: false` requires a matching registration
already to exist. Registration is account-scoped, independent of the project;
matching registration does not prove private-key possession or working job SSH.

```powershell
vllm-agent setup-plan --request config/local.setup.json --output artifacts/setup-plan.json
vllm-agent setup-apply --plan artifacts/setup-plan.json --state run/setup/first
```

The first command uses read-only discovery and writes a new plan file (existing
files are refused). The second previews without allocating anything. Review the
exact project/server, hostname/product, key fingerprint and create/reuse actions.
Public Links persist and can consume allocation. Registering a key grants that
key account access according to UCloud's rules; it is not project-isolated.

## Apply and recovery

```powershell
vllm-agent setup-apply --plan artifacts/setup-plan.json --state run/setup/first --yes
vllm-agent setup-status --state run/setup/first
```

Apply rechecks the plan before starting. It journals intent before each mutation,
records exact IDs and `created`/`reused` ownership, and waits up to 180 seconds for
Link readiness. Repeating apply resumes confirmed resources instead of creating
them again. A local failure or readiness timeout does not delete anything.
Keep the plan, `setup.json`, upstream `operations/` receipts and workspace
`run/resource-setup-current.json` together, outside Git. Back up these non-secret
ownership records: a lost record is not permission to infer ownership later.

The report suggests a public API URL but writes no settings. Save that URL in the
local provider settings and use the returned Link ID in your bootstrap request.
Continue with [bootstrap](bootstrap.md), or the manual shared-folder/credential/
template steps if using existing job IDs, then run source-specific doctor/preview.
`resources_ready` does not mean deployment-ready, bound, authenticated or publicly
verified. `setup-status` reports the saved journal, not fresh resource readiness.

After an interrupted or uncertain create:

```powershell
vllm-agent setup-reconcile --state run/setup/first
```

Reconciliation is read-only remotely. A confirmed upstream receipt with a returned
ID can repair a lost local acknowledgement after rechecking target identity.
A receipt showing rejection marks the action rejected; review a new plan/state
before trying again. Pending/unknown receipts, missing receipts, ambiguous receipts
and uncertain deletes stay blocked. A matching domain or fingerprint alone never
proves this operation created a resource. Do not change directories, erase state
or use another workspace to bypass uncertainty. Inspect the exact upstream
operation with the administrator/operator; retain the evidence. The CLI does not
offer an unsafe force-retry or a self-certified "nothing happened" switch.

An unresolved setup also blocks another setup in the same workspace. This local
lock/journal is not a distributed lock across researchers or computers; use one
operator/workspace per setup and resolve conflicts through UCloud.

## Exact, explicit cleanup

```powershell
vllm-agent setup-cleanup --state run/setup/first --kind link
vllm-agent setup-cleanup --state run/setup/first --kind link --yes
```

Cleanup previews by default and requires a confirmed creation receipt, matching
project/server/domain/product, known empty bindings and the exact recorded ID.
It protects reused resources. Stop/release an owned job separately before removing
its Link. Job release never deletes a Link or SSH key implicitly. An uncertain
deletion blocks retries; a timeout is not evidence that the resource survived.

To remove a key **created by this setup**, explicitly select `--kind ssh_key`
and review its preview before adding `--yes`. Keys are shared at account scope:
ensure it is no longer needed by other projects or jobs. Cleanup verifies the
registered ID/fingerprint; it cannot prove the key is unused elsewhere or that
revocation takes effect on already-running jobs. Normally retain reusable keys.

## Integration review and remaining limits

Reviewed release source: `v0.1.7`, commit
`4bc8af51d153963ba6273d8de78337541d6c3070` (annotated tag object
`7ad93440d51eb8d8f1541edaa377f34c0c62f3f6`). The integration uses
`resources.prepare_resource/list_resources/scoped_resource/create_resource/`
`wait_for_resource/delete_resource` and the public-key helpers in `ssh_keys`.
Generic payloads, pagination, provider patterns, POST outcome receipts and key
validation remain upstream. This provider adds the hosting setup plan, local
ownership/recovery contract and conservative project/binding guards.

Do not use upstream `run_with_job_resources` for a persistent inference server:
that short-lived-run helper always terminates its job on callback completion.
The existing hosting lifecycle retains its separate journal and SSH-off nginx
submission. No IP, license, firewall, runtime attach/detach or automatic machine
fallback is added here. Upstream's HTTP 449 observation does not validate our
public inference route. The [2026-10-20 Qwen trial](bootstrap-live-validation.md)
validated Link setup, existing-key reuse, actual-image nginx syntax and public
chat/auth/SSE. New-workspace PII, live key registration/removal and injected
uncertain resource outcomes remain separate scoped validation tasks.

Bootstrap without prior jobs remains separate and is implemented in provider
v0.1.5. It combines reviewed CPU/nginx application schemas with complete mappings
through the released low-level builder; reviewed read-only application/Files
routes use the released generic client. The application-aware resource helpers
still obtain metadata through prior jobs and are not used to manufacture a
bootstrap template. See [bootstrap](bootstrap.md) and SPEC.md for provenance.
Never allocate a dummy GPU or treat `job-templates.json` recipes as submit payloads.

### Regression record (§B)

2026-10-20: the private-key non-reading test initially intercepted every
`Path.read_text`, including installed-package version metadata. Scope the guard
to the selected private-key path. The existing no-private-key-read contract is
unchanged; this was test instrumentation, not a credential access failure.
