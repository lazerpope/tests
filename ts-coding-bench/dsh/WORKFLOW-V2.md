# DSH v2: offline coding with public-feedback repairs

This replaces the v1 shell/submit workflow for new `dsh_bench.py run` invocations. Existing runs and private grading tasks are preserved. **Use a new run name.** The code has been inspected and syntax-checked; no models, graders, or benchmark tests were executed while implementing this revision.

## Recommended command

From `ts-coding-bench`, with Ollama and Docker Desktop's Linux engine running:

```powershell
python -u dsh_bench.py run --suite typescript --pull --tool-protocol text --context 8192 --tokens 2048 --thinking off --max-submissions 3 --max-steps 6 --seconds 300 --run dsh-repair-v2
```

This runs all enabled entries in `models.json`, including models without native tool support. It permits one initial implementation plus **two different repaired implementations**. Six provider requests allow some format corrections; the limit is not six source submissions.

The 300-second limit applies to each model/task session. Cleanup and private grading follow it, so total command duration can exceed that limit. Full-suite duration depends on how many models you enable.

Why these settings: the overnight run spent most of its effort on shell/tool protocol problems and long reasoning. A common text protocol, direct source submission, thinking off where supported, and short fixed repair budget make this a more useful coding baseline. These are starting settings, not a promise that every model will solve the tasks or fit entirely in GPU memory.

A smaller first batch using both native-capable and text-only models:

```powershell
python -u dsh_bench.py run --models "qwen2.5-coder:7b,qwen3:4b,ministral-3:3b" --tasks group-by,merge-intervals,result-types --pull --tool-protocol text --context 8192 --tokens 2048 --thinking off --max-submissions 3 --max-steps 6 --seconds 300 --run dsh-repair-v2-small
```

The existing compiler image `ts-coding-bench-sandbox:v1` is reused; this revision does not require an image rebuild if your overnight runs already used it. On a new installation, `python dsh_bench.py build` builds it first. Building/downloading is a host setup action; the model has no network access.

## What the agent is told and allowed to do

Every session gets explicit instructions:

> You are offline. There is no shell, browser, network, package manager or documentation-fetch tool. Never request npm/npx/pip installs, curl, wget, git clone, or online access. TypeScript 5.9.3 and the checker are already installed. Compilation and public checks run automatically for each submission.

The **only DSH tool is `submit_solution(source)`**. It receives a complete TypeScript implementation and returns strict compiler diagnostics, public API/type-contract results and public runtime-example results. No shell quoting, file-writing commands, dependency installation or separate submit step is required.

The agent can change code after receiving public feedback. Private checks and reference implementations never enter the prompt, tool configuration or public grader. After DSH stops, first and final distinct submissions receive the existing private grading. The last distinct submission is authoritative; hidden scores never select a best-of-many answer.

Public graders run with `--network none`, a read-only root, an unprivileged user, resource limits and **no host mounts**. Private graders are likewise isolated. There is no long-lived model shell container in v2. `--pull` downloads base models through the host runner; it does not give the model internet access.

## Models without native tools

| Option | Behavior |
|---|---|
| `--tool-protocol text` | Default and recommended comparison mode. Removes native tool schemas from provider requests. Model returns a complete TypeScript code block, raw source, or the documented JSON submission action. Adapter validates final content and creates a DSH `submit_solution` call. |
| `--tool-protocol native` | Uses native function calls when supported. Falls back to text if native support is not advertised, unless strict mode is enabled. |
| `--tool-protocol auto` | Starts native for models advertising tools, otherwise text; switches native to text after an invalid native response. Actual mode is recorded, including mixed sessions. |
| `--strict-capabilities` | Optional: rejects unsupported explicitly requested native tools or thinking. Leave this off when comparing all models. |

Text mode uses the same grading, tool, feedback and budgets for all models. DSH continues to drive the agent/tool loop; Python translates its provider messages. Reasoning is kept in raw logs and is never mined for executable source. Only validated final-answer content can become a submission.

Empty starters, wrong tool names, extra arguments and missing source are rejected. Response-format errors receive a correction opportunity, up to `--max-protocol-errors` (default 3). Repeated source hashes do not create new candidates or rerun checks; two duplicate submissions stop the session. `repair_submissions` now counts actual distinct submitted revisions.

Public checks passing ends the repair loop. Otherwise it stops at the submission, request, tool-call, format-error or wall-time limit. Completed first/final results can still fail hidden checks: public success does not imply full correctness.

## Thinking and context

- `--thinking off`: request disabled reasoning on models that support a thinking setting.
- `--thinking on`: request reasoning where supported; unsupported models continue without that setting.
- `--thinking auto`: follow each catalog entry's thinking flag where supported.
- Results record `thinking_requested`, `thinking_effective` (the setting sent), `thinking_reason`, and `thinking_observed` (whether returned reasoning fields contained text). The dashboard filters by the effective setting. Model/provider behavior can still differ from the requested setting; observed reasoning helps detect this.
- `--tokens` is the output limit **per provider request**, not the entire session.
- Provider history keeps the original instructions/task, latest candidate with public feedback, and latest format correction. Earlier candidates and reasoning are not replayed. Full original DSH events and provider streams remain saved.
- Feedback sent to the model is bounded for context space; full public grader diagnostics remain in the saved submission artifacts.
- A conservative message-byte estimate reserves output and tool-schema headroom. This is not an exact model tokenizer. Oversized history stops with `context_budget` instead of silently truncating source. If that occurs, increase context in a **new run**, for example 12288, while keeping the same output/repair limits.
- Output truncated by the provider is reported as `output_token_limit` and is not submitted as a complete implementation. Timeouts, transport issues and format failures remain visible.

Flash Attention and KV-cache settings still belong to the already-running Ollama server. See [USAGE.md section 9](../USAGE.md#9-attention-and-kv-cache). Client flags do not reconfigure that server.

After getting a complete baseline, compare thinking using the same task/model subset and a new run name. If you change output/time budgets too, treat it as a separate budget experiment, not an isolated thinking comparison.

## Public versus private examples

`dsh_public.py` contains independently written, visible examples and positive API/type-contract checks for all 16 tasks. These include required exports, readonly inputs, representative error cases and generic return types. They are shown in the initial task prompt. They do not import/copy the private checks or reference answers from `tasks.py`.

Public checks are intentionally incomplete; the original final runtime/type checks stay private. Public suite hash, private suite hash, harness hash, image ID, model digest and all budgets are recorded. Old v1 and new v2 runs remain separate experiments in the viewer.

The `passed` and `first_passed` fields retain the original private-suite scoring rules. Public outcomes are reported separately; because the example sets differ, their results can disagree. A private-suite pass is not a proof that every possible specification case has been covered.

## Results and dashboard

Restart your viewer server once to load its new artifact support:

```powershell
python viewer/serve.py
```

Open http://127.0.0.1:8765 and filter **Workflow → source_repair_v2**.

New metrics/filters include:

- Source-submission rate and clean protocol success rate.
- First/final private task pass rates.
- Pass rate among graded implementations, with the number of excluded ungraded attempts explicitly shown.
- Public/private runtime-check fractions; type correctness remains part of the final task pass.
- Distinct candidates, protocol errors, tokens, elapsed time and stop reason.
- Failure category: coding, protocol, budget or environment. Main end-to-end pass rate still includes unsuccessful attempts, so protocol failures cannot silently inflate rankings.
- Actual tool protocol and requested/effective/observed thinking.

Artifacts include `public-result.json`, `protocol-summary.json`, per-request `protocol-*.json` and `history-*.json`, raw provider streams, DSH events, first/final source and grades, and each distinct submission's public grade.

`wall_s` includes DSH/public-feedback execution and cleanup; `end_to_end_s` adds private grading. Suite `timing.json` also includes setup/downloads and accumulates across resumes. Generation tokens/second stays blank because agent time is not pure generation time.

Ctrl+C once stops the session, cleans up, and saves/grades any captured source. Rerun the identical command to skip saved results and continue. Saved failed attempts are not silently retried. Changed settings/model selection/code require a new run name. Both generations of runs accumulate in the same dashboard.

## Validation performed during implementation

Only static source/syntax checks. No benchmark task, candidate code, reference answer, model, Docker image build or grader was executed. Runtime integration and comparative quality must be checked by your manually launched runs.
