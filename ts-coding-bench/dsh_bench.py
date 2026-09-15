"""Run real DSH agents with Docker-only tools and private, post-session grading.

Nothing runs on import. See dsh/README.md before starting your first run.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

import bench

ROOT = Path(__file__).resolve().parent
SUPPORT = ROOT / 'dsh'
IMAGE = 'ts-coding-bench-sandbox:v1'
DSH_VERSION = '0.1.5-rc.1'
SYSTEM = ('You are solving a TypeScript coding benchmark using bash and submit. '
          'Work only in /workspace. Read TASK.md. Implement solution.ts with the requested exports. '
          'Use strict TypeScript, ES2022, CommonJS; no imports, external packages, Node APIs, '
          'timers, I/O, compiler suppression comments, or reference directives in the solution. '
          'You may use the shell and compiler to develop it. Call submit to save your answer '
          'and receive public feedback. Repair as needed within the budget. Your LAST submitted '
          'file is graded. A final chat reply is not a submission. Private checks are unavailable.')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def execute(args, *, data=None, timeout=60):
    result = subprocess.run([str(a) for a in args], input=data, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:])
    return result.stdout


def dsh_bin(explicit):
    candidates = [Path(explicit)] if explicit else []
    for name in ('dsh.cmd', 'dsh', 'dsh.ps1'):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).parent / 'node_modules/@deepseek-ai/dsh/lib/bin.js')
    for candidate in candidates:
        if candidate.is_file():
            package = read(candidate.parent.parent / 'package.json')
            if package.get('name') != '@deepseek-ai/dsh' or package['version'] != DSH_VERSION:
                raise RuntimeError(f'This adapter targets DSH {DSH_VERSION}; found {package.get("version")}. '
                                   'Use the documented version or update/review this adapter first.')
            return candidate.resolve()
    raise RuntimeError('DSH entry point not found. Install @deepseek-ai/dsh@' + DSH_VERSION +
                       ', or supply --dsh-bin with the full path to its lib/bin.js.')


def restricted(image, name):
    return ['run', '--rm', '-i', '--name', name, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '64',
            '--memory', '512m', '--cpus', '1', '--user', '1000:1000',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777', image]


def remove_container(docker, name):
    # Names are generated here, never supplied by a model. No filesystem deletion.
    with contextlib.suppress(RuntimeError, subprocess.TimeoutExpired):
        execute([docker, 'rm', '-f', name], timeout=15)


class Gateway:
    """Loopback-only provider bridge; fixes options and limits model requests.

    The agent's container has no network, including access to this bridge.
    This also refuses any composition advertising unexpected tools.
    """
    def __init__(self, alias, options, thinking, args, directory):
        self.calls = 0
        self.stop_reason = None
        self.lock = threading.Lock()
        self.connections = set()
        self.key = uuid.uuid4().hex
        self.deadline = time.monotonic() + args.seconds
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != '/v1/chat/completions' or self.headers.get('Authorization') != 'Bearer ' + outer.key:
                    self.send_error(403)
                    return
                upstream = None
                response_started = False
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2_000_000:
                        raise ValueError('Invalid request size')
                    body = json.loads(self.rfile.read(length))
                    names = {t.get('function', {}).get('name') for t in body.get('tools', [])}
                    if names != {'bash', 'submit'}:
                        outer.stop_reason = 'unexpected_tools'
                        raise ValueError('Refusing tool roster: ' + str(names))
                    with outer.lock:
                        if outer.calls >= args.max_steps or time.monotonic() >= outer.deadline:
                            outer.stop_reason = 'model_request_budget'
                            raise ValueError('Model request/time budget exhausted')
                        outer.calls += 1
                        index = outer.calls
                    body.update(model=alias, temperature=options['temperature'], top_p=options['top_p'],
                                seed=options['seed'], max_tokens=options['num_predict'], stream=True)
                    body.pop('max_completion_tokens', None)
                    if thinking is not None:
                        body['reasoning_effort'] = 'high' if thinking else 'none'
                    else:
                        body.pop('reasoning_effort', None)
                    body['stream_options'] = {'include_usage': True}
                    bench.dump(directory / f'provider-request-{index:03}.json', body)
                    address = urlsplit(bench.ollama_url())
                    connection_type = http.client.HTTPSConnection if address.scheme == 'https' else http.client.HTTPConnection
                    upstream = connection_type(address.hostname, address.port,
                               timeout=max(1, min(args.idle_timeout, outer.deadline-time.monotonic())))
                    with outer.lock:
                        outer.connections.add(upstream)
                    upstream.connect()
                    if time.monotonic() >= outer.deadline:
                        raise TimeoutError('Session stopped before request started')
                    upstream.request('POST', address.path.rstrip('/') + '/v1/chat/completions',
                                     body=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                    with upstream.getresponse() as response:
                        if response.status != 200:
                            raise RuntimeError(f'Ollama HTTP {response.status}: ' + response.read(4000).decode(errors='replace'))
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.end_headers()
                        response_started = True
                        with (directory / f'provider-stream-{index:03}.jsonl').open('wb') as log:
                            for line in response:
                                if time.monotonic() >= outer.deadline:
                                    outer.stop_reason = 'time_budget'
                                    break
                                log.write(line)
                                log.flush()
                                self.wfile.write(line)
                                self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as error:
                    with outer.lock:
                        with (directory / 'provider-errors.jsonl').open('a', encoding='utf-8') as log:
                            log.write(json.dumps({'at': now(), 'error': str(error)}) + '\n')
                    with contextlib.suppress(OSError):
                        if not response_started:
                            self.send_error(502, 'Provider request failed; see provider-errors.jsonl')
                finally:
                    if upstream:
                        with outer.lock:
                            outer.connections.discard(upstream)
                        upstream.close()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.deadline = 0
        with self.lock:
            for upstream in self.connections:
                with contextlib.suppress(OSError):
                    if upstream.sock:
                        upstream.sock.shutdown(socket.SHUT_RDWR)
                    upstream.close()
            self.connections.clear()
        self.server.shutdown()
        self.server.server_close()


def patch_for(gateway, alias, options, thinking):
    profile = {'api': 'openai-completions', 'baseURL': gateway.url,
               'apiKeyEnv': 'OLLAMA_API_KEY',
               'compat': {'supportsStore': False, 'supportsDeveloperRole': False,
                          'supportsReasoningEffort': thinking is not None, 'maxTokensField': 'max_tokens'},
               'models': [{'id': alias, 'name': alias, 'contextWindow': options['num_ctx'],
                           'maxTokens': options['num_predict'], 'input': ['text'],
                           'reasoningEfforts': {'off': 'none', 'high': 'high'} if thinking is not None else False}]}
    # Fresh DSH_HOME + sdk-minimal avoids user settings, instructions and tools.
    disabled = ['persistent-bash', 'persistent-pwsh', 'terminal-bash', 'terminal-pwsh',
                'pty', 'subprocess', 'llm-deepseek']
    return ([{'id': row, 'disabled': True} for row in disabled] +
            [{'id': 'agent-loop', 'config': {'agents': [], 'maxParallelToolCalls': 1}},
             {'id': 'tools', 'config': {'mode': 'native'}},
             {'insert': [{'id': 'bench-tools', 'name': (SUPPORT / 'tools.mjs').as_uri()},
                         {'id': 'llm-pi-ai', 'name': '@deepseek-ai/dsh-llm-pi-ai',
                          'config': {'providers': {'ollama-bench': profile}}}]}])


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        with contextlib.suppress(Exception):
            execute(['taskkill', '/PID', str(process.pid), '/T', '/F'], timeout=15)
    else:
        process.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)


def session(args, model, task, directory, docker, binary, node, alias, options, thinking, image):
    token = uuid.uuid4().hex
    container, public = 'tsb-agent-' + token, 'tsb-public-' + token
    snapshots = directory / 'submissions'
    snapshots.mkdir(parents=True, exist_ok=True)
    prompt = (task['prompt'] + '\n\nTool-call budget: ' + str(args.max_tool_calls) +
              '. Total session deadline: ' + str(args.seconds) + ' seconds.\n' + SYSTEM)
    bench.dump(directory / 'request.json', {'backend': 'dsh', 'model': model['name'],
               'prompt': prompt, 'public_checks': task['tests'][:1], 'options': options, 'thinking': thinking})
    started = time.perf_counter()
    process = gateway = None
    stop = 'startup_error'
    steps = 0
    error = ''
    try:
        # No bind mounts. Populate only this public payload through stdin.
        run_args = restricted(image, container)
        run_args.insert(1, '-d')
        run_args[-1:-1] = ['--tmpfs', '/workspace:rw,nosuid,nodev,size=64m,mode=1777,uid=1000,gid=1000']
        execute([docker, *run_args])
        files = {'TASK.md': prompt, 'solution.ts': 'export {};\n',
                 'public-checks.json': json.dumps(task['tests'][:1], indent=2)}
        populate = ("let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>{"
                    "for(const [n,v] of Object.entries(JSON.parse(s)))require('fs').writeFileSync('/workspace/'+n,v)})")
        execute([docker, 'exec', '-i', container, '/usr/local/bin/node', '-e', populate], data=json.dumps(files))
        with tempfile.TemporaryDirectory(prefix='tsb-dsh-', ignore_cleanup_errors=True) as isolated:
            isolated = Path(isolated)
            home, cwd = isolated / 'home', isolated / 'cwd'
            home.mkdir()
            cwd.mkdir()
            config = {'docker': docker, 'container': container, 'publicContainer': public,
                      'image': image, 'log': str(directory / 'tool-events.jsonl'),
                      'snapshots': str(snapshots), 'maxCalls': args.max_tool_calls,
                      'deadline': (time.time() + args.seconds - (time.perf_counter() - started)) * 1000,
                      'publicTests': task['tests'][:1]}
            bench.dump(isolated / 'tools.json', config)
            gateway = Gateway(alias, options, thinking, args, directory)
            gateway.deadline -= time.perf_counter() - started
            bench.dump(isolated / 'patch.json', patch_for(gateway, alias, options, thinking))
            # Whitelist OS necessities; discard ambient Node options, DSH patches and API keys.
            env = {k: v for k, v in os.environ.items() if k.upper() in
                   {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
                    'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'USERPROFILE', 'HOME'}}
            env.update(DSH_HOME=str(home), DSH_SYSTEM_PROMPT=SYSTEM, OLLAMA_API_KEY=gateway.key,
                       BENCH_DSH_BIN=str(binary), BENCH_TOOL_CONFIG=str(isolated / 'tools.json'))
            messages = queue.Queue()
            with (directory / 'dsh-stderr.log').open('w', encoding='utf-8') as stderr, \
                 (directory / 'dsh-events.jsonl').open('w', encoding='utf-8') as events:
                process = subprocess.Popen([node, str(binary), '--profile', 'sdk-minimal', '--patch', str(isolated / 'patch.json')],
                          cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                          text=True, encoding='utf-8', errors='replace', bufsize=1,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

                def consume():
                    try:
                        for line in process.stdout:
                            messages.put(line)
                    finally:
                        messages.put(None)

                threading.Thread(target=consume, daemon=True).start()

                def send(identifier, method, params):
                    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': identifier,
                                                    'method': method, 'params': params}) + '\n')
                    process.stdin.flush()

                init = {'cwd': str(cwd), 'provider': 'ollama-bench', 'model': alias,
                        'maxTokens': options['num_predict']}
                if thinking is not None:
                    init['reasoningEffort'] = 'high' if thinking else 'off'
                send(1, 'initialize', init)
                prompted = False
                heartbeat = 0
                stop = 'process_exit'
                while True:
                    elapsed = time.perf_counter() - started
                    if elapsed >= args.seconds or gateway.stop_reason:
                        stop = gateway.stop_reason or 'time_budget'
                        break
                    if elapsed - heartbeat >= args.heartbeat:
                        print(f'  DSH {elapsed:.0f}s | {gateway.calls}/{args.max_steps} model requests | '
                              f'{len(list(snapshots.glob("*.ts")))} submissions', flush=True)
                        heartbeat = elapsed
                    try:
                        line = messages.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if line is None:
                        error = 'DSH exited before turn/end. See dsh-stderr.log.'
                        break
                    events.write(line)
                    events.flush()
                    try:
                        item = json.loads(line)
                    except ValueError:
                        raise RuntimeError('DSH stdout is not JSON-RPC. See dsh-events.jsonl.')
                    if item.get('error'):
                        raise RuntimeError('DSH RPC error: ' + json.dumps(item['error']))
                    if item.get('id') == 1 and not prompted:
                        if item.get('result', {}).get('serverInfo', {}).get('name') != 'deepseek-harness-sdk-runtime':
                            raise RuntimeError('Unexpected DSH SDK handshake')
                        send(2, 'session/prompt', {'sessionId': token, 'contentBlocks': [{'type': 'text', 'text': prompt}]})
                        prompted = True
                    params = item.get('params', {})
                    if item.get('method') != 'session.event' or params.get('sessionId') != token:
                        continue
                    event = params.get('event', {})
                    if event.get('type') == 'step/start':
                        steps += 1
                    if event.get('type') == 'tool/call':
                        print('  tool: ' + str(event.get('data', {}).get('name', '?')), flush=True)
                    if event.get('type') == 'turn/end':
                        reason = event.get('data', {}).get('reason', {})
                        stop = reason.get('kind', 'turn_ended') if isinstance(reason, dict) else str(reason)
                        break
                stop_process(process)
    except KeyboardInterrupt:
        stop = 'interrupted'
    except Exception as exc:
        error = str(exc)
        stop = 'runner_error'
    finally:
        if process:
            stop_process(process)
        if gateway:
            gateway.close()
        # ALL tools and agent processes lose access before private checks arrive.
        remove_container(docker, container)
        remove_container(docker, public)
    return {'wall_s': time.perf_counter() - started, 'wall_time_kind': 'agent_session',
            'agent_stop_reason': stop, 'agent_error': error, 'agent_steps': steps,
            'model_requests': gateway.calls if gateway else 0, 'tokens_s': None,
            'usage_scope': 'completed provider responses only; interrupted responses may be missing'}


def grade(docker, image, task, source):
    name = 'tsb-grade-' + uuid.uuid4().hex
    try:
        output = execute([docker, *restricted(image, name), '/usr/local/bin/node', '/opt/bench/grade.cjs'],
                         data=json.dumps({'source': source, 'types': task['types'], 'tests': task['tests']}), timeout=75)
        return json.loads(output)
    finally:
        remove_container(docker, name)


def usage(directory):
    total = {'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens': 0,
             'usage_responses': 0, 'reasoning_usage_responses': 0}
    for path in directory.glob('provider-stream-*.jsonl'):
        last = None
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.startswith('data: '):
                with contextlib.suppress(ValueError):
                    last = json.loads(line[6:]).get('usage') or last
        if last:
            total['usage_responses'] += 1
            total['input_tokens'] += last.get('prompt_tokens', 0)
            total['output_tokens'] += last.get('completion_tokens', 0)
            reasoning = (last.get('completion_tokens_details') or {}).get('reasoning_tokens')
            if reasoning is not None:
                total['reasoning_tokens'] += reasoning
                total['reasoning_usage_responses'] += 1
    total['eval_count'] = total['output_tokens'] if total['usage_responses'] else None
    if not total['usage_responses']:
        total['input_tokens'] = total['output_tokens'] = None
    if not total['reasoning_usage_responses']:
        total['reasoning_tokens'] = None
    return total


def tool_count(directory):
    path = directory / 'tool-events.jsonl'
    count = 0
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            with contextlib.suppress(ValueError):
                count += json.loads(line).get('type') == 'tool_start'
    return count


def publish(out):
    # Existing dashboard consumes the same result schema. No benchmark execution.
    from dashboard import dashboard
    dashboard(out.parent)
    rows = [read(p) for p in out.glob('answers/*/result.json')]
    payload = json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c')
    page = ('<!doctype html><meta charset="utf-8"><title>DSH benchmark</title>'
            '<style>body{background:#10151f;color:#e4eaf3;font:16px system-ui;padding:2rem}'
            'a{color:#81ded0}pre{white-space:pre-wrap}</style><h1>DSH benchmark</h1>'
            '<p>Private grading after tool-assisted public-feedback sessions. '
            'First and final submission scores are recorded separately.</p>'
            '<p><a href="http://127.0.0.1:8765">Interactive viewer</a> · '
            '<a href="../index.html">All runs</a></p><pre id="results"></pre>'
            '<script>document.getElementById("results").textContent=JSON.stringify(' + payload + ',null,2)</script>')
    (out / 'report.html').write_text(page, encoding='utf-8')


def run(args):
    models = bench.selected(args)
    tasks = bench.suite_tasks(args.suite)
    if args.tasks:
        wanted = set(args.tasks.split(','))
        if wanted - {t['id'] for t in tasks}:
            raise RuntimeError('Unknown task IDs: ' + ', '.join(sorted(wanted - {t['id'] for t in tasks})))
        tasks = [t for t in tasks if t['id'] in wanted]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run):
        raise RuntimeError('Use a simple run name containing letters, digits, dots, underscores or hyphens.')
    binary = dsh_bin(args.dsh_bin)
    docker, node = shutil.which('docker'), shutil.which('node')
    if not docker or not node:
        raise RuntimeError('Docker CLI and Node.js must be installed and on PATH.')
    try:
        if execute([docker, 'info', '--format', '{{.OSType}}'], timeout=15).strip() != 'linux':
            raise RuntimeError('Docker must use Linux containers.')
        image = execute([docker, 'image', 'inspect', '--format', '{{.Id}}', IMAGE], timeout=15).strip()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Start Docker Desktop with Linux containers, then run '
                           '"python dsh_bench.py build" once.\n' + str(exc)) from None
    out = ROOT / 'runs' / args.run
    options = bench.generation_options(args)
    config = {'backend': 'dsh', 'suite': args.suite, 'models': [m['name'] for m in models],
              'tasks': [t['id'] for t in tasks], 'repeats': args.repeats, 'options': options,
              'thinking': args.thinking, 'dsh_version': DSH_VERSION, 'sandbox_image': image,
              'seconds': args.seconds, 'max_tool_calls': args.max_tool_calls, 'max_steps': args.max_steps,
              'idle_timeout': args.idle_timeout, 'public_check_groups': 1,
              'suite_hash': hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest(),
              'harness_hash': hashlib.sha256(Path(__file__).read_bytes() + b''.join(
                  p.read_bytes() for p in sorted(SUPPORT.iterdir()) if p.suffix in {'.cjs', '.mjs'})).hexdigest()}
    (ROOT / 'runs').mkdir(exist_ok=True)
    lock = ROOT / 'runs/active.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('Another benchmark holds runs/active.lock. Stop it before using the DSH runner.') from None
    with os.fdopen(fd, 'w') as stream:
        stream.write(json.dumps({'pid': os.getpid(), 'run': args.run, 'backend': 'dsh'}))
    segment_start = time.perf_counter()
    segment_created = now()
    manifest_ready = False
    timing = None

    def save_timing(active):
        if timing is None:
            return
        timing['segments'][-1].update(updated=now(), seconds=time.perf_counter()-segment_start, active=active)
        timing['total_suite_s'] = sum(s['seconds'] for s in timing['segments'])
        bench.dump(out / 'timing.json', timing)

    try:
        if (out / 'manifest.json').exists():
            manifest = read(out / 'manifest.json')
            if manifest['config'] != config:
                raise RuntimeError('Run configuration changed. Use a new --run name; saved runs remain in the viewer.')
        else:
            manifest = {'created': now(), 'config': config, 'hardware': {
                'platform': sys.platform, 'ollama': bench.request('version'),
                'client_flash_attention': os.environ.get('OLLAMA_FLASH_ATTENTION'),
                'client_kv_cache_type': os.environ.get('OLLAMA_KV_CACHE_TYPE'),
                'server_settings_verified': False}}
            bench.dump(out / 'manifest.json', manifest)
        manifest_ready = True
        timing = read(out / 'timing.json') if (out / 'timing.json').exists() else {'segments': []}
        timing['segments'].append({'started': segment_created})
        timing['scope'] = 'Active runner segments, including model setup/downloads, DSH, grading and reports; excludes pauses between invocations. Updated after each task and on exit; a hard kill loses time since the last update.'
        save_timing(True)
        for model in models:
            try:
                pending = [(task, repeat) for task in tasks for repeat in range(args.repeats)
                           if not (out / 'answers' / f'{bench.slug(model["name"])}--{task["id"]}--{repeat}' / 'result.json').exists()]
                if not pending:
                    print('Already complete: ' + model['name'], flush=True)
                    continue
                if args.pull:
                    bench.pull(model)
                info = bench.request('show', {'model': model['name']})
                if 'tools' not in info.get('capabilities', []):
                    raise RuntimeError('Model does not advertise tool support. Direct coding runs are still supported.')
                thinking = (args.thinking == 'on' or (args.thinking == 'auto' and model.get('thinking', False)))
                if thinking and 'thinking' not in info.get('capabilities', []):
                    raise RuntimeError('Thinking requested, but model does not advertise thinking support.')
                if 'thinking' not in info.get('capabilities', []):
                    thinking = None
                tags = bench.request('tags')['models']
                digest = next((t.get('digest') for t in tags if t['name'] == model['name']), None)
                if not digest:
                    raise RuntimeError('Cannot determine installed model digest.')
                saved = [read(p) for p in out.glob('answers/*/result.json')]
                if any(r['model'] == model['name'] and r.get('model_digest') != digest for r in saved):
                    raise RuntimeError('Model digest changed during this run. Use a new run name.')
                alias = 'tsb-dsh-' + hashlib.sha256(json.dumps([digest, options], sort_keys=True).encode()).hexdigest()[:16]
                bench.request('create', {'model': alias, 'from': model['name'], 'parameters': options, 'stream': False}, timeout=300)
                (out / 'errors' / (bench.slug(model['name']) + '.json')).unlink(missing_ok=True)
            except (RuntimeError, OSError, ValueError) as exc:
                bench.dump(out / 'errors' / (bench.slug(model['name']) + '.json'), {'model': model['name'], 'error': str(exc), 'at': now()})
                print('MODEL SETUP ERROR ' + model['name'] + ': ' + str(exc), flush=True)
                publish(out)
                continue
            for task, repeat in pending:
                directory = out / 'answers' / f'{bench.slug(model["name"])}--{task["id"]}--{repeat}'
                if directory.exists():
                    # Retain incomplete artifacts; do not accidentally score a previous checkpoint.
                    archive = out / 'incomplete' / (directory.name + '-' + uuid.uuid4().hex[:8])
                    archive.parent.mkdir(exist_ok=True)
                    directory.rename(archive)
                directory.mkdir(parents=True)
                print(f'\n{model["name"]} | {task["id"]} | repeat {repeat + 1}', flush=True)
                attempt_start = time.perf_counter()
                metrics = session(args, model, task, directory, docker, binary, node, alias, options, thinking, image)
                submissions = sorted((directory / 'submissions').glob('*.ts'))
                result = {'compiled': False, 'types_pass': None, 'checks': [], 'passed': False, 'status': 'no_submission'}
                first = None
                grading_start = time.perf_counter()
                try:
                    if submissions:
                        print('  Agent stopped. Grading saved submissions privately.', flush=True)
                        first_source = submissions[0].read_text(encoding='utf-8')
                        source = submissions[-1].read_text(encoding='utf-8')
                        (directory / 'first-solution.ts').write_text(first_source, encoding='utf-8')
                        (directory / 'solution.ts').write_text(source, encoding='utf-8')
                        first = grade(docker, image, task, first_source)
                        bench.dump(directory / 'first-result.json', first)
                        result = first.copy() if len(submissions) == 1 else grade(docker, image, task, source)
                    elif metrics['agent_stop_reason'] in {'runner_error', 'startup_error', 'unexpected_tools', 'process_exit'}:
                        result.update(status='harness_error', error=metrics['agent_error'] or metrics['agent_stop_reason'])
                except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                    result.update(status='harness_error', error=str(exc))
                result.update(model=model['name'], task=task['id'], category=task['category'], repeat=repeat,
                              total_checks=len(task['tests']), model_digest=digest, harness_hash=config['harness_hash'],
                              backend='dsh', submissions=len(submissions), repair_submissions=max(0, len(submissions)-1),
                              tool_calls=tool_count(directory),
                              first_passed=first.get('passed') if first else None, actual_thinking=thinking,
                              grading_wall_s=time.perf_counter()-grading_start, **metrics, **usage(directory))
                result['end_to_end_s'] = time.perf_counter() - attempt_start
                (directory / 'compile.log').write_text(result.pop('compile_log', ''), encoding='utf-8')
                bench.dump(directory / 'result.json', result)
                save_timing(True)
                publish(out)
                print(f'  {result["status"]} | first={result["first_passed"]} final={result["passed"]} '
                      f'| {result["wall_s"]:.1f}s | stop={result["agent_stop_reason"]}', flush=True)
                if metrics['agent_stop_reason'] == 'interrupted':
                    return
    finally:
        try:
            if manifest_ready:
                save_timing(False)
        finally:
            lock.unlink(missing_ok=True)
    print('Report: ' + str(out / 'report.html'), flush=True)


def main():
    defaults = read(ROOT / 'settings.json')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build', help='Build the isolated Node/TypeScript image; no models or tests run')
    p = sub.add_parser('run', help='Start model sessions and privately grade their submissions')
    p.add_argument('--suite', default='typescript', choices=['typescript'])
    p.add_argument('--run', required=True)
    p.add_argument('--models', help='Comma-separated names from models.json; default: all enabled models')
    p.set_defaults(profile='enabled')
    p.add_argument('--tasks', help='Comma-separated task IDs; default: entire suite')
    p.add_argument('--pull', action='store_true')
    p.add_argument('--dsh-bin')
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--thinking', choices=['on', 'off', 'auto'], default=defaults.get('thinking', 'off'))
    for name, fallback in [('context', 4096), ('tokens', 2048), ('seed', 42), ('top_k', 40)]:
        p.add_argument('--' + name.replace('_', '-'), type=int, default=defaults.get(name, fallback))
    for name, fallback in [('temperature', 0), ('top_p', .9), ('min_p', 0), ('repeat_penalty', 1.1)]:
        p.add_argument('--' + name.replace('_', '-'), type=float, default=defaults.get(name, fallback))
    p.add_argument('--seconds', type=int, default=600, help='Maximum task session wall seconds (includes DSH startup/public grading)')
    p.add_argument('--max-tool-calls', type=int, default=24)
    p.add_argument('--max-steps', type=int, default=12, help='Maximum provider requests, including retries')
    p.add_argument('--idle-timeout', type=int, default=120)
    p.add_argument('--heartbeat', type=int, default=5)
    args = parser.parse_args()
    if args.command == 'build':
        docker = shutil.which('docker')
        if not docker:
            parser.error('Docker CLI not found.')
        subprocess.run([docker, 'build', '-t', IMAGE, str(SUPPORT)], check=True)
        return
    for key in ('repeats', 'context', 'tokens', 'seconds', 'max_tool_calls', 'max_steps', 'idle_timeout', 'heartbeat'):
        if getattr(args, key) <= 0:
            parser.error(key + ' must be positive')
    if args.tokens >= args.context:
        parser.error('--tokens must be smaller than --context to leave room for the task and tools')
    if (not all(math.isfinite(getattr(args, k)) for k in ('temperature', 'top_p', 'min_p', 'repeat_penalty'))
            or not 0 <= args.temperature <= 2 or not 0 <= args.top_p <= 1 or not 0 <= args.min_p <= 1
            or args.top_k < 0 or args.repeat_penalty <= 0):
        parser.error('Invalid sampling settings: temperature 0..2, top-p/min-p 0..1, top-k >= 0, repeat-penalty > 0')
    try:
        run(args)
    except KeyboardInterrupt:
        print('\nStopped. Completed results remain saved. Rerun the same command to resume.', flush=True)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()
