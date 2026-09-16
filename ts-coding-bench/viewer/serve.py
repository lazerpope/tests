"""Read-only benchmark viewer. Does not import or execute benchmark code."""
import argparse
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"

def snapshot():
    runs, rows, warnings = [], [], []
    def read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.append(f"{path.relative_to(RUNS)}: {exc}")
            return None
    for path in RUNS.glob("*/manifest.json"):
        manifest = read(path)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("config"), dict):
            continue
        config = manifest["config"]
        run = dict(id=path.parent.name, created=manifest.get("created", ""),
                   config=config, hardware=manifest.get("hardware", {}),
                   history=manifest.get("harness_changes", []), errors=[])
        timing_path = path.parent / "timing.json"
        if timing_path.exists():
            run["timing"] = read(timing_path)
        for error in path.parent.glob("errors/*.json"):
            value = read(error)
            if value is not None:
                run["errors"].append(value)
        runs.append(run)
        for result in path.parent.glob("answers/*/result.json"):
            value = read(result)
            if not isinstance(value, dict) or not all(k in value for k in ("model", "task", "status", "passed")):
                continue
            try:
                saved = dt.datetime.fromtimestamp(result.stat().st_mtime, dt.timezone.utc).isoformat()
            except OSError:
                continue
            rows.append({**value, "run":run["id"], "saved":saved,
                         "artifact":result.parent.relative_to(RUNS).as_posix(),
                         "id":result.relative_to(RUNS).as_posix()})
    return dict(runs=sorted(runs, key=lambda r:r["created"], reverse=True), rows=rows,
                warnings=warnings, updated=dt.datetime.now(dt.timezone.utc).isoformat())

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, code, content, mime="application/json; charset=utf-8"):
        raw = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/results":
            return self.send(200, json.dumps(snapshot(), ensure_ascii=False))
        if url.path == "/api/artifact":
            rel = parse_qs(url.query).get("path", [""])[0]
            target = (RUNS / rel).resolve()
            allowed = {"solution.ts", "answer.txt", "thinking.txt", "compile.log",
                       "request.json", "result.json", "typechecks.ts", "checks.json",
                       "first-solution.ts", "first-result.json", "dsh-events.jsonl",
                       "tool-events.jsonl", "dsh-stderr.log", "provider-errors.jsonl",
                       "public-result.json", "protocol-summary.json"}
            if not target.is_relative_to(RUNS.resolve()) or target.name not in allowed:
                return self.send(403, '{"error":"Artifact not allowed"}')
            try:
                if target.stat().st_size > 2_000_000:
                    return self.send(413, '{"error":"Artifact exceeds 2 MB display limit"}')
                return self.send(200, target.read_text(encoding="utf-8"), "text/plain; charset=utf-8")
            except OSError:
                return self.send(404, '{"error":"Artifact not available"}')
        files = {"/":("index.html","text/html"), "/app.js":("app.js","text/javascript"),
                 "/style.css":("style.css","text/css")}
        if url.path not in files:
            return self.send(404, '{"error":"Not found"}')
        filename, mime = files[url.path]
        return self.send(200, (HERE / filename).read_bytes(), mime+"; charset=utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"Benchmark viewer: http://127.0.0.1:{args.port}\nReading: {RUNS}\nRead-only. Ctrl+C stops only this viewer.", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
