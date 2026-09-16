# DSH coding benchmark

## Current workflow: v2 offline source repairs

**Use [WORKFLOW-V2.md](WORKFLOW-V2.md) for current commands and behavior.** New runs use direct source submissions, a text adapter for models without native tools, independent public examples/type checks, and a default three-candidate repair budget. Agents are explicitly told they are offline and receive no shell or network tool.

The remainder of this document describes the **legacy v1 shell workflow** for interpreting existing runs and is retained with your earlier examples. Its shell tools, capability rejections and first-check-group disclosure do not describe new runs.

This is a separate **real DeepSeek Harness agent runner**. The existing `bench.py run` remains the direct Ollama benchmark. Nothing here starts until you run a command.

## First run

From the `ts-coding-bench` folder:

1. Start Docker Desktop using **Linux containers**. Start your local Ollama server.
2. The adapter targets your installed **DSH 0.1.5-rc.1** and requires Node.js 24+. It rejects other DSH versions to avoid silently changing tool access or the protocol. If installing on another machine, use `npm install -g @deepseek-ai/dsh@0.1.5-rc.1`.
3. Build the isolated compiler image once. This downloads the Node image and TypeScript; it does not run benchmark tasks:

```powershell
python dsh_bench.py build
```

4. Start with one model and one task:

```powershell
python -u dsh_bench.py run --suite typescript --models "qwen3:8b" --tasks group-by --pull --context 8192 --tokens 2048 --thinking off --seconds 300 --run dsh-first
```
```powershell
python -u dsh_bench.py run --suite typescript --models "deepseek-coder:1.3b"  --pull --context 8192 --tokens 2048 --thinking off --seconds 300 --run dsh-first
```

**Implementation status:** source and syntax reviewed; the complete DSH/Docker/model pipeline has not been executed. Docker's Linux engine was unavailable during implementation. Your first run is the integration check. There is no fallback to an unrestricted host shell.

If DSH cannot be located automatically, add:

```powershell
--dsh-bin "C:\nvm4w\nodejs\node_modules\@deepseek-ai\dsh\lib\bin.js"
```

## All enabled models, with automatic downloads

```powershell
python -u dsh_bench.py run --suite typescript --pull --context 8192 --tokens 2048 --thinking off --run dsh-enabled
```

Without `--models`, selection uses `enabled: true` in `models.json`. Models must advertise **tool support** in Ollama's `/api/show`. Unsupported models are recorded as model setup errors, not failed coding tasks. They can still be evaluated by the direct runner.

To select specific catalog entries regardless of enabled flags:

```powershell
python -u dsh_bench.py run --models "qwen3:8b,qwen3:4b" --pull --context 8192 --tokens 4096 --thinking on --run dsh-thinking
python -u dsh_bench.py run --models "qwen2.5-coder:3b" --pull --context 8192 --tokens 4096 --thinking on --run dsh-thinking-qwen
python -u dsh_bench.py run --models "hf.co/Tesslate/OmniCoder-9B-GGUF:Q4_K_M" --pull --context 8192 --tokens 4096 --thinking on --run dsh-thinking-omni
```


A new alias named `tsb-dsh-<settings-hash>` holds each model's sampling/context preset. Aliases remain available after the run; base model weights are reused. No export or manual editing of DSH settings is necessary for this runner.

## What the model can access

```text
Python supervisor on your host
  │
  ├── DSH SDK session → loopback provider bridge → Ollama
  │       │
  │       └── bash / submit → isolated agent container
  │                            TASK.md
  │                            solution.ts
  │                            public-checks.json
  │                            Node + TypeScript compiler
  │
  ├── submit → save source checkpoint → fresh PUBLIC grader
  │                                      ↓
  │                              compiler + example feedback → DSH
  │
  └── stop DSH, remove agent container
           └── saved first/final source → fresh PRIVATE graders
                                            ↓
                                      results + dashboard
```

- The task prompt and **first check group** are public. The other check groups and all type checks are private. Final grading includes the complete original check set; the overall score therefore includes the disclosed public group. Compare agent runs with other agent runs using the same disclosure and budgets.
- Reference solutions, `tasks.py`, previous answers, run results and the host project are never copied into the agent container.
- The agent has no network, host directory mounts, Docker socket, credentials or host shell. Both built-in DSH shell tools are disabled. A fresh DSH home excludes your normal settings, project instructions and plugins.
- `bash` can edit files and run `tsc`. It starts in `/workspace` each call; files persist, shell variables do not. Each command has a 20-second limit and bounded output.
- `submit` captures a regular, bounded `solution.ts` file. Public checking happens in a **new** container using the original public check group. Editing `public-checks.json` cannot change trusted feedback.
- Hidden grading starts after DSH is stopped and its tools are removed. Hidden feedback is never sent back for another repair. Only saved source is graded; candidate package scripts are never used.
- Candidate globals execute in a separate VM context from the runtime assertions. Docker supplies the OS isolation; Node's VM alone is not treated as a security boundary. This restricts file/test exposure, but is not a formal proof against Docker/Node vulnerabilities or adversarial grading exploits.

## Reasoning, generation and cache controls

```powershell
python -u dsh_bench.py run --models "qwen3:8b" --pull --context 8192 --tokens 4096 --temperature 0.2 --top-p 0.9 --top-k 40 --min-p 0.05 --repeat-penalty 1.05 --seed 42 --thinking on --seconds 600 --max-steps 12 --max-tool-calls 24 --run dsh-qwen-reasoning
```

| Control | Meaning |
|---|---|
| `--thinking off/on/auto` | Off disables thinking for supported models; on requires thinking support; auto follows each catalog entry's `thinking` flag. DSH uses off/high reasoning, translated to Ollama none/high. |
| `--tokens` | Maximum output tokens **per model request**, including reasoning where the provider counts it. Not a total session token budget. |
| `--context` | Ollama context allocation and DSH model context metadata. Tool schemas, task, history, reasoning and output all need space. |
| `--max-steps` | Hard maximum provider requests per task, **including retries**. Defaults to 12; recorded DSH agent steps may differ. |
| `--max-tool-calls` | Maximum executed bash/submit calls per task. Defaults to 24. |
| `--seconds` | Session deadline, including container/DSH startup and public feedback. Defaults to 600. Cleanup and private grading can extend command duration beyond this deadline. |
| `--idle-timeout` | Provider network read timeout, default 120 seconds. |
| `--heartbeat` | Progress interval, default 5 seconds. Shows elapsed time, provider requests and submissions. |
| `--repeats` | Independent agent sessions per model/task, default 1. |

Generation defaults are read from `settings.json`; the examples explicitly request a larger context for agent history. The minimal DSH profile has no history compaction, so large conversations can exhaust context. Context and thinking also consume GPU memory; these settings are experimental budgets, not a guarantee that every model fits your 8 GB GPU.

The bridge forces temperature, top-p, seed, output limit and reasoning settings on each outgoing request. Top-k, min-p, repeat penalty and context are set on the Ollama alias. Exact outgoing JSON is saved as `provider-request-*.json` for inspection.

**Flash Attention and KV-cache precision remain Ollama server settings.** Configure them before starting the server using [USAGE.md section 9](../USAGE.md#9-attention-and-kv-cache). Editing client settings cannot reconfigure an already-running server. Run metadata labels client environment values as unverified server settings.

## Stop, resume and add models

- Press **Ctrl+C once**. During an agent session, the runner stops DSH, removes its containers, privately grades any submitted checkpoints, saves that attempt and exits. Allow cleanup/grading to finish.
- Rerun the **identical command** to skip saved task results and continue missing attempts. A saved failed or interrupted result is still a completed attempt and is not silently retried.
- If you stop during private grading, that attempt may have no `result.json`; the next run archives its incomplete artifacts and starts that task again. A hard process kill can also leave a lock or container behind.
- Changing models, task selection, budgets, image, sampling settings or harness code requires a **new `--run` name**. All runs remain visible together. You can disable tested models, enable new ones and start `--run dsh-new-models`.
- DSH uses the existing `runs/active.lock`; it refuses to compete with another benchmark. Remove a stale lock only after confirming the owning process has ended. Container names start with `tsb-agent-`, `tsb-public-`, or `tsb-grade-`; inspect `docker ps -a` after a hard kill and remove only abandoned benchmark containers.

## Results and timing

```powershell
python viewer/serve.py
```

Open **http://127.0.0.1:8765** and select **Backend → dsh**. Restart an already-running viewer server once to load its new artifact/timing support. The viewer reads saved files only.

- Main pass rate = private grading of the **last submitted** source. Final chat text and unsubmitted edits are not scored.
- First-submission pass rate = private grading of the first submitted source, before the first `submit` feedback. The model has already seen the public example and may have used its shell/compiler before submitting; this is **not** a one-shot baseline.
- Each task stores first/final source and grade, submitted checkpoints, tool log, DSH events, stderr, outgoing requests, token counts, submission count, tool calls, model requests and stop reason.
- `wall_s` measures the complete agent session, including public feedback and cleanup. `end_to_end_s` also includes private grading. Both exclude model setup/downloads performed before the task.
- `timing.json` accumulates active suite invocation time including downloads, aliases, sessions, grading and reporting. Pauses between invocations are excluded. It updates after each task and on normal exit; a hard kill loses timing since the last checkpoint.
- The time/pass-rate chart uses DSH `end_to_end_s`. Historical direct results have only generation `wall_s`, so use the Backend filter for timing comparisons.
- Generation tokens/second is left blank for DSH: agent wall time includes tools and is not pure generation time. Token totals come from completed provider usage responses; interrupted streams may be missing usage. `usage_scope` and `usage_responses` make this limitation explicit.
- Host/runtime errors are labeled separately from coding failures, but still appear among unsuccessful saved attempts. Filter Outcome and Agent stop reason when diagnosing a run. Model setup errors appear in the experiment notebook.

Result files are saved after each task; earlier models remain visible if you stop later. The runner also rebuilds the existing all-runs dashboard. No fake/sample benchmark results are added.

## Sources and compatibility

The adapter was written against the installed DSH 0.1.5-rc.1 SDK protocol, tool schema, loader and provider adapter sources, with these official references:

- [DSH minimal SDK profile](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/README.md)
- [DSH pi-ai provider adapter](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-pi-ai/README.md)
- [Ollama model creation and parameters](https://docs.ollama.com/api/create)
- [Ollama OpenAI-compatible request fields](https://docs.ollama.com/api/openai-compatibility)
