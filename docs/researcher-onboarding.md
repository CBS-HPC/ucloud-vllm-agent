# Researcher onboarding: UCloud vLLM

This guide is for a researcher hosting a model in their own UCloud project.
If you only need to call an existing model endpoint, ask its operator for the
base URL, served model name, credential delivery method and permitted use. You
do not need deployment credentials, SSH or template jobs merely to use that API.

For hosting, use Windows or Linux with Python 3.11+, Git and OpenSSH (`ssh` and
`scp`) on PATH. Python 3.11/3.13 are tested locally/in CI; this is distinct from
the required remote Python 3.12 environment. Obtain GitHub read access to the
private CBS-HPC/model-agent and CBS-HPC/ucloud-vllm-agent repositories. Your Git
credential manager must also permit pip's Git dependency downloads; logging into
the GitHub website alone does not establish command-line access. Never embed a
GitHub token in a clone URL or command.

## Install the agent and its provider workspace

Clone both repositories into a new parent directory. The wrapper installs the
released provider code; its separate source checkout supplies profiles, notebooks,
agent instructions and a persistent workspace for your project records.

```sh
git clone --branch v0.1.1 https://github.com/CBS-HPC/model-agent.git model-agent
git clone --branch v0.1.3 https://github.com/CBS-HPC/ucloud-vllm-agent.git ucloud-vllm-agent
```

On Windows PowerShell, from the parent directory:

```powershell
$AgentVenv = Join-Path $env:LOCALAPPDATA 'cbs-model-agent\venv'
python -m venv $AgentVenv
& "$AgentVenv\Scripts\python.exe" -m pip install -e './model-agent[ucloud-vllm]'
& "$AgentVenv\Scripts\Activate.ps1"
```

On Linux, from the same parent directory:

```sh
python3 -m venv "$HOME/.local/share/cbs-model-agent/venv"
. "$HOME/.local/share/cbs-model-agent/venv/bin/activate"
python -m pip install -e './model-agent[ucloud-vllm]'
```

Use an environment outside OneDrive/synchronised storage. For multiple independent
installations, choose separate environment paths. If PowerShell activation is
restricted, invoke the environment's python.exe directly; do not weaken machine-wide
execution policy. Direct provider-only use is also supported: clone the provider,
create a venv and run `python -m pip install -e '.[ucloud]'` inside that checkout.
Keep the two released versions aligned; the wrapper does not execute Python source
from the selected workspace unless that source is separately installed editable.

Verify installation without credentials or network calls:

```sh
cbs-model --version
vllm-agent --version
cbs-model providers
```

## Set up your project

| Requirement | Who supplies it / where it belongs |
| --- | --- |
| UCloud project and CPU/GPU allocation | Researcher/project administrator; check permissions and accounting limits. |
| UCloud API token and matching token ID | Researcher's local provider `.env`; never upload it. |
| SSH identity | Private key stays on your computer; register its public key on UCloud. Set an absolute UCLOUD_SSH_IDENTITY_FILE path if needed. |
| Shared persistent folder, CPU and nginx job IDs, reserved URL | Follow [workspace/job setup](ucloud-workspace-template.md). Both jobs must belong to your project. |
| HF_TOKEN | Optional for public models; use authorized access for gated models. Local metadata and remote downloads may each need it. |
| VLLM_API_KEY | Strong serving credential, matching locally and in the remote `/work/vllm/.env`. It is separate from the UCloud API token. |
| Runtime and hardware | nginx 1.31.2, compatible Python 3.12 images, vLLM 0.31.0; current automatic machine mapping is B200 only. |

In the provider checkout, copy `.env.example` to `.env` only if it does not exist,
then edit it locally. Environment variables already set in the invoking process
take precedence over `.env`. Do not export one project's credentials globally
when working in another workspace. The wrapper does not need UCloud credentials
in its own `.env`.

```sh
cd ucloud-vllm-agent
vllm-agent workspace-template --output artifacts/ucloud-workspace
vllm-agent doctor
```

Follow the workspace setup guide before continuing. `doctor` exits 1 when required
settings/tools/identity are missing and reports remedies without printing values.
Exit 0 means local requirements passed, not authenticated or remote readiness.
Link/key provisioning and bootstrap without prior job IDs are still planned;
the current deployment mode requires both explicit template IDs.

## First model: preview before allocating

Copy `config/hosting.qwen-small.json` to ignored `config/local.qwen.json`. Review
the pinned model/license, context, concurrency, hours and machine for your project.
The existing B200 profile is historical capacity evidence, not a universal minimum
or a guarantee of availability. A product/profile marked verified for the original
project still needs verification for yours.

```sh
vllm-agent models --status validated
vllm-agent doctor --online --profile config/local.qwen.json
vllm-agent size --profile config/local.qwen.json
vllm-agent prepare-profile --profile config/local.qwen.json
vllm-agent preview-profile --profile config/local.qwen.json
```

Online doctor performs read-only API checks: project ownership, supported template
applications, shared mount references, public-link mapping/bindings and token
coverage for the profile's allocation. It does not start a job, use SSH, inspect
remote credentials or prove the model can run. A link already serving a model
blocks this first-deployment check; do not release it just to pass preflight.
Inspect its recorded deployment and explicitly choose replacement when intended.

Only when the user requests deployment and the profile is reviewed:

```sh
vllm-agent deploy --profile config/local.qwen.json --reviewed
```

Use `--auto-size` only when you intend automatic selection from the current
supported project machine catalog. Save the returned deployment path; follow
[operations and troubleshooting](researcher-operations.md). To operate through the
wrapper, prefix commands with `cbs-model ucloud-vllm --workspace PATH`, as shown
in the [harness integration contract](harness-integration.md).

Acceptance: authentication and actual task checks pass on the intended public
HTTPS endpoint, and you know the allocation expiry, responsible operator and exact
deployment record. A colleague's first-project live validation remains pending;
test suites and this guide do not establish current uptime or platform approval.
