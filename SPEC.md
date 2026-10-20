# Isolated first-time bootstrap

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

## §G Goal
Host through reviewed application specifications without prior job IDs; prepare
new persistent storage and starter files in an isolated researcher workspace.
Existing template deployments and credentials remain intact.

## §C Constraints
- C1: Consume released ucloud-api v0.1.7: job builder/client, SSH/SCP, resource checks.
  Generic HTTP calls use only reviewed official routes below; no dependency edits.
- C2: Select an existing project-owned drive/folder. Create a fresh named namespace
  and its `vllm` child; no new drive allocation, replacement or folder deletion.
- C3: Bootstrap may allocate one explicitly selected CPU job for at most one hour.
  No GPU until a model deployment request. No dummy template jobs.
- C4: Work in onboarding-sandbox-20261020. No copied .env/private keys, no changes
  to the original checkouts or deployed folder. Credentials are supplied separately.
- C5: Live target: operator-selected "isolated validation project" project; resolve exact
  UUID and review concrete isolated workload/resources before allocation.
- C6: Retain existing template-ID behavior and persistent hosting lifetime rules.

## §I Interfaces
- I.request: ucloud.vllm.bootstrap_request.v1: project UUID, storage_parent,
  namespace, cpu_product, link_id, public_base_url, ssh_public_key (.pub path).
- I.cli: bootstrap-plan/apply/credentials/finish/status/release/reconcile; apply/credentials/finish/release
  preview until --yes. bootstrap-reconcile accepts only a known CPU job ID.
- I.mode: doctor/preview-profile/deploy --bootstrap FILE. Recovery, renewal and
  rollback use the deployment's stored bootstrap snapshot; no implicit fallback.
- I.state: bootstrap plan + deployment.json journal + upstream/API provenance;
  finalized bootstrap.json includes complete preparation/serving specifications.
- I.remote: immutable staging bundle and exclusive starter-file installation;
  credential presence/permissions/hash verification emits no credential values.

## §R Research
| id | Question | Finding | Source |
| --- | --- | --- | --- |
| R1 | Application discovery | GET /api/hpc/apps/byNameAndVersion; appName/appVersion | [AppStoreApi.ts](https://github.com/SDU-eScience/UCloud/blob/3d08e18c539d364c127b898a147e40151c9708d8/frontend-web/webclient/app/Applications/AppStoreApi.ts#L755) |
| R2 | Storage ownership/create | Files inherit drive owner/permissions; POST /api/files/folder uses bulk id/conflictPolicy; REJECT prevents replacement | [files.go](https://github.com/SDU-eScience/UCloud/blob/3d08e18c539d364c127b898a147e40151c9708d8/provider-integration/shared/pkg/orchestrators/files.go), [FilesApi.tsx](https://github.com/SDU-eScience/UCloud/blob/3d08e18c539d364c127b898a147e40151c9708d8/frontend-web/webclient/app/UCloud/FilesApi.tsx#L1132) |
| R3 | Complete jobs | JobSpecification includes application/product/replicas/parameters/resources; released builder accepts complete mappings | [jobs.go](https://github.com/SDU-eScience/UCloud/blob/3d08e18c539d364c127b898a147e40151c9708d8/provider-integration/shared/pkg/orchestrators/jobs.go#L130), [released builder](https://github.com/CBS-HPC/ucloud-api/blob/v0.1.7/src/ucloud_workflow/jobs.py#L122) |
| R4 | Baseline schemas | Read-only catalog review 2026-10-20 confirmed coder-python 1.89.1 SSH OPTIONAL; nginx 1.31.2 configFile/initScript input_file; both permit additional mounts | Packaged data/bootstrap_applications.json; no job parameters or credentials exported |
| R5 | Persistence/startup | Mounted volumes are under /work; nginx accepts a configuration and initialization script | [job guide](https://docs.cloud.sdu.dk/guide/submitting.html), [nginx](https://docs.cloud.sdu.dk/Apps/nginx.html) |

## §V Invariants
- V1: Explicit bootstrap input or journal source selects bootstrap; missing template
  IDs never select it implicitly. Recovery pins the stored source and digest.
- V2: Bootstrap submits only the reviewed CPU application/product for one hour;
  serving specification is inert until deploy selects the profile's GPU product.
- V3: New namespace creation uses REJECT and journals intent first. Unknown
  folder/job acknowledgements block retries; existence never proves creation ownership.
- V4: Verify /work/vllm persistence and staging ownership before uploads. Install
  only packaged assets; reject symlinks/conflicting files, preserve existing bytes.
- V5: No real .env upload or credential generation. A separate explicit credentials
  command may send only selected VLLM/HF keys through SSH stdin to exclusive 0600
  creation; never send UCloud credentials, overwrite or retry an unknown write.
  Finish requires owner-only remote .env and matching local serving-key hash.
- V6: Revalidate exact server/project, directory/collection, application schema,
  CPU/GPU product support and Link scope/domain/bindings before allocations.
- V7: Resume uses exact owned CPU job; reconciliation validates name/application/
  product/mounts. Release affects only its recorded CPU and preserves storage/Link/key.
- V8: Template mode and existing lifecycle tests stay green. Cross-source replacement
  is rejected; bootstrap replacement/renewal/rollback retain the same storage identity.
- V9: Reports/journals contain no secrets or raw authenticated responses. Plan/apply
  changes never touch original workspace credentials or deployment directories.
- V10: Synthetic live evidence records project/workload/hardware/expiry and actual
  endpoint results. An operator-led sandbox run is not colleague-led acceptance.
- V11: Validate reviewed payload version before any mutation, including resumed
  bootstraps requiring a replacement CPU job.

## Review gate and verification contract
GO for isolated implementation. HARDEN: read-only app lookup must replace prior-job
metadata (R1); folder acknowledgement loss cannot become ownership (R2/V3);
payload checks precede replacement allocation (V11); secret provisioning stays an
explicit stdin-only action (V5). Live allocation awaits the prepared target plan.

Named checks: test_bootstrap_plan_is_read_only_and_has_no_job_dependency (V1,V2,V6),
test_unknown_folder_or_job_blocks_duplicate_creation (V3,V7),
test_assets_preserve_conflicts_symlinks_and_secret_files (V4,V9),
test_secrets_use_stdin_exclusive_creation_and_unknown_write_guard (V5),
test_bootstrap_deployment_recovery_and_template_mode (V1,V8),
test_payload_change_blocks_all_mutations (V11). Run pytest, build, wheel smoke;
record live evidence separately (V10).

## §T Tasks
| id | status | Task | cites |
| --- | --- | --- | --- |
| T1 | x | Validate application/storage/product contracts; read-only bootstrap plan | V1,V2,V6,V9,I.request |
| T2 | x | Journal folder/CPU setup and exclusive remote uploads; finish/release/reconcile | V2,V3,V4,V5,V7,V9,I.remote,I.state |
| T3 | x | Add explicit bootstrap source to lifecycle, doctor, preview and CLI | V1,V6,V8,I.mode,I.cli |
| T4 | ~ | Update docs; isolated tests/build/CI and reviewable Git publication | V8,V9,I.cli |
| T5 | . | Run scoped isolated live trial; retain exact evidence and remaining colleague gate | V6,V7,V10,C5 |

## §B Regression record
| id | date | cause | fix |
| --- | --- | --- | --- |
| B1 | 2026-10-20 | --no-isolation requires a build backend absent from the fresh Python 3.13 venv | Use standard python -m build with its declared isolated backend; no runtime invariant change needed |
