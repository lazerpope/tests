"""Collect saved results only: no model calls, compilation, or test execution."""
import csv
import datetime as dt
import json
from pathlib import Path
import tempfile

def dashboard(root):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    runs=[]; rows=[]; warnings=[]
    def read(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError) as error:
            warnings.append(f'{path.relative_to(root)}: {error}')
            return None
    for path in sorted(root.glob('*/manifest.json')):
        manifest=read(path)
        if not isinstance(manifest,dict) or not isinstance(manifest.get('config'),dict):
            warnings.append(f'Skipped invalid manifest: {path.relative_to(root)}')
            continue
        folder=path.parent
        config=manifest['config']
        run={'id':folder.name,'created':manifest.get('created',''),
             'suite':config.get('suite','typescript'),'backend':config.get('backend','ollama'),
             'manifest':manifest,'errors':[]}
        for errorfile in sorted(folder.glob('errors/*.json')):
            error=read(errorfile)
            if error is not None:
                run['errors'].append(error)
        runs.append(run)
        for resultfile in sorted(folder.glob('answers/*/result.json')):
            result=read(resultfile)
            if not isinstance(result,dict) or not all(k in result for k in ['model','task','passed','status']):
                warnings.append(f'Skipped invalid result: {resultfile.relative_to(root)}')
                continue
            # Links derive from disk paths, not untrusted result-provided HTML.
            rows.append({**result,'run':folder.name,'suite':run['suite'],'backend':run['backend'],
                         'created':run['created'],'artifact':resultfile.parent.relative_to(root).as_posix()})
    runs.sort(key=lambda r:r['created'],reverse=True)
    payload={'built':dt.datetime.now(dt.timezone.utc).isoformat(),'runs':runs,'rows':rows,'warnings':warnings}
    data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    # Unique temp files allow a manual rebuild while a benchmark updates its report.
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=root,suffix='.tmp',delete=False) as f:
        f.write(TEMPLATE.replace('__DATA__',data))
        temporary=Path(f.name)
    temporary.replace(root/'index.html')
    keys=['run','created','suite','backend','model','task','repeat','status','passed',
          'compiled','types_pass','tokens_s','wall_s','model_digest','artifact']
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=root,suffix='.tmp',delete=False) as f:
        writer=csv.DictWriter(f,keys,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)
        temporary=Path(f.name)
    temporary.replace(root/'all-results.csv')
    return root/'index.html'

TEMPLATE='''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>All coding benchmark results</title>
<style>
:root{color-scheme:dark;font-family:system-ui;background:#10151f;color:#e4eaf3}
body{max-width:1500px;margin:32px auto;padding:0 24px}p{color:#b7c5d9;line-height:1.6}
a{color:#8fc7ff}button,input,select{background:#1a2433;color:inherit;border:1px solid #43516a;padding:10px;border-radius:6px}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.cards{display:flex;gap:15px;flex-wrap:wrap;margin:20px 0}
.card{background:#1a2433;border-radius:10px;padding:18px;min-width:150px}.card strong{display:block;font-size:28px;color:#81ded0}
table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border-bottom:1px solid #2c394e}th{color:#a6bacd}
.scroll{overflow:auto}.pass{color:#81ded0}.fail{color:#ff9b9b}details{background:#1a2433;margin:10px 0;padding:12px;border-radius:8px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:450px;overflow:auto}summary{cursor:pointer}small{color:#a6bacd}
</style>
<h1>All coding benchmark results</h1>
<p>Results from every saved run, across dates. Rebuilding this page reads saved files only.</p>
<p id="built"></p>
<button onclick="location.reload()">Refresh page</button> <a href="all-results.csv">All results CSV</a>
<label><input id="auto" type="checkbox"> Refresh every 15 seconds</label>
<p>Future runs rebuild this dashboard after each saved answer. For older runs or an already-running process, use <code>python bench.py dashboard</code>.</p>
<div class="filters">
<label>Run <select id="run"></select></label><label>Suite <select id="suite"></select></label>
<label>Model <select id="model"></select></label>
<label>Outcome <select id="status"><option value="">All</option><option value="pass">Passed</option><option value="fail">Failed</option></select></label>
<label>Search <input id="search" placeholder="Task or run name"></label>
</div>
<div class="cards" id="cards"></div>
<h2>Run and model summaries</h2>
<p>Each row keeps its own settings and task set. Scores from different suites, versions, or settings are not merged into one ranking. Repeated attempts remain separate records.</p>
<div class="scroll"><table><thead><tr><th>Run / date</th><th>Suite / backend</th><th>Model</th><th>Saved / planned</th><th>Passed / saved</th><th>Checks passed</th><th>Median tokens/s</th><th>Settings</th></tr></thead><tbody id="summaries"></tbody></table></div>
<h2>All task attempts</h2><p id="count"></p>
<div id="attempts"></div><button id="more">Show 100 more</button>
<details><summary>Import warnings and model setup errors</summary><pre id="warnings"></pre></details>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent), el=id=>document.getElementById(id);
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const url=p=>p.split('/').map(encodeURIComponent).join('/');
const fmt=n=>n==null?'—':Number(n).toFixed(2);
const median=xs=>{xs=xs.filter(x=>typeof x==='number').sort((a,b)=>a-b);const n=xs.length;return n?(xs[Math.floor(n/2)]+xs[Math.floor((n-1)/2)])/2:null};
for(const [id,values] of [['run',D.runs.map(r=>r.id)],['suite',D.runs.map(r=>r.suite)],['model',D.runs.flatMap(r=>r.manifest.config.models||[])]])
 el(id).innerHTML='<option value="">All</option>'+[...new Set(values)].map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('');
el('built').textContent='Built '+D.built+' · '+D.runs.length+' runs · '+D.rows.length+' saved attempts';
el('warnings').textContent=JSON.stringify({warnings:D.warnings,errors:D.runs.filter(r=>r.errors.length).map(r=>({run:r.id,errors:r.errors}))},null,2);
let limit=100;
function filtered(){return D.rows.filter(r=>(!el('run').value||r.run===el('run').value)&&(!el('suite').value||r.suite===el('suite').value)&&(!el('model').value||r.model===el('model').value)&&(!el('status').value||(el('status').value==='pass')===r.passed)&&(r.task+' '+r.run).toLowerCase().includes(el('search').value.toLowerCase()));}
function render(){
 const rows=filtered();
 el('cards').innerHTML=[['Visible attempts',rows.length],['Passed',rows.filter(r=>r.passed).length],['Runs with attempts',new Set(rows.map(r=>r.run)).size],['Models with attempts',new Set(rows.map(r=>r.model)).size]].map(([k,v])=>'<div class="card">'+k+'<strong>'+v+'</strong></div>').join('');
 const summaries=[];
 for(const run of D.runs){
 if(el('run').value&&el('run').value!==run.id||el('suite').value&&el('suite').value!==run.suite)continue;
 for(const model of run.manifest.config.models||[]){
 if(el('model').value&&el('model').value!==model)continue;
 const all=D.rows.filter(r=>r.run===run.id&&r.model===model),visible=rows.filter(r=>r.run===run.id&&r.model===model);
 if((el('status').value||el('search').value)&&!visible.length)continue;
 const cfg=run.manifest.config,planned=(cfg.tasks||[]).length*(cfg.repeats||1),passed=all.filter(r=>r.passed).length;
 const checkPassed=all.reduce((n,r)=>n+(r.checks||[]).filter(c=>c.pass).length,0),checkTotal=all.reduce((n,r)=>n+(r.total_checks||0),0);
 summaries.push('<tr><td><a href="'+url(run.id+'/report.html')+'">'+esc(run.id)+'</a><br><small>'+esc(run.created)+'</small></td><td>'+esc(run.suite)+' / '+esc(run.backend)+'</td><td>'+esc(model)+'</td><td>'+all.length+'/'+planned+'</td><td>'+passed+'/'+all.length+'</td><td>'+checkPassed+'/'+checkTotal+'</td><td>'+fmt(median(all.map(r=>r.tokens_s)))+'</td><td><details><summary>Inspect</summary><pre>'+esc(JSON.stringify(run.manifest,null,2))+'</pre></details></td></tr>');
 }}
 el('summaries').innerHTML=summaries.join('');
 rows.sort((a,b)=>b.created.localeCompare(a.created)||a.run.localeCompare(b.run)||a.model.localeCompare(b.model)||a.task.localeCompare(b.task)||(a.repeat||0)-(b.repeat||0));
 el('count').textContent='Showing '+Math.min(limit,rows.length)+' of '+rows.length+' attempts. Summary counts always cover the entire run/model, even when outcomes or search filter the attempts.';
 el('attempts').innerHTML=rows.slice(0,limit).map(r=>'<details><summary><span class="'+(r.passed?'pass':'fail')+'">'+esc(r.status)+'</span> · '+esc(r.run)+' · '+esc(r.model)+' · '+esc(r.task)+' · attempt '+((r.repeat||0)+1)+'</summary><p><a href="'+url(r.artifact+'/solution.ts')+'">Solution</a> · <a href="'+url(r.artifact+'/request.json')+'">Prompt</a> · <a href="'+url(r.artifact+'/result.json')+'">Result JSON</a></p><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details>').join('');
 el('more').hidden=rows.length<=limit;
}
for(const id of ['run','suite','model','status','search'])el(id).addEventListener('input',()=>{limit=100;render()});
el('more').onclick=()=>{limit+=100;render()};
// URL state preserves filters and auto-refresh when the page reloads.
const params=new URLSearchParams(location.hash.slice(1));
for(const id of ['run','suite','model','status','search'])if(params.has(id))el(id).value=params.get(id);
el('auto').checked=params.get('auto')==='1';
function save(){const p=new URLSearchParams();for(const id of ['run','suite','model','status','search'])if(el(id).value)p.set(id,el(id).value);if(el('auto').checked)p.set('auto','1');location.replace('#'+p.toString());}
for(const id of ['run','suite','model','status','search','auto'])el(id).addEventListener('change',save);
setInterval(()=>{if(el('auto').checked)location.reload()},15000);
render();
</script></html>'''
