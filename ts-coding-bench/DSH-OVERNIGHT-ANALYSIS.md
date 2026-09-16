# DSH overnight analysis — 2026-09-16

Read-only analysis of saved files. No model requests, benchmark tests, Docker commands, or changes to the running harness were made for this analysis. The second run was still producing results during inspection; its figures below describe the completed Ministral-3:3B group at the final snapshot.

## Conclusion

The first run predominantly measured failures to operate the tool/submission workflow, not incorrect TypeScript implementations. Increasing the reasoning budget does not address these failures. The original integration needs a simpler submission interface, a text adapter for models without native tool calling, and better separation of protocol/environment failures from coding scores.

## Main run: dsh-thinking_overnight

| Observation | Count |
|---|---:|
| Saved attempts | 166 |
| Passed tasks | 1 |
| No submission | 141 |
| Attempts with a submitted file | 25 |
| Final files still exactly `export {};` | 21 |
| Non-starter final files | 4 |
| Submitted attempts with identical first/final source | 24 / 25 |
| Summed agent-session time | 4.99 hours |
| Stops at output-token limit | 44 |
| Stops at provider-request budget | 30 |
| Shell calls ending with timeout code 124 | 144 |
| Timed-out shell calls containing `npx` | 139 |
| `submit` calls carrying unexpected arguments | 113 / 265 |

The manifest plans 30 models, but saved attempts cover only 11: ten complete groups and six tasks for Qwen3:8B. There are no saved model setup errors in this run. The remaining planned models were not reached in this snapshot; they should not all be described as unsupported/skipped.

### 1. Textual tool calls were not executed

Qwen2.5-Coder 0.5B, 1.5B, 3B and 7B each have 16 `no_submission` results. In the inspected Qwen2.5-Coder 7B group-by response, the provider returned this as ordinary assistant content:

```json
{"name":"bash","arguments":{"command":"tsc --init --strict --esModuleInterop --module commonjs --target es2022 --outDir ./dist"}}
```

The response had no native `tool_calls` and finished with `stop`. DSH therefore ended the turn without running the shell. This is a protocol compatibility failure, not evidence that the model cannot implement groupBy.

Evidence: [saved provider stream](runs/dsh-thinking_overnight/answers/qwen2.5-coder_7b--group-by--0/provider-stream-001.jsonl), [result](runs/dsh-thinking_overnight/answers/qwen2.5-coder_7b--group-by--0/result.json).

The current runner's capability checks have been commented out. That permits requests but does not supply the missing text-to-tool translation.

### 2. Empty files were repeatedly submitted

Qwen3:4B group-by submitted the starter file 20 times. Qwen3:8B did the same. The latter's first provider tool call was named `submit` but carried a `command` argument intended for a shell. The submit tool has no arguments and its implementation ignores the supplied object, so it graded the unchanged starter.

The logs establish the wrong tool/argument combination at the provider boundary. They do not establish whether the original mistake came from model generation, its template, or Ollama's tool parser.

The harness should reject unexpected arguments and empty/unchanged starter submissions with actionable feedback. It should count distinct source hashes, not describe every repeated submission as a code repair.

Evidence: [Qwen3:8B tool log](runs/dsh-thinking_overnight/answers/qwen3_8b--group-by--0/tool-events.jsonl), [source](runs/dsh-thinking_overnight/answers/qwen3_8b--group-by--0/solution.ts), [result](runs/dsh-thinking_overnight/answers/qwen3_8b--group-by--0/result.json).

### 3. The development environment wasted tool calls

There were 139 timeouts on `npx` commands and five on other commands, including npm installation attempts. At the 20-second shell limit, those 144 timeouts alone consume roughly 48 minutes.

The image installs TypeScript under `/opt/compiler` and places its bin directory on PATH, while the workspace has no normal local npm compiler dependency. `npx` can attempt package resolution/install; network is disabled. That is a plausible explanation for the repeated stalls, consistent with the recorded commands, but no runtime reproduction was performed.

Provide a ready-made project, local compiler resolution, tsconfig and a trusted `check` action. Explicitly tell the model dependencies are already installed. Unexpected package commands should fail quickly with guidance instead of waiting for network timeouts. Do not enable network access to solve this benchmark-environment issue.

Evidence: [Qwen3.5:4B group-by tool log](runs/dsh-thinking_overnight/answers/qwen3.5_4b--group-by--0/tool-events.jsonl), [timeout feedback](runs/dsh-thinking_overnight/answers/qwen3.5_4b--group-by--0/provider-request-003.json).

### 4. Reasoning and history consumed the budgets

44 attempts stopped with `max-tokens`; sampled provider responses used all 8192 output tokens with no ordinary answer content. Some did reasoning without reaching a tool call. The highest recorded prompt usage was 16,377 tokens against the configured 16,384 context size: effectively no reserved output headroom.

The run generated approximately 900,690 reported output tokens. More output is not equivalent to more candidate implementations: only four final sources were non-starters.

The runner needs an explicit context/history budget and repeated-action detection. Compare thinking on/off under controlled settings after fixing the workflow. Do not infer CPU offload or GPU bottlenecks from these logs: actual VRAM placement was not recorded here.

### 5. There are also real coding failures

Among the four non-starter final files:

| Model / task | Actual grading finding |
|---|---|
| Qwen3:4B / result-types | Passed runtime and type checks |
| Qwen3:4B / merge-intervals | Passed first two runtime groups; mutated a frozen input in the third |
| Qwen3.5:4B / result-types | Passed both runtime groups; failed type checks because `Result` was not exported |
| Qwen3.5:4B / retry | Failed the public first runtime group; passed the other two |

These are relevant coding results. Private failures are deliberately not fed back, so a model that passes a weak public example can stop without discovering them. Keep hidden grading private, but provide better independently written public examples and public API/export/type contract checks based on the task specification.

## Second run: dsh-thinking_overnight-2

Completed Ministral-3:3B group:

| Measure | Result |
|---|---:|
| Tasks | 16 |
| First-submission passes | 0 |
| Final-submission passes | 3 |
| Saved direct-run passes on matched tasks/model digest | 0 |
| Summed agent-session time | 876.7 seconds |

The repaired successes are binary-search-fix, result-types and topological-sort. This is evidence that public-feedback repairs can help. It is a small sample. The direct run used 4096 context / 2048 output tokens, while DSH used 16384 / 8192, so it does not isolate the effect of DSH. Also, the second run uses a 500-second session budget rather than the first run's 1000 seconds.

## How to include models without native tools

Implement an explicit **text tool protocol** in the DSH provider adapter:

1. Present the same allowed tool actions in the prompt; omit native `tools` from requests to unsupported models.
2. Require one structured action in ordinary assistant content. Parse only that content, never reasoning text.
3. Validate the action name, arguments and size against a strict allowlist.
4. Convert the validated action to a DSH tool-call event. DSH continues using the existing isolated executors and returns public feedback through the adapter.
5. Translate tool history back to ordinary messages for models lacking native tool roles.
6. Preserve raw output, normalized actions and protocol errors. Keep the same isolation, hidden graders, time and call limits.

This changes the interface, not the model's native capabilities. Record `tool_protocol=native|text`, and do not silently label emulated calls as native support. For the strongest like-for-like coding comparison, use the same text protocol for every model in that experiment.

For these single-file tasks, simplify the main action to `submit_solution(source)`: the harness writes the source and returns trusted compilation/public-check feedback. This avoids requiring the model to operate a shell, quote a heredoc and remember a separate submit step just to demonstrate TypeScript skill. Keep the full shell-agent benchmark as a separate experiment if repository-tool competence is also of interest.

## Recommended next experiment

Make the changes in a new harness revision/run; preserve these historical files.

1. Add text protocol and source-based submission. Reject wrong arguments, unchanged starter files and repeated identical submissions.
2. Supply a functioning offline development workspace and deterministic public `check`; remove repeated npm setup work.
3. Add specification-derived public API/type checks and representative examples; retain independent hidden checks.
4. Start with the same small task/model subset, a fixed initial attempt plus two repair opportunities, and thinking off where supported. Then compare a separate thinking-on run with identical tasks and limits.
5. Report: protocol success rate, real-source submission rate, compilation rate, public/hidden check fractions, first/final task passes, distinct candidate count, total elapsed time and tokens.
6. Keep overall end-to-end success as a metric, but show protocol/environment failures separately. Conditional code-quality scores must display how many attempts never produced code to avoid overstating performance.

Do not raise the overnight budgets again before fixing these workflow failures.

## Official protocol/environment references

- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling): tool calls are a structured response field, followed by tool-result messages.
- [npm exec / npx](https://docs.npmjs.com/cli/v11/commands/npm-exec/): missing requested packages can be installed into npm's cache.
- [Ollama thinking](https://docs.ollama.com/capabilities/thinking): reasoning and ordinary response content are separate outputs.
