"""Local Ollama TypeScript benchmark. Python standard library only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from tasks import TASKS
from progress import progress

ROOT = Path(__file__).resolve().parent
IDLE_TIMEOUT = 120
SYSTEM = """Implement the TypeScript coding task. Return one complete solution.ts file only, optionally inside one typescript code fence. Use the exact named exports requested. Target TypeScript 5.9 strict, ES2022, CommonJS. No imports, external packages, Node APIs, timers, I/O, or compiler suppression comments. Standard ECMAScript objects and Promise are available. Do not include tests or explanations."""

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)

class OllamaConnectionError(RuntimeError):
    """An actionable transport error, separate from model/test failures."""

def ollama_url():
    host=os.environ.get('OLLAMA_HOST','').strip() or 'http://127.0.0.1:11434'
    if '://' not in host:
        host='http://'+host
    return host.rstrip('/')

def api(endpoint, body=None, timeout=None):
    url=ollama_url() + '/api/' + endpoint
    req = urllib.request.Request(url,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=IDLE_TIMEOUT if timeout is None else timeout)
    except urllib.error.HTTPError as e:
        detail=e.read(4096).decode('utf-8',errors='replace')
        raise OllamaConnectionError(f'Ollama returned HTTP {e.code} for {url}: {detail}') from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise OllamaConnectionError(
            f'Cannot connect to Ollama at {url}.\n'
            f'Detail: {getattr(e,"reason",e)}\n'
            'Start the Ollama app, or run "ollama serve" in another terminal and leave it open.\n'
            'If you use a different server, set $env:OLLAMA_HOST to its full URL.\n'
            'Then rerun the same benchmark command. Saved results are preserved.'
        ) from None

def request(endpoint, body=None, timeout=None):
    with progress(endpoint), api(endpoint, body, timeout) as response:
        return json.load(response)

def command(args, cwd=ROOT, timeout=30):
    return subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=timeout)

def extract(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    fence = chr(96)*3
    blocks = re.findall(r'^[ \t]*' + fence + r'(?:typescript|ts|javascript|js)?[ \t]*\n(.*?)^[ \t]*' + fence, text, re.M|re.S)
    return '\n'.join(blocks).strip() if blocks else text

def evaluate(task, source, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'solution.ts').write_text(source, encoding='utf-8')
    (directory/'typechecks.ts').write_text(task['types'], encoding='utf-8')
    dump(directory/'checks.json', task['tests'])
    result = dict(compiled=False, types_pass=None, checks=[], passed=False)
    if re.search(r'@ts-(?:nocheck|ignore|expect-error)|///\s*<reference', source):
        return {**result, 'status':'invalid_output', 'error':'Compiler suppression/reference directives are forbidden.'}
    flags = ['--strict','--target','ES2022','--module','commonjs','--lib','ES2022','--skipLibCheck','--noEmitOnError','--pretty','false']
    try:
        c = command(['node',ROOT/'node_modules/typescript/bin/tsc',*flags,'solution.ts'], directory)
        (directory/'compile.log').write_text(c.stdout+c.stderr, encoding='utf-8')
        if c.returncode:
            return {**result,'status':'compile_error','error':(c.stdout+c.stderr)[-8000:]}
        result['compiled'] = True
        if task['types']:
            c = command(['node',ROOT/'node_modules/typescript/bin/tsc',*flags,'--noEmit','solution.ts','typechecks.ts'], directory)
            result['types_pass'] = c.returncode == 0
            result['type_error'] = (c.stdout+c.stderr)[-8000:]
        c = command(['node','--permission',f'--allow-fs-read={directory}',f'--allow-fs-read={ROOT/"evaluate.cjs"}',
            '--max-old-space-size=128',ROOT/'evaluate.cjs',directory/'solution.js',directory/'checks.json'], directory, 12)
        if c.returncode:
            return {**result,'status':'runtime_error','error':(c.stdout+c.stderr)[-8000:]}
        if not c.stdout.strip():
            return {**result,'status':'runtime_error','error':'Evaluator ended without results; possibly an unresolved promise.'}
        checks = json.loads(c.stdout)
        if not isinstance(checks,list) or len(checks)!=len(task['tests']):
            raise ValueError('Invalid evaluator response')
        result['checks'] = checks
        result['passed'] = all(x.get('pass') is True for x in checks) and result['types_pass'] is not False
        result['status'] = 'pass' if result['passed'] else 'test_failure'
        return result
    except subprocess.TimeoutExpired:
        return {**result,'status':'execution_timeout','error':'Compiler or candidate exceeded time limit.'}
    except (ValueError,OSError) as e:
        return {**result,'status':'harness_error','error':str(e)}

def generate(model, task, options, thinking, directory):
    body = {'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':task['prompt']}],
            'stream':True,'keep_alive':'10m','options':options}
    if thinking is not None:
        body['think'] = thinking
    dump(directory/'request.json', body)
    start = time.perf_counter()
    first = first_content = None
    content, reasoning = [], []
    final = None
    chunks = chars = thought_chars = 0
    with progress('generating') as update, api('chat',body) as response, (directory/'stream.jsonl').open('w',encoding='utf-8') as stream:
        for line in response:
            if not line.strip():
                continue
            event=json.loads(line)
            stream.write(json.dumps(event,ensure_ascii=False)+'\n')
            stream.flush()
            if event.get('error'):
                raise RuntimeError(event['error'])
            message=event.get('message',{})
            chunks += 1
            chars += len(message.get('content',''))
            thought_chars += len(message.get('thinking',''))
            update(f'{chunks} chunks | {chars} answer chars | {thought_chars} thinking chars')
            elapsed=time.perf_counter()-start
            if first is None and (message.get('content') or message.get('thinking')):
                first=elapsed
            if message.get('content'):
                if first_content is None:
                    first_content=elapsed
                content.append(message['content'])
            reasoning.append(message.get('thinking',''))
            if event.get('done'):
                final=event
    if final is None:
        raise RuntimeError('Ollama stream ended without a final metrics event')
    answer=''.join(content)
    (directory/'answer.txt').write_text(answer,encoding='utf-8')
    (directory/'thinking.txt').write_text(''.join(reasoning),encoding='utf-8')
    metrics={k:final.get(k) for k in ['eval_count','eval_duration','prompt_eval_count','prompt_eval_duration','load_duration','total_duration','done_reason']}
    metrics.update(wall_s=time.perf_counter()-start,ttft_s=first,first_code_s=first_content)
    metrics['tokens_s']=(final.get('eval_count',0)*1e9/final['eval_duration']) if final.get('eval_duration') else None
    metrics['prompt_tokens_s']=(final.get('prompt_eval_count',0)*1e9/final['prompt_eval_duration']) if final.get('prompt_eval_duration') else None
    return answer,metrics

def selected(args):
    catalog=json.loads((ROOT/'models.json').read_text(encoding='utf-8'))
    known={m['name']:m for m in catalog}
    if len(known)!=len(catalog):
        raise SystemExit('Duplicate model names in models.json')
    if args.models is not None:
        names=list(dict.fromkeys(n.strip() for n in args.models.split(',') if n.strip()))
        unknown=set(names)-known.keys()
        if unknown:
            raise SystemExit('Unknown models: '+', '.join(sorted(unknown))+'. Add them to models.json first.')
        chosen=[known[n] for n in names]
    elif args.profile == 'enabled':
        chosen=[m for m in catalog if m.get('enabled') is True]
    else:
        groups={'core'} if args.profile=='core' else {'core','extended','borderline'}
        if args.profile=='offload':
            groups.add('cpu-offload')
        chosen=[m for m in catalog if m['group'] in groups]
    if not chosen:
        raise SystemExit('No models selected. Set enabled: true in models.json or provide --models.')
    return chosen

def suite_tasks(name):
    suites=json.loads((ROOT/'suites.json').read_text(encoding='utf-8'))
    if name not in suites:
        raise SystemExit(f'Unknown suite: {name}')
    suite=suites[name]
    if not suite['enabled']:
        raise SystemExit(f"Suite {name} is inactive. {suite.get('reason','')}")
    if suite['runner']!='typescript':
        raise SystemExit(f'No implemented runner for suite {name}. Enabling a flag alone does not implement it.')
    return TASKS

def generation_options(args):
    return {'temperature':args.temperature,'seed':args.seed,'num_ctx':args.context,'num_predict':args.tokens,
            'top_p':args.top_p,'top_k':args.top_k,'min_p':args.min_p,'repeat_penalty':args.repeat_penalty}

def pull(model):
    name=model['name']
    installed={m['name'] for m in request('tags')['models']}
    if name in installed:
        print('Already installed:',name,flush=True)
        return
    model_dir=Path(os.environ.get('OLLAMA_MODELS',str(Path.home()/'.ollama/models')))
    probe=model_dir
    while not probe.exists() and probe!=probe.parent:
        probe=probe.parent
    free=shutil.disk_usage(probe).free/1e9
    if model['gb'] and free<model['gb']*1.2+5:
        raise RuntimeError(f'Insufficient estimated free disk: {free:.1f} GB on {probe}')
    print('Pulling:',name,flush=True)
    last=0
    with progress('download '+name) as update, api('pull',{'model':name,'stream':True}) as response:
        for line in response:
            e=json.loads(line)
            if e.get('error'):
                raise RuntimeError(e['error'])
            update(e.get('status','') + (f" {e.get('completed',0)/1e9:.2f}/{e['total']/1e9:.2f} GB" if e.get('total') else ''))
            if time.monotonic()-last>15 or e.get('status')=='success':
                percent_text=f" {100*e.get('completed',0)/e['total']:.0f}%" if e.get('total') else ''
                print(name,e.get('status',''),percent_text,flush=True)
                last=time.monotonic()

def doctor():
    data={'platform':platform.platform(),'processor':platform.processor(),'python':sys.version,
          'disk_free_gb':round(shutil.disk_usage(ROOT).free/1e9,1),
          'client_ollama_environment':{k:os.environ.get(k) for k in
              ['OLLAMA_HOST','OLLAMA_FLASH_ATTENTION','OLLAMA_KV_CACHE_TYPE','OLLAMA_NUM_PARALLEL']},
          'server_attention_note':'Client environment is not proof of the server configuration; consult Ollama server logs.'}
    for label,cmd in [('node',['node','--version']),('gpu',['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'])]:
        try:
            data[label]=command(cmd).stdout.strip()
        except OSError as e:
            data[label]=str(e)
    data['ollama']=request('version')
    data['installed']=request('tags')['models']
    return data

def selftest(suite):
    failures=[]
    for task in suite_tasks(suite):
        result=evaluate(task,task['reference'],ROOT/'runs/selftest'/task['id'])
        print(task['id'],result['status'],flush=True)
        if not result['passed']:
            failures.append((task['id'],result))
    task=TASKS[0]
    for name,source,expected in [
        ('syntax','export function !!!','compile_error'),
        ('wrong','export function groupBy<T>(x:readonly T[],f:(v:T)=>string):Record<string,T[]>{return {}}','test_failure'),
        ('suppression','// @ts-nocheck\nexport const x=1','invalid_output'),
        ('hang','export function groupBy<T>(x:readonly T[],f:(v:T)=>string):Record<string,T[]>{while(true){}}','test_failure'),
        ('broad','export function groupBy(x:any,f:any):any{return {}}','test_failure')]:
        result=evaluate(task,source,ROOT/'runs/selftest'/name)
        if result['status']!=expected or result['passed']:
            failures.append((name,result))
    if failures:
        print(json.dumps(failures,indent=2))
        raise SystemExit(1)
    print(f'All {len(TASKS)} references and 5 negative controls passed.')

def run(args):
    from report import report
    models=selected(args)
    available=suite_tasks(args.suite)
    tasks=available if not args.tasks else [t for t in available if t['id'] in args.tasks.split(',')]
    if args.tasks and len(tasks)!=len(set(args.tasks.split(','))):
        raise SystemExit('Unknown task ID; run python bench.py tasks')
    if not (ROOT/'node_modules/typescript/bin/tsc').exists():
        raise SystemExit('Run npm install first.')
    out=ROOT/'runs'/args.run
    out.mkdir(parents=True,exist_ok=True)
    lock=ROOT/'runs/active.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('Another run holds runs/active.lock. If its process is dead, remove that file before resuming.')
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    try:
        options=generation_options(args)
        config={'suite':args.suite,'backend':'ollama','models':[m['name'] for m in models],'tasks':[t['id'] for t in tasks],
            'options':options,'thinking':args.thinking,'repeats':args.repeats,
            'suite_hash':hashlib.sha256(json.dumps(TASKS,sort_keys=True).encode()).hexdigest(),
            'idle_timeout':args.idle_timeout,
            'harness_hash':hashlib.sha256((ROOT/'bench.py').read_bytes()+(ROOT/'evaluate.cjs').read_bytes()+(ROOT/'progress.py').read_bytes()+SYSTEM.encode()).hexdigest()}
        if (out/'manifest.json').exists():
            manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            if manifest['config']!=config:
                previous=manifest['config']
                changed={key for key in previous.keys()|config.keys() if previous.get(key)!=config.get(key)}
                if changed=={'harness_hash'} and args.resume_harness_change:
                    manifest.setdefault('harness_changes',[]).append({
                        'at':dt.datetime.now(dt.timezone.utc).isoformat(),
                        'previous_hash':previous['harness_hash'],'new_hash':config['harness_hash'],
                        'preserved_results':[str(p.relative_to(out)) for p in sorted(out.glob('answers/*/result.json'))]})
                    manifest['config']=config
                    dump(out/'manifest.json',manifest)
                    print('Resuming after acknowledged harness change; previous results retained and change recorded.',flush=True)
                else:
                    raise SystemExit('Run configuration changed: '+', '.join(sorted(changed))+
                        '. Use a new --run name, or --resume-harness-change for a harness-only fix.')
        else:
            manifest={'created':dt.datetime.now(dt.timezone.utc).isoformat(),'config':config,'hardware':doctor()}
            dump(out/'manifest.json',manifest)
        rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('answers/*/result.json'))]
        completed={(r['model'],r['task'],r['repeat']) for r in rows}
        total=len(models)*len(tasks)*args.repeats
        print(f'Suite: {args.suite} | selected models: {len(models)} | attempts: {total} | saved: {len(rows)}',flush=True)
        print('Models: '+', '.join(m['name'] for m in models),flush=True)
        print('Options: '+json.dumps(options)+f' | thinking: {args.thinking}',flush=True)
        print('Report: '+str(out/'report.html'),flush=True)
        report(out)
        for model in models:
            name=model['name']
            if all((name,t['id'],r) in completed for t in tasks for r in range(args.repeats)):
                continue
            if (out/'STOP').exists():
                break
            try:
                if args.pull:
                    pull(model)
                installed={m['name']:m for m in request('tags')['models']}
                if name not in installed:
                    raise RuntimeError('Model missing; use --pull')
                info=request('show',{'model':name})
                thinking=args.thinking=='on' if 'thinking' in info.get('capabilities',[]) else None
                if args.thinking=='on' and thinking is None:
                    raise RuntimeError('Model does not support thinking; use a separate non-thinking run')
                for resident in request('ps').get('models',[]):
                    request('generate',{'model':resident['name'],'keep_alive':0})
                warm={'model':name,'messages':[{'role':'user','content':'Return exactly: export const x = 1;'}],
                      'stream':False,'keep_alive':'10m','options':{**options,'num_predict':32}}
                if thinking is not None:
                    warm['think']=thinking
                print(f'Loading and warming {name}; this can be slower than subsequent tasks.',flush=True)
                warm_result=request('chat',warm)
                modelmeta={'installed':installed[name],'show':info,'warmup':warm_result,'resident':request('ps')}
                dump(out/'models'/f'{slug(name)}.json',modelmeta)
                (out/'errors'/f'{slug(name)}.json').unlink(missing_ok=True)
            except Exception as e:
                print('MODEL ERROR',name,str(e),flush=True)
                dump(out/'errors'/f'{slug(name)}.json',{'model':name,'error':str(e)})
                report(out)
                continue
            for repeat in range(args.repeats):
                for task in tasks:
                    if (out/'STOP').exists():
                        report(out)
                        return
                    if (name,task['id'],repeat) in completed:
                        continue
                    directory=out/'answers'/f'{slug(name)}--{task["id"]}--{repeat}'
                    directory.mkdir(parents=True,exist_ok=True)
                    row={'model':name,'task':task['id'],'category':task['category'],'repeat':repeat,
                         'harness_hash':config['harness_hash'],
                         'model_digest':installed[name]['digest'],'total_checks':len(task['tests']),'artifact':str(directory.relative_to(out).as_posix())}
                    print(f'[{len(rows)+1}/{total}] {name} | {task["id"]} | repeat {repeat+1}',flush=True)
                    try:
                        answer,metrics=generate(name,task,{**options,'seed':args.seed+repeat},thinking,directory)
                        row.update(metrics)
                        with progress('compile and check'):
                            row.update(evaluate(task,extract(answer),directory))
                        row['truncated']=metrics['done_reason']=='length'
                        if row['truncated']:
                            row.update(passed=False,status='truncated')
                    except Exception as e:
                        row.update(passed=False,compiled=False,status='model_error',error=str(e),checks=[])
                    dump(directory/'result.json',row)
                    rows.append(row)
                    report(out)
                    print(f'  {row["status"]}; {row.get("tokens_s",0) or 0:.1f} tokens/s; {row.get("wall_s",0):.1f}s',flush=True)
            request('generate',{'model':name,'keep_alive':0})
        report(out)
        print('Report:',out/'report.html',flush=True)
    finally:
        lock.unlink(missing_ok=True)

def slug(value):
    return re.sub(r'[^a-zA-Z0-9_.-]','_',value)

def main():
    defaults=json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('suites')
    sub.add_parser('dashboard',help='Build one HTML page from all saved runs; no tests or model calls')
    for name in ['selftest','tasks']:
        q=sub.add_parser(name)
        q.add_argument('--suite',default=defaults['suite'])
    for name in ['models','pull','run','dsh-export']:
        q=sub.add_parser(name)
        select=q.add_mutually_exclusive_group()
        select.add_argument('--profile',choices=['enabled','core','all','offload'],default='enabled')
        select.add_argument('--models',help='Comma-separated exact tags from models.json; overrides enabled flags')
        if name in ['run','dsh-export']:
            q.add_argument('--context',type=int,default=defaults['context'])
            q.add_argument('--tokens',type=int,default=defaults['tokens'])
            q.add_argument('--temperature',type=float,default=defaults['temperature'])
            q.add_argument('--top-p',type=float,default=defaults['top_p'])
            q.add_argument('--top-k',type=int,default=defaults['top_k'])
            q.add_argument('--min-p',type=float,default=defaults['min_p'])
            q.add_argument('--repeat-penalty',type=float,default=defaults['repeat_penalty'])
            q.add_argument('--seed',type=int,default=defaults['seed'])
            q.add_argument('--thinking',choices=['off','on'],default=defaults['thinking'])
        if name=='run':
            q.add_argument('--run',default='typescript-selected')
            q.add_argument('--suite',default=defaults['suite'])
            q.add_argument('--pull',action='store_true')
            q.add_argument('--resume-harness-change',action='store_true',
                           help='Acknowledge a harness-only code fix on resume; record history and retain saved results')
            q.add_argument('--tasks')
            q.add_argument('--repeats',type=int,default=defaults['repeats'])
            q.add_argument('--heartbeat',type=float,default=defaults['heartbeat'])
            q.add_argument('--idle-timeout',type=float,default=defaults['idle_timeout'])
            q.add_argument('--dry-run',action='store_true',help='Show plan without contacting Ollama or executing tests')
        if name=='dsh-export':
            q.add_argument('--export',default='local-dsh')
            q.add_argument('--flash-attention',choices=['on','off'],default='on' if defaults['flash_attention'] else 'off')
            q.add_argument('--kv-cache-type',choices=['f16','q8_0','q4_0'],default=defaults['kv_cache_type'])
    q=sub.add_parser('report');q.add_argument('--run',default='typescript-selected')
    args=p.parse_args()
    if args.command in ['run','report'] and not re.fullmatch(r'[A-Za-z0-9_-]+',args.run):
        p.error('--run accepts only letters, numbers, underscores and hyphens')
    if args.command in ['run','dsh-export']:
        if args.context<512 or args.tokens<1 or args.tokens>=args.context:
            p.error('context must be >=512 and 0 < tokens < context (leave room for the prompt)')
        if not 0<=args.temperature<=2 or not 0<args.top_p<=1 or not 0<=args.min_p<=1 or args.top_k<1 or not 0<args.repeat_penalty<=10:
            p.error('Invalid sampling settings: temperature 0..2, top-p (0,1], min-p 0..1, top-k >=1, repeat-penalty (0,10]')
    if args.command=='doctor':
        print(json.dumps(doctor(),indent=2,ensure_ascii=False))
    elif args.command=='dashboard':
        from dashboard import dashboard
        print(dashboard(ROOT/'runs'))
    elif args.command=='suites':
        print((ROOT/'suites.json').read_text(encoding='utf-8'))
    elif args.command=='tasks':
        for t in suite_tasks(args.suite):
            print(t['id'],t['category'])
    elif args.command=='selftest':
        selftest(args.suite)
    elif args.command=='models':
        models=selected(args)
        print(json.dumps(models,indent=2))
        print(f'{len(models)} models; estimated total {sum(m["gb"] or 0 for m in models):.1f} GB (shared layers can reduce this).')
    elif args.command=='pull':
        failed=[]
        for m in selected(args):
            try:
                pull(m)
            except Exception as e:
                failed.append(m['name']);print('ERROR',m['name'],str(e),flush=True)
        if failed:
            raise SystemExit(1)
    elif args.command=='run':
        if args.repeats<1 or args.heartbeat<1 or args.idle_timeout<1:
            p.error('repeats >=1, heartbeat >=1s, idle-timeout >=1s required')
        import progress as progress_module
        progress_module.INTERVAL=args.heartbeat
        global IDLE_TIMEOUT
        IDLE_TIMEOUT=args.idle_timeout
        if args.dry_run:
            tasks=suite_tasks(args.suite)
            if args.tasks:
                names=set(args.tasks.split(','))
                if names-{t['id'] for t in tasks}:
                    p.error('Unknown task ID')
                tasks=[t for t in tasks if t['id'] in names]
            print(json.dumps({'suite':args.suite,'models':[m['name'] for m in selected(args)],
                'tasks':[t['id'] for t in tasks],'options':generation_options(args),'thinking':args.thinking,
                'repeats':args.repeats,'pull':args.pull,'report':str(ROOT/'runs'/args.run/'report.html')},indent=2))
        else:
            run(args)
    elif args.command=='dsh-export':
        from dsh_export import export
        export(args,selected(args),generation_options(args))
    elif args.command=='report':
        from report import report
        print(report(ROOT/'runs'/args.run))

if __name__=='__main__':
    try:
        main()
    except OllamaConnectionError as e:
        print(f'\nERROR: {e}',file=sys.stderr,flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrupted. Saved results are preserved.',file=sys.stderr,flush=True)
        sys.exit(130)
