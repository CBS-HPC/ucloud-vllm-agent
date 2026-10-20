# First-time setup without prior job IDs

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

This path is for a new project with an existing writable UCloud drive, CPU/GPU
allocation, a reserved Public Link and a registered SSH public key. It builds
complete job specifications from reviewed application definitions. It does not
create a dummy GPU job to manufacture a template ID. The existing
[template-ID path](ucloud-workspace-template.md) remains supported and separate.

Use a new provider checkout/workspace for a different project. Install this
checkout with `python -m pip install -e '.[ucloud]'` in its own external venv.
The currently published wrapper still pins provider v0.1.4, which has no bootstrap
commands; this branch must be installed editable for the isolated trial. A wrapper
release will consume the new provider only after its reviewed release is published.

## Intake and read-only plan

Set UCLOUD_SERVER, UCLOUD_PROJECT (exact project UUID), UCLOUD_TOKEN,
UCLOUD_TOKEN_ID, UCLOUD_PUBLIC_BASE_URL, UCLOUD_SSH_IDENTITY_FILE and VLLM_API_KEY
in this workspace's local `.env`. Set HF_TOKEN only if needed. Leave both template
IDs blank for bootstrap. Keep the private key in its existing local location;
select the corresponding `.pub` path in the request. Never paste tokens in chat.

Use [Link and optional public-key setup](resource-setup.md) first if these resources
do not already exist. That workflow creates no jobs. Choose the exact CPU product
from the project's advertised products/allocation, not from a guessed machine name.

Copy `config/bootstrap.example.json` to ignored `config/local.bootstrap.json` and
replace every placeholder. `storage_parent` is a UCloud Files path, e.g.
`/DRIVE_ID`, not a container `/work` path. The parent must already exist and be
writable, project-owned and on the same provider as compute and the Link.
Choose a fresh namespace. Bootstrap creates `PARENT/NAMESPACE/vllm`; mounting this
leaf folder gives the jobs `/work/vllm` without touching any existing vllm folder.

```sh
vllm-agent bootstrap-plan --request config/local.bootstrap.json --output artifacts/bootstrap-plan.json
vllm-agent bootstrap-apply --plan artifacts/bootstrap-plan.json --state run/bootstrap/first
```

The plan retrieves exact application versions/parameters, directory ownership,
permissions, public-link status, product support and SSH registration. No job is
submitted. Review its project, hostname, Files path, CPU product and one-hour limit.
Application contracts are pinned in `data/bootstrap_applications.json` with the
reviewed official API revision. A changed schema fails closed. Generic reviewed
HTTP routes run through released ucloud-api v0.1.7; the dependency is not modified.

## Apply, credentials and finish

Only when those folder changes and CPU allocation are requested:

```sh
vllm-agent bootstrap-apply --plan artifacts/bootstrap-plan.json --state run/bootstrap/first --yes
vllm-agent bootstrap-status --state run/bootstrap/first
```

Apply uses REJECT for new folders, persists intent before each mutation and submits
one coder-python 1.89.1 CPU job for at most one hour. It verifies that `/work/vllm`
is a persistent mount, creates an owned private staging directory, and uploads the
packaged nginx.conf, init_vllm.sh, README.md and `.env.example` plus source helpers.
All existing targets are checked before asset installation; differing files and
symlinks are preserved and block installation. No real `.env` is uploaded.
The CPU job stays allocated until finish/release or expiry. No GPU is started.

Provision the remote `/work/vllm/.env` through an editor in this owned setup job
and set mode 0600, or use this separate explicit action:

```sh
vllm-agent bootstrap-credentials --state run/bootstrap/first
vllm-agent bootstrap-credentials --state run/bootstrap/first --yes
# For a gated model, explicitly select the locally configured HF_TOKEN too:
# vllm-agent bootstrap-credentials --state run/bootstrap/first --include-hf-token --yes
vllm-agent bootstrap-finish --state run/bootstrap/first
vllm-agent bootstrap-finish --state run/bootstrap/first --yes
```

The credential command sends only selected VLLM/HF values through encrypted SSH
stdin. It creates the fixed remote file exclusively with mode 0600; it neither
overwrites nor creates a duplicate credential file. UCloud tokens remain local.
An existing `.env` requires verification, never replacement. Credentials must be
single-line values without quotes. HF_TOKEN is optional for public Qwen.

Finish verifies remote ownership/permissions and the serving key against a hash of
the local key, releases only this recorded bootstrap CPU job, and writes
`run/bootstrap/first/bootstrap.json`. This finalized artifact is an inert source
specification, not runtime readiness. No `.env` settings or template IDs are written.

## Deploy the actual model

Review a project-specific profile with your new URL, exact GPU/MIG product,
context, concurrency and hours. For the supported small Qwen baseline:

```sh
vllm-agent doctor --bootstrap run/bootstrap/first/bootstrap.json
vllm-agent doctor --online --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json
vllm-agent preview-profile --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json
vllm-agent deploy --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json --reviewed
```

Deployment revalidates scope, schemas, storage, Link and product support, then uses
the ordinary model-preparation CPU job followed by the profile's actual GPU job.
Budget for bootstrap CPU up to one hour, preparation CPU up to one hour, and the
requested GPU duration. Queue waits and package/model downloads affect startup.
The nginx initScript starts the model; there is no GPU template allocation.
Persist the returned deployment path and expiry. Successful hosting remains alive.
`recover`, replacement, `renew` and `rollback` use the saved bootstrap snapshot;
changing its source/storage or switching from template mode is rejected. Renewal
and rollback still involve downtime. Release is explicit and preserves files/caches.

## Recovery and limits

Repeat apply only with the same journal/plan/provider payload. A known running CPU
is reused. After its confirmed expiry, explicit apply can create one replacement
CPU and reuse identical assets. Changed helper/asset bytes block all mutations.
Unknown job submission outcomes require identifying the exact matching CPU job:

```sh
vllm-agent bootstrap-reconcile --state run/bootstrap/first --job-id EXACT_CPU_JOB_ID
vllm-agent bootstrap-release --state run/bootstrap/first
vllm-agent bootstrap-release --state run/bootstrap/first --yes
```

Reconciliation checks name, project, application, product, mounts and allocation.
A lost folder acknowledgement cannot be reconciled from existence alone: preserve
the journal and obtain provider/audit confirmation; this version has no automatic
folder adoption or deletion. Never use new state to bypass an unresolved pointer.
An unknown credential write blocks resubmission; finish can verify the existing
file instead. If the CPU expired, apply may restore CPU access first. Release stops
only the owned CPU; it preserves all folders, Links and keys. A released unfinished
bootstrap cannot be resumed. Storage and separately created resources need explicit
operator management, following their ownership records.

Offline contract tests are not live platform validation. The isolated operator-led
trial in "isolated validation project" is pending; colleague-led onboarding and actual
generic-nginx/public auth/chat/SSE checks remain separate acceptance evidence.
