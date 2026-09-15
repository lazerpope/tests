# Coding benchmark

See [USAGE.md](USAGE.md) for examples and complete instructions.

- **typescript:** active, 16 tasks.
- **engine2d:** inactive placeholder.
- Set **enabled: true** on selected entries in models.json. Only qwen3:8b is enabled initially.
- Change generation defaults in settings.json.
- Runs and downloads happen only when you launch their commands.
- DSH export prepares model presets, provider settings, and attention/cache server configuration for manual use; it does not run agent benchmarks.

Preview without running anything:

~~~powershell
python bench.py run --suite typescript --dry-run
~~~

Run yourself:

~~~powershell
python -u bench.py run --suite typescript --models "qwen3:8b" --run ts-qwen3
~~~
