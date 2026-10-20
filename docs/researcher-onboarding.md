# Researcher onboarding: UCloud vLLM

Follow this guide to host a model in your own UCloud project. It targets the
published pair **CBS Model Agent v0.1.4 / UCloud vLLM agent v0.1.6**, consuming
ucloud-api v0.1.7. Documentation reviewed against that pair on 2026-10-20.
This maintained guide includes clarifications after the immutable release tags;
use the [online guide](https://github.com/CBS-HPC/ucloud-vllm-agent/blob/main/docs/researcher-onboarding.md)
alongside the pinned checkout, whose local docs reflect release-day content.

If you only want to call an existing endpoint, obtain its base URL, served model
name, serving key and permitted use from its operator. Deployment credentials,
SSH and UCloud job setup are not required for API-only use.

## 1. Check access and choose a setup path

You need Windows or Linux, Python 3.11+, Git and OpenSSH (`ssh`, `scp` and
`ssh-keygen`) on PATH. CI covers Windows/Linux with Python 3.11 and 3.13;
remote jobs use the separate Python 3.12 runtime baseline.

The CBS-HPC/model-agent, CBS-HPC/ucloud-vllm-agent, CBS-HPC/lumi-aitta-api and
CBS-HPC/ucloud-api repositories are public. Git and network access to GitHub must
work for pip's dependency downloads; no GitHub token is required for installation.
UCloud access still requires your own project allocation and API credentials.
The UCloud-only install does not need a LUMI account; using AITTA requires an
active LUMI project and its own AITTA token.

| Your situation | Path | Deployment source |
| --- | --- | --- |
| New project; no suitable previous jobs | [Bootstrap](bootstrap.md): choose an existing writable drive, reserve a Link, then prepare fresh folders/files through a bounded CPU job. | Finalized `run/bootstrap/first/bootstrap.json`; leave both template IDs blank. |
| Existing compatible CPU/nginx jobs, shared folder and URL | [Template-ID setup](ucloud-workspace-template.md): verify and reuse those exact resources. | Both explicit template job IDs. |

Bootstrap creates folders on an existing drive; it does not provision a new
drive. Both paths need project CPU/GPU allocation and supported products. Current
automatic hardware mapping covers B200 full GPUs and B200 1g.23gb MIG. The tested
images are coder-python 1.89.1 and nginx 1.31.2 with vLLM 0.31.0. Other hardware
or image/runtime versions require compatibility review.

## 2. Install into a new local workspace

Clone both repositories into a new parent directory, separate from any existing
operator workspace. Each UCloud project should have its own provider checkout
and journals. The wrapper installs released provider code; the provider checkout
supplies profiles, notebooks, agent instructions and local operational records.

```sh
git clone --branch v0.1.4 https://github.com/CBS-HPC/model-agent.git model-agent
git clone --branch v0.1.6 https://github.com/CBS-HPC/ucloud-vllm-agent.git ucloud-vllm-agent
```

Cloning a release tag leaves Git in detached HEAD state; this is expected for a
released workspace. Your local profiles and runtime records remain ignored by Git.

From that parent directory on Windows PowerShell:

```powershell
$AgentVenv = Join-Path $env:LOCALAPPDATA 'cbs-model-agent\venv'
python -m venv $AgentVenv
& "$AgentVenv\Scripts\python.exe" -m pip install './model-agent[ucloud-vllm]'
& "$AgentVenv\Scripts\Activate.ps1"
```

On Linux, from the same parent directory:

```sh
python3 -m venv "$HOME/.local/share/cbs-model-agent/venv"
. "$HOME/.local/share/cbs-model-agent/venv/bin/activate"
python -m pip install './model-agent[ucloud-vllm]'
```

Choose a different venv path if this one belongs to another installation. Keep
the environment outside OneDrive/synchronised storage. If activation is
restricted, invoke the venv's Python with `-m cbs_model_agent` or
`-m ucloud_vllm_agent`; changing machine-wide execution policy is unnecessary.
Editable installation (`-e`) is for development, not required for operation.
The workspace's Python source is not executed merely because it was selected
with `--workspace`. Keep its release aligned with the installed provider.

Provider-only use is supported: clone the provider tag, create a venv, then run
`python -m pip install '.[ucloud]'` inside that checkout.

Check installation without credentials or network requests:

```sh
cbs-model --version
vllm-agent --version
cbs-model providers
```

Expected versions are 0.1.4 and 0.1.6. `providers` lists capabilities offline;
an entry marked implemented does not prove its optional dependency is installed.

## 3. Configure local access

Change into `ucloud-vllm-agent`. Copy its root `.env.example` to `.env` only if
the destination does not already exist, then edit it locally. Do not read it into
an agent conversation or copy it to the wrapper or UCloud.

| Local setting | Requirement |
| --- | --- |
| `UCLOUD_TOKEN` | Researcher's UCloud API credential for the intended project/resources. |
| `UCLOUD_PROJECT` | Exact project UUID, supplied by the project administrator or verified project metadata; the project title/accounting ID is not accepted. |
| `UCLOUD_TOKEN_ID` | Non-secret metadata ID of the token actually supplied, used to check expiry. This is required for deployment. |
| `VLLM_API_KEY` | Strong serving key used by clients and the remote model; distinct from the UCloud token. |
| `UCLOUD_PUBLIC_BASE_URL` | Your reserved public hostname or HTTPS URL ending in `/v1`; fill after Link selection. |
| Both template job IDs | Required only in template-ID mode; leave blank for bootstrap. |
| `HF_TOKEN` | Optional for public Qwen; needed for gated metadata/downloads when permitted. Select it explicitly during bootstrap credential provisioning if required remotely. |
| `UCLOUD_SSH_IDENTITY_FILE` | Optional absolute path to an existing local private key when default discovery does not select the correct identity. Its public key must be registered. |
| Other example settings | Keep the supplied server/mount/nginx/SSH defaults for the supported baseline. Change only with a reviewed reason. |

Three filled values (`UCLOUD_TOKEN`, `UCLOUD_PROJECT`, `VLLM_API_KEY`) are enough
to begin parts of setup, but not the complete deployment preflight. The token ID,
reserved URL and selected source must also be established. Run
`ucloud tokens status` for non-secret token metadata and match the ID to your
token's title/expiry; if multiple tokens are plausible, ask the token owner.
Never guess the match or create a new token merely to obtain an ID.

The defaults include `UCLOUD_SERVER=https://cloud.sdu.dk`,
`UCLOUD_SSH_ALIAS=ucloud` and `UCLOUD_WORK_FOLDER=/work/vllm`. An alias alone
does not establish SSH access. Keep the private key on your computer and select
its matching `.pub` file for optional registration/bootstrap.
If no identity exists, generate one locally with interactive `ssh-keygen`, choosing
a new filename that preserves existing keys. Passphrase-protected keys must already
be available through your local SSH agent: the deployment transport uses batch
mode and cannot prompt for the passphrase. For concurrent project workspaces,
choose distinct SSH aliases/configs so their connection updates do not collide.

Explicit process environment variables override `.env` in the CLI. Avoid global
credentials from another project. The wrapper does not need UCloud settings in
its own `.env`. Local UCloud credentials remain local; remote
`/work/vllm/.env` contains only the serving key and optional HF token. These two
files serve different processes; bootstrap transfers only selected remote values
over SSH stdin, never the local file or UCloud token.

## 4. Prepare resources and one explicit deployment source

For **bootstrap**, follow [bootstrap.md](bootstrap.md) in order:

1. Select an existing writable project-owned UCloud drive, exact CPU product,
   matching public key and your own Public Link. Use
   [resource setup](resource-setup.md) if Link/key setup is needed.
2. Copy/edit `config/bootstrap.example.json` as `config/local.bootstrap.json`.
   Choose a fresh namespace; Files paths such as `/DRIVE_ID` differ from job
   paths such as `/work/vllm`.
3. Run `bootstrap-plan`, inspect the plan and preview `bootstrap-apply`.
4. Once those folder changes and CPU use are requested, apply with `--yes`.
   Explicitly provision/verify remote credentials, then finish with `--yes`.
5. Retain `run/bootstrap/first/bootstrap.json` and the ownership journals.
   Finish releases the owned bootstrap CPU. It does not deploy a model.

For **template mode**, complete [the template guide](ucloud-workspace-template.md)
and set both job IDs. Use the same persistent folder and correct URL in both
templates; preserve existing nginx and credentials.

Resource reservation, bootstrap and model deployment are separate stages. Setup
commands reserve/reuse a Link and optionally register a public key without jobs.
Bootstrap can allocate one CPU job for up to an hour; actual deployment can use
another preparation CPU for up to an hour plus the profile's GPU duration. Check
accounting limits and storage capacity with the project owner. Queueing, package
installation and model downloads make first-run duration variable.

`doctor` without `--bootstrap` selects template mode and reports missing IDs.
That is expected before bootstrap is finalized: do not invent IDs or allocate a
dummy GPU to satisfy it. Local template export is optional for bootstrap because
bootstrap uploads the packaged assets itself.

## 5. Review a small model and preview

Copy `config/hosting.qwen-small.json` to ignored `config/local.qwen.json`. Review
the pinned model/license, name, 4096-token total context, concurrency 1, one-hour
duration and exact product/capacities against your project. `machine.verified`
in the example records previous evidence; it does not verify your allocation.
The URL comes from local settings unless explicitly overridden in a profile.

From the provider checkout, for **bootstrap mode**:

```sh
vllm-agent models --status validated
vllm-agent size --profile config/local.qwen.json
vllm-agent prepare-profile --profile config/local.qwen.json
vllm-agent doctor --bootstrap run/bootstrap/first/bootstrap.json
vllm-agent doctor --online --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json
vllm-agent preview-profile --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json
```

For **template mode**, use the same commands but omit `--bootstrap FILE` from
doctor/preview. Metadata inspection and API preflight are read-only; prepare
writes a local bundle. None of these commands allocate jobs.

Doctor reports missing requirements with remedies. Local exit 0 means configured;
online success adds checked project/source/Link/application/token prerequisites.
Neither proves available capacity, working SSH, remote credentials, nginx syntax
or model readiness. A bound Link blocks first-deployment checks: inspect its
operator/deployment rather than releasing it to make preflight pass.

## 6. Deploy, verify and hand over

Only after the user requests this reviewed workload, for bootstrap mode:

```sh
vllm-agent deploy --profile config/local.qwen.json --bootstrap run/bootstrap/first/bootstrap.json --reviewed
```

For template mode, omit `--bootstrap FILE`. Use `--auto-size` only when automatic
selection from the supported live project catalog is intended. Save the exact
deployment path returned by deploy; an earlier prepare-profile bundle is not
the deployment journal. If a command fails/times out, inspect its saved journal
and [recover it](researcher-operations.md); do not blindly repeat deploy.

Deploy prepares the environment/model cache on CPU, releases that preparation
job, starts nginx/vLLM on the GPU, registers the route and runs task/auth checks
on loopback, nginx and public HTTPS. Success leaves hosting running until explicit
release or allocation expiry. Record the base URL, served name, job ID, expiry,
responsible operator and credential delivery method.

For an interactive test, use `notebooks/test_model.ipynb` in an existing Jupyter
installation with a Python 3.11+ kernel. Set its `PROFILE_FILE` to your
`config/local.qwen.json` and use your local `.env` endpoint/key. The first cell
installs the client dependencies, not Jupyter itself. PII uses its separate
[email notebook and task guide](pii-tracer.md); do not run chat checks against it.
Notebooks show generated text and should be saved with outputs cleared.

When the intended trial is finished and release is requested:

```sh
vllm-agent status --deployment deployments/NAME/RUN
vllm-agent release --deployment deployments/NAME/RUN
```

Replace NAME/RUN with the returned path. Release ends recorded owned jobs; files,
caches, Links and account keys remain. Stop only stops the model and keeps the
allocation. Renewal/replacement incur downtime and new allocations. Read
[operations](researcher-operations.md) before routine use.

## 7. Connect your coding harness and record acceptance

Have the harness read the wrapper/provider AGENTS.md and WORKFLOW_CONTRACT.md.
Use the [copyable instructions and subprocess contract](harness-integration.md)
for harnesses that do not load those instructions automatically. No native MCP
server or hosted agent daemon is supplied by this project.

For example, from any directory with the venv active:

```sh
cbs-model ucloud-vllm --workspace /absolute/path/ucloud-vllm-agent models
cbs-model ucloud-vllm --workspace /absolute/path/ucloud-vllm-agent status --deployment deployments/NAME/RUN
```

All provider-relative paths resolve in that explicit workspace. The wrapper
delegates commands and preserves the provider's output/exit codes and journals.

Acceptance requires a colleague to follow this guide in their own workspace and
project, pass the intended public task/auth checks, locate the expiry/journal,
and release the exact trial allocation. Record undocumented prerequisites and
support interventions in the wrapper's [onboarding plan](https://github.com/CBS-HPC/model-agent/blob/main/docs/onboarding-plan.md).
The operator-led [Qwen bootstrap trial](bootstrap-live-validation.md) and fresh
release installation passed; independent colleague-led acceptance remains open.
