# Benchroom viewer

A separate, read-only dashboard for all saved benchmark runs. It does not import the benchmark, execute tests, download models, or modify results. No npm install, framework build, CDN, or Python packages are required.

## Start

From ts-coding-bench:

~~~powershell
python viewer/serve.py
~~~

Open **http://127.0.0.1:8765** in your browser. Keep the terminal open. Ctrl+C stops only this viewer. Use --port 8766 if the default port is occupied.

## Features

- Include/exclude each run, or select/clear all.
- Filters for model, task, outcome, suite, backend, thinking, category, context, output cap, temperature, top-p/top-k/min-p, repetition penalty, seed, repeat index, model digest, suite/harness revision, and GPU.
- Date, throughput, latency, and completed-group filters; text search includes errors.
- Quality/speed scatter plot, outcome breakdown, latency histogram and daily result counts.
- Sortable comparison board and clickable task heatmap.
- Paginated answer explorer with source, prompt, thinking, compiler diagnostics, test definitions and raw result inspection.
- Run notebook with full configuration, hardware, setup errors and harness-change history.
- Export exactly the filtered attempt rows to CSV.
- Live refresh every 10 seconds without losing filters. Preferences persist in browser storage.

## Interpret results

Pass rates use saved attempts matching your filters. Compile errors count as failed attempts. A passing task must satisfy all checks; partial correctness is visible in the answer inspector.

Comparison groups stay separate by run, model, model digest and harness revision. Different task subsets, settings, and hardware are not a controlled comparison simply because they share a graph. Partial groups are marked. “Complete” describes saved attempt coverage, not whether tasks passed.

Speed and latency are medians over filtered attempts. Generation tokens/s counts model-specific tokens, including reasoning when enabled. Answer latency includes the model request, not compiler/test execution. Missing speed data is omitted from medians, not treated as zero.

The timeline and date filters use result file modification timestamps in UTC; copying files may change those times. Run dates remain visible in the notebook. Attention/cache configuration cannot be reliably inferred from client environment values; inspect the saved manifest and your Ollama server configuration.

The notebook follows run toggles; other filters apply to attempt comparisons. A newly discovered run is selected by default. Hidden or malformed files are never evaluated; incomplete/corrupt JSON is skipped with an import diagnostic. Self-test directories without manifests are excluded.

## Isolation

Only the new viewer folder contains this application. It reads runs/*/manifest.json, saved result files and model setup errors. Artifact access is restricted to a small filename allowlist inside the runs directory. The server binds to localhost and implements no write endpoint.
