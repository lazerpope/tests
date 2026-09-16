# Run your coding benchmarks

All commands below are for you to run in PowerShell. Editing configuration or reading this guide does not start anything.

## DSH v2: recommended offline repair benchmark

From the benchmark folder, with Ollama and Docker's Linux engine running:

~~~powershell
python -u dsh_bench.py run --suite typescript --pull --tool-protocol text --context 8192 --tokens 2048 --thinking off --max-submissions 3 --max-steps 6 --seconds 300 --run dsh-repair-v2
~~~

Runs all enabled models using the same source-submission protocol, even without native tools. Agents are told explicitly that internet, shell and package installation are unavailable; the installed compiler and public checks run automatically. One initial implementation plus two distinct repairs; hidden grading stays private. Use a new run name instead of resuming the overnight v1 run.

See [the current DSH guide](dsh/WORKFLOW-V2.md) for a small first batch, capability/thinking handling, context limits, stopping/resuming and dashboard metrics. The existing overnight compiler image is reused. No tests or models were started while implementing these changes.

## 1. Open the benchmark folder

~~~powershell
cd C:\Users\Max\Documents\_dev\AI\tests\ts-coding-bench
~~~

Requirements: Python 3.10+, Node.js 24+, Ollama. The compiler dependency is pinned in package-lock.json. If dependencies are missing:

~~~powershell
npm ci --ignore-scripts --no-audit --no-fund
~~~

## 2. Select models in models.json

### If startup fails with WinError 10061

The configured Ollama endpoint refused the connection. No model tasks started if this happened during the initial version check.

Start the Ollama Windows app, or run the following in another terminal and keep it open:

~~~powershell
ollama serve
~~~

Then repeat your benchmark command. If you use a custom server address, set it in the benchmark terminal:

~~~powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
~~~

For custom attention/cache settings, use the server launcher described in sections 8–9 instead. Do not start a second server if one already owns port 11434.

Only **qwen3:8b** is enabled initially. Set enabled to true on each model you want, and false on the others:

~~~json
{"name":"qwen3:8b","gb":5.2,"group":"core","enabled":true,"thinking":true}
~~~

- enabled controls the default selection for run, pull, models, and dsh-export.
- thinking declares reasoning capability for offline DSH exports. The direct benchmark checks actual Ollama capabilities instead.
- No model is downloaded unless you explicitly run pull or add --pull to run.
- Explicit --models overrides enabled flags. Every name must exist in models.json.
- Explicit --profile core/all/offload overrides enabled flags and selects that entire group. Avoid these options if you only want your checked models.

Inspect the selected models, without contacting Ollama:

~~~powershell
python bench.py models
~~~

## 3. Choose a suite

| Suite | Status | Purpose |
|---|---|---|
| typescript | Active | 16 small coding tasks; compile-time and runtime checks |
| engine2d | Inactive | Future project bug-fix tasks with independent numerical checks |

~~~powershell
python bench.py suites
python bench.py tasks --suite typescript
~~~

engine2d fails immediately with an explanation if selected. It does not read your engine project or run anything. Changing enabled alone cannot activate it: a snapshot, injected bug, runner, and grader still need to be implemented.

## 4. Examples: preview, download, run

### Preview the exact plan without any model calls, downloads, or tests

~~~powershell
python bench.py run --suite typescript --dry-run
python bench.py run --suite typescript --models "qwen3:8b,qwen2.5-coder:3b" --run ts-two --dry-run
~~~

### Run only the enabled models

~~~powershell
python -u bench.py run --suite typescript --run ts-selected
~~~

### Run exactly one model

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --run ts-qwen3
~~~

### Download and run exactly two models

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b,qwen2.5-coder:3b" --pull --run ts-two
~~~

### Download selected models without benchmarking them

~~~powershell
python bench.py pull
python bench.py pull --models "qwen2.5-coder:3b"
~~~

### Run only a few tasks

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --tasks "group-by,lru-cache,binary-search-fix" --run ts-short
~~~

### Record a log while seeing live output

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --run ts-logged 2>&1 | Tee-Object -FilePath ts-logged.log
~~~

## 5. Generation and thinking settings

Edit settings.json for defaults, or override them on the command line. CLI values take precedence.

| Setting / CLI option | Meaning |
|---|---|
| temperature / --temperature | Sampling randomness; 0 is the initial deterministic setting |
| top_p / --top-p | Probability-mass cutoff for sampling |
| top_k / --top-k | Number of candidate tokens considered |
| min_p / --min-p | Relative probability cutoff |
| repeat_penalty / --repeat-penalty | Repetition penalty; 1 means no penalty |
| context / --context | Ollama context allocation, including prompt and answer |
| tokens / --tokens | Maximum generated tokens, including thinking when enabled |
| thinking / --thinking off or on | Disable/enable reasoning for models supporting it |
| seed / --seed | Sampling seed; repeat index is added for subsequent repeats |
| repeats / --repeats | Attempts per task; all attempts count, not best-of |

Example with sampling controls:

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --temperature 0.2 --top-p 0.9 --top-k 40 --min-p 0.05 --repeat-penalty 1.05 --context 4096 --tokens 2048 --thinking off --run ts-sampling
~~~

Thinking comparison:

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --thinking on --context 8192 --tokens 4096 --run ts-thinking
~~~

Larger context uses more memory and can trigger CPU offload. The configured output cap must be smaller than context; leave room for prompts too. Thinking-on is refused for models without that capability. Different settings should use separate run names.

## 6. Know whether a run is progressing

The terminal shows:

- Selected suite, models, settings, report location, and total attempts.
- [current/total] model, task, and repeat.
- Separate download, load/warmup, generation, and compile/check stages.
- A heartbeat every 5 seconds, even while waiting for the server.
- During generation: received chunk count, answer characters, thinking characters, and age of the last update.
- Downloaded GB when Ollama reports sizes.
- Outcome, tokens/second, and request duration after each answer.

Example output format (illustration, not measured results):

~~~text
[1/16] qwen3:8b | group-by | repeat 1
  [generating] started
  [generating] elapsed 5s | 95 chunks | 330 answer chars | 0 thinking chars | last update 0s ago
~~~

A heartbeat proves the Python runner is alive, not that the GPU is making progress. If no updates arrive for 30 seconds, the status explicitly says the server may be loading or stalled. Network reads time out after 120 seconds without data by default. This is an inactivity timeout, not a total generation deadline. A slow server that keeps sending data can continue longer.

~~~powershell
python -u bench.py run --models "qwen3:8b" --heartbeat 2 --idle-timeout 180 --run ts-visible
~~~

For an additional view, run these yourself in another terminal:

~~~powershell
ollama ps
nvidia-smi
~~~

## 7. Results, stop, and resume

### One dashboard for all dates and runs

Open **runs/index.html** to view all saved benchmark attempts together. It is rebuilt automatically whenever a new run saves an answer or rebuilds its report. Existing runs are included regardless of date or current model selection.

To collect older results immediately, or update while an older benchmark process is still running:

~~~powershell
python bench.py dashboard
~~~

This command only reads saved results and builds HTML/CSV. It does not execute tests, call models, or download anything.

Example: run three tasks now, four later, then see all seven attempts on the same page:

~~~powershell
python -u bench.py run --models "qwen3:8b" --tasks "group-by,lru-cache,binary-search-fix" --run batch-one
python -u bench.py run --models "qwen3:8b" --tasks "parse-csv,query-parser,path-normalize,typed-pick" --run batch-two
~~~

Use a different run name for each new batch. Reusing a run name resumes its original task/model selection and skips saved attempts.

The dashboard filters by run, suite, model, outcome, and task name. It includes links to original answers and settings, and exports runs/all-results.csv. Run/model summaries remain separate so changed settings, task subsets, or suite versions do not silently produce one misleading score. Repeating a task in another run adds another attempt; rebuilding the dashboard does not duplicate saved files.

Refresh the browser after a rebuild, or enable its 15-second auto-refresh checkbox. Auto-refresh reloads the generated page; it does not itself scan folders. Corrupt/unreadable result files appear in import warnings and are skipped. Self-test folders without benchmark manifests are excluded. Keep run folders to retain their history; deleting one removes it from the next dashboard build.

For --run ts-selected, open **runs/ts-selected/report.html**. The page is standalone and has model filtering, sortable results, and task details. Refresh it after more answers finish. results.csv and raw answers are alongside it.

To rebuild a report from saved results (no model calls or tests):

~~~powershell
python bench.py report --run ts-selected
~~~

To stop after the active task/setup stage:

~~~powershell
New-Item -ItemType File -Path .\runs\ts-selected\STOP -Force
~~~

To resume, remove that marker and repeat the exact original run command:

~~~powershell
Remove-Item -LiteralPath .\runs\ts-selected\STOP
python -u bench.py run --suite typescript --run ts-selected
~~~

Ctrl+C interrupts immediately; saved results remain. Interrupted attempts without result.json are retried. Completed attempts, including model errors, are skipped on resume. Model setup errors are retried. Do not change enabled model selection, settings, tasks, or code while resuming a run; use a new run name for changed experiments.

A crash may leave runs/active.lock containing the process PID. Only remove it after verifying that process is no longer running. The lock prevents two benchmark runs from sharing GPU timings.

## 8. DSH: use the same model presets

**Current scope:** DSH export prepares configuration for your manual DSH sessions. The active TypeScript benchmark still calls Ollama directly; it does not run DSH agents. Automated engine2d/DSH scoring remains inactive.

Export your selected models and settings without contacting Ollama or launching DSH:

~~~powershell
python bench.py dsh-export --export my-dsh
~~~

Or specify models and settings:

~~~powershell
python bench.py dsh-export --models "qwen3:8b" --export qwen-thinking --context 8192 --tokens 4096 --temperature 0.2 --top-p 0.9 --top-k 40 --min-p 0.05 --repeat-penalty 1.05 --thinking on --flash-attention on --kv-cache-type q8_0
~~~

The export contains:

| File | Purpose |
|---|---|
| *.Modelfile | Named Ollama presets with context and sampling defaults; original model unchanged |
| create-models.ps1 | Commands to create those local model aliases when you run it |
| dsh-settings.yaml | Provider settings section listing only the selected aliases |
| serve-ollama.ps1 | Starts Ollama with the chosen attention/cache environment when you run it |
| settings-snapshot.json | Exact exported settings |

Existing export folders are never overwritten. Use a new --export name for new settings.

### Apply an export yourself

1. Pull any missing base models with the pull command.
2. Quit the existing Ollama application from the Windows tray.
3. In one PowerShell terminal, start the generated server launcher:

~~~powershell
.\exports\my-dsh\serve-ollama.ps1
~~~

4. Keep that terminal open. In a second terminal, create the aliases:

~~~powershell
cd C:\Users\Max\Documents\_dev\AI\tests\ts-coding-bench
.\exports\my-dsh\create-models.ps1
~~~

5. Merge the **llm-pi-ai** section from dsh-settings.yaml into your existing DSH settings.yaml, preserving your other settings. The exported file uses JSON notation, which is valid YAML. It is a settings section, not a complete DSH plugin composition. Your DSH installation must have the dsh-llm-pi-ai plugin mounted.
6. In the terminal where you launch your installed DSH, set the local placeholder key:

~~~powershell
$env:OLLAMA_API_KEY = "ollama"
~~~

7. Launch DSH as you normally do. Select provider **ollama-bench** and one of the exported aliases.

The route points to http://127.0.0.1:11434/v1. The placeholder key is for the adapter's credential requirement; it is not a paid API key.

### Which settings DSH uses

- Modelfiles carry temperature, top-p, top-k, min-p, repeat penalty, seed, context, and output defaults.
- DSH sends the configured maxTokens and offers off/high reasoning for catalog entries marked thinking:true. The off wire value is none, matching Ollama's OpenAI-compatible API. High requests thinking; it is not a promise of a fixed reasoning budget on Qwen.
- Explicit values sent by DSH override Modelfile defaults (notably temperature/output limit). Match those values in your DSH session/plugin configuration; exporting defaults cannot force an application to honor them.
- DSH's contextWindow is metadata used by the harness; the alias's num_ctx controls the Ollama allocation. The export sets both.
- Some catalog models do not support tools and may be unsuitable for DSH even when direct coding answers work.
- DSH is a changing developer preview. The configuration is based on the official source below, but this integration has not been executed or compatibility-tested in your installation.

## 9. Attention and KV cache

These are **Ollama server settings**, shared by direct benchmarks and DSH clients. They are not per-task DSH generation parameters.

| Setting | Options |
|---|---|
| flash_attention / --flash-attention (export) | true/false in settings.json; on/off on CLI |
| kv_cache_type / --kv-cache-type (export) | f16, q8_0, q4_0 |

The export defaults are Flash Attention enabled and q8_0 KV cache. Quantized cache requires Flash Attention; export rejects incompatible combinations. Cache quantization can affect quality as well as memory. Do not combine measurements from different cache modes under one run name.

Manual equivalent, after quitting the running Ollama application:

~~~powershell
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_CONTEXT_LENGTH = "4096"
ollama serve
~~~

Environment variables apply to this new server process. Changing settings.json or your client shell does not reconfigure an already-running server. Verify effective backend settings from Ollama server logs. Benchmark metadata records client environment values only; those are not proof of server configuration.

There is no generic “attention strength” control here. Flash Attention is an execution optimization; KV cache stores attention state; thinking controls reasoning generation.

## 10. Optional harness self-tests

Only run these yourself if you want to validate the task harness. They use built-in reference answers and intentionally broken answers, not Ollama:

~~~powershell
python bench.py selftest --suite typescript
~~~

Scoring requires strict compilation, runtime checks, and applicable type checks. These small tasks do not measure repository navigation or framework work. Generated code runs with Node permission restrictions and time/memory limits, but the VM context is not a security boundary for hostile code.

## Official references

- [DSH provider configuration](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-pi-ai/README.md)
- [DSH configuration catalog](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/config-catalog.md)
- [Ollama OpenAI-compatible fields](https://docs.ollama.com/api/openai-compatibility)
- [Ollama Modelfile parameters](https://docs.ollama.com/modelfile)
- [Ollama Flash Attention and KV cache](https://docs.ollama.com/faq)
