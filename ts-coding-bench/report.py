"""Build a standalone, offline HTML report and CSV from recorded task results."""
import csv
import json
from pathlib import Path
import statistics

def report(out):
    out=Path(out)
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('answers/*/result.json'))]
    errors=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('errors/*.json'))]
    summaries=[]
    expected=len(manifest['config']['tasks'])*manifest['config']['repeats']
    for model in manifest['config']['models']:
        results=[r for r in rows if r['model']==model]
        def median(key):
            values=[r[key] for r in results if r.get(key) is not None]
            return round(statistics.median(values),2) if values else None
        summaries.append(dict(model=model,completed=len(results),expected=expected,
            passed=sum(r['passed'] for r in results),compiled=sum(r.get('compiled',False) for r in results),
            checks=sum(sum(c['pass'] for c in r.get('checks',[])) for r in results),
            total_checks=sum(r['total_checks'] for r in results),
            tokens_s=median('tokens_s'),ttft_s=median('ttft_s'),wall_s=median('wall_s')))
    summaries.sort(key=lambda s:(s['completed']==expected,s['passed'],s['tokens_s'] or 0),reverse=True)
    with (out/'results.csv').open('w',newline='',encoding='utf-8') as f:
        keys=['model','task','repeat','status','passed','compiled','types_pass','tokens_s','ttft_s','first_code_s','wall_s','eval_count','done_reason','model_digest']
        w=csv.DictWriter(f,keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    payload={'manifest':manifest,'summaries':summaries,'rows':rows,'errors':errors}
    data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    page=TEMPLATE.replace('__DATA__',data)
    tmp=out/'report.tmp.html'
    tmp.write_text(page,encoding='utf-8');tmp.replace(out/'report.html')
    from dashboard import dashboard
    try:
        dashboard(out.parent)
    except (OSError,ValueError) as error:
        print(f'Dashboard update failed: {error}. Rebuild later with python bench.py dashboard.',flush=True)
    return out/'report.html'

TEMPLATE='''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TypeScript coding benchmark</title>
<style>
:root{color-scheme:dark;font-family:system-ui;background:#10151f;color:#e4eaf3}
body{max-width:1400px;margin:36px auto;padding:0 24px}h1{font-size:32px;margin-bottom:6px}
p{color:#aebbd0;line-height:1.6}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{background:#1a2433;padding:20px;border-radius:12px;min-width:180px}
.card strong{font-size:28px;display:block;color:#81ded0}input,select,button{padding:10px;background:#1a2433;color:#eee;border:1px solid #43516a;border-radius:6px}
table{width:100%;border-collapse:collapse;margin:20px 0}th,td{text-align:left;padding:12px;border-bottom:1px solid #2c394e}th{color:#a6bacd;cursor:pointer}
.pass{color:#81ded0}.fail{color:#ff9b9b}.muted{color:#94a2b8}.bar{height:5px;background:#81ded0;border-radius:4px;margin-top:6px}
.scroll{overflow:auto}details{background:#151f2d;margin:8px 0;padding:12px;border-radius:8px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:500px;overflow:auto}
a{color:#8fc7ff}svg{background:#151f2d;border-radius:12px;width:100%;max-height:340px}text{fill:#aebbd0;font-size:12px}
</style>
<h1>TypeScript coding benchmark</h1>
<p>Executable checks + strict TypeScript compilation. One attempt per task per repeat; no repair feedback.</p>
<div class="cards" id="cards"></div>
<p id="hardware"></p><p id="settings"></p>
<button onclick="location.reload()">Refresh results</button> <a href="results.csv">Download CSV</a> · <a href="../index.html">All runs dashboard</a>
<p>Complete models rank first by tasks passed, then median generation tokens/s. Partial runs are provisional.
Generation speed includes reasoning tokens when enabled; tokenizers differ. TTFT is time to first content or reasoning token.
Answer latency includes the complete Ollama request, excluding compilation and tests. Models are warmed before evaluation.</p>
<h2>Leaderboard</h2><input id="filter" placeholder="Filter model…" aria-label="Filter model">
<div class="scroll"><table><thead><tr><th data-key="model">Model ↕</th><th data-key="passed">Solved ↕</th><th data-key="compiled">Compile ↕</th><th>Assertions</th><th data-key="tokens_s">Tokens/s ↕</th><th data-key="ttft_s">TTFT s ↕</th><th data-key="wall_s">Answer s ↕</th></tr></thead><tbody id="leader"></tbody></table></div>
<h2>Quality and speed</h2><p>Only fully evaluated models appear. Horizontal: median tokens/s. Vertical: percentage of tasks passed.</p><svg id="plot" viewBox="0 0 1100 320" role="img" aria-label="Coding quality versus generation speed"></svg>
<h2>Task results</h2><select id="modelSelect" aria-label="Model"></select> <select id="statusSelect" aria-label="Status"><option value="">All outcomes</option><option value="pass">Passed</option><option value="fail">Failed</option></select>
<div id="tasks"></div><h2>Run metadata and model errors</h2><details><summary>Configuration, hardware, and errors</summary><pre id="meta"></pre></details>
<p>This original 16-task suite screens small self-contained TypeScript implementations. It does not measure repository navigation, multi-file editing, framework work, or tool use. Runtime complexity requirements are not formally proven by these tests. Repeated deterministic runs measure speed variation, not independent quality samples. Avoid other GPU workloads during a run.</p>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>x==null?'—':Number(x).toFixed(2);
el('cards').innerHTML=[['Models',D.summaries.length],['Completed answers',D.rows.length],['Tasks per model',D.manifest.config.tasks.length]].map(([k,v])=>'<div class="card">'+esc(k)+'<strong>'+v+'</strong></div>').join('');
el('hardware').textContent=D.manifest.hardware.gpu+' | '+D.manifest.hardware.platform;
el('settings').textContent='Suite: '+(D.manifest.config.suite||'typescript')+' | Backend: '+(D.manifest.config.backend||'ollama')+' | Options: '+JSON.stringify(D.manifest.config.options)+' | Thinking: '+D.manifest.config.thinking+' | Repeats: '+D.manifest.config.repeats+' | Created: '+D.manifest.created;
let sorted=[...D.summaries],ascending=false;
function leaderboard(){
el('leader').innerHTML=sorted.filter(s=>s.model.toLowerCase().includes(el('filter').value.toLowerCase())).map(s=>'<tr><td>'+esc(s.model)+(s.completed<s.expected?'<br><small class="muted">Partial: '+s.completed+'/'+s.expected+'</small>':'')+'</td><td>'+s.passed+'/'+s.expected+'<div class="bar" style="width:'+100*s.passed/s.expected+'%"></div></td><td>'+s.compiled+'/'+s.completed+'</td><td>'+s.checks+'/'+s.total_checks+'</td><td>'+fmt(s.tokens_s)+'</td><td>'+fmt(s.ttft_s)+'</td><td>'+fmt(s.wall_s)+'</td></tr>').join('');
}leaderboard();el('filter').oninput=leaderboard;
document.querySelectorAll('th[data-key]').forEach(th=>th.onclick=()=>{ascending=!ascending;const k=th.dataset.key;sorted.sort((a,b)=>typeof a[k]==='string'?a[k].localeCompare(b[k])*(ascending?1:-1):((a[k]??-1)-(b[k]??-1))*(ascending?1:-1));leaderboard();});
const complete=D.summaries.filter(s=>s.completed===s.expected&&s.tokens_s!=null),max=Math.max(1,...complete.map(s=>s.tokens_s))*1.15;
el('plot').innerHTML='<path d="M50 15 V275 H1050" fill="none" stroke="#65748b"/><text x="10" y="20">100%</text><text x="20" y="280">0%</text><text x="490" y="310">Generation tokens / second</text>'+[0,.25,.5,.75,1].map(f=>'<text x="'+(50+1000*f)+'" y="293">'+Math.round(max*f)+'</text>').join('')+complete.map((s,i)=>'<g><circle cx="'+(50+1000*s.tokens_s/max)+'" cy="'+(275-250*s.passed/s.expected)+'" r="6" fill="hsl('+i*47+' 65% 65%)"><title>'+esc(s.model)+' | '+s.passed+'/'+s.expected+' | '+s.tokens_s+' tok/s</title></circle><text x="'+(58+1000*s.tokens_s/max)+'" y="'+(270-250*s.passed/s.expected)+'">'+esc(s.model)+'</text></g>').join('');
el('modelSelect').innerHTML='<option value="">All models</option>'+D.summaries.map(s=>'<option>'+esc(s.model)+'</option>').join('');
function taskResults(){
el('tasks').innerHTML=D.rows.filter(r=>(!el('modelSelect').value||r.model===el('modelSelect').value)&&(!el('statusSelect').value||(el('statusSelect').value==='pass')===r.passed)).map(r=>'<details><summary><span class="'+(r.passed?'pass':'fail')+'">'+esc(r.status)+'</span> · '+esc(r.model)+' · '+esc(r.task)+' · '+fmt(r.wall_s)+' s</summary><p><a href="'+encodeURI(r.artifact)+'/solution.ts">TypeScript answer</a> · <a href="'+encodeURI(r.artifact)+'/answer.txt">Raw response</a> · <a href="'+encodeURI(r.artifact)+'/request.json">Prompt</a></p><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details>').join('');
}taskResults();el('modelSelect').onchange=taskResults;el('statusSelect').onchange=taskResults;
el('meta').textContent=JSON.stringify({manifest:D.manifest,model_errors:D.errors},null,2);
</script></html>'''
