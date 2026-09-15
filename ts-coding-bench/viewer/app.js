'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(x,n=1)=>Number.isFinite(x)?x.toFixed(n):'—';
const median=xs=>{xs=xs.filter(Number.isFinite).sort((a,b)=>a-b);return xs.length?(xs[Math.floor(xs.length/2)]+xs[Math.floor((xs.length-1)/2)])/2:null};
const color=i=>['#238778','#9bbd62','#d98d69','#778fc0','#b29bc6','#baac57','#5bafb0'][i%7];
const nice=x=>String(x).replaceAll('_',' ');
let data={runs:[],rows:[],warnings:[]}, enriched=[], grouped=[], matching=[], page=0, view='overview', busy=false, detailRow=null, artifactVersion=0;
let sortKey='rate',sortDir=-1;
let state={excluded:[],filters:{},search:'',from:'',to:'',minSpeed:'',maxTime:'',completeOnly:false,live:true};
try{state={...state,...JSON.parse(localStorage.getItem('benchroom-v1')||'{}')}}catch{}
const save=()=>{try{localStorage.setItem('benchroom-v1',JSON.stringify(state))}catch{}};
const fieldDefs=[['model','Model'],['task','Task'],['status','Outcome'],['suite','Suite'],['backend','Backend'],['thinking','Thinking'],['agent_stop_reason','Agent stop reason'],['first_passed','First submission passed']];
const advancedDefs=[['category','Category'],['context','Context'],['tokens','Output limit'],['temperature','Temperature'],['top_p','Top p'],['top_k','Top k'],['min_p','Min p'],['repeat_penalty','Repeat penalty'],['seed','Seed'],['repeat','Repeat index'],['digest','Model digest'],['suiteHash','Suite version'],['harnessHash','Harness version'],['gpu','GPU']];
const fmtDate=x=>x?new Date(x).toLocaleString():'Unknown';
const fullkey=r=>JSON.stringify([r.run,r.model,r.digest,r.harnessHash]);

function prepare(){
 const runs=new Map(data.runs.map(r=>[r.id,r]));
 enriched=data.rows.map(r=>{
  const run=runs.get(r.run),cfg=run.config,opts=cfg.options||{};
  // Old records preserved by an acknowledged change retain their original revision.
  const prior=(run.history||[]).find(h=>(h.preserved_results||[]).includes(r.artifact.slice(r.run.length+1)+'/result.json'));
  return {...r,suite:cfg.suite||'typescript',backend:cfg.backend||'ollama',thinking:cfg.thinking||'unknown',
   context:opts.num_ctx??'unknown',tokens:opts.num_predict??'unknown',temperature:opts.temperature??'unknown',
   top_p:opts.top_p??'default',top_k:opts.top_k??'default',min_p:opts.min_p??'default',repeat_penalty:opts.repeat_penalty??'default',
   seed:opts.seed??'unknown',digest:r.model_digest||'unknown',suiteHash:cfg.suite_hash||'unknown',
   harnessHash:r.harness_hash||prior?.previous_hash||cfg.harness_hash||'unknown',gpu:run.hardware.gpu||'unknown'};
 });
}
function runSidebar(){
 $('runCount').textContent=data.runs.length;
 $('runList').innerHTML=data.runs.map(run=>{
  const rows=data.rows.filter(r=>r.run===run.id),planned=(run.config.models||[]).length*(run.config.tasks||[]).length*(run.config.repeats||1);
  const done=rows.length,pc=planned?Math.min(100,100*done/planned):0;
  return '<label class="run-item"><input type="checkbox" data-run="'+esc(run.id)+'" '+(!state.excluded.includes(run.id)?'checked':'')+'><div><strong>'+esc(run.id)+'</strong><small>'+esc((run.created||'').slice(0,10))+' · '+done+'/'+planned+' saved</small><div class="tinybar"><i style="width:'+pc+'%"></i></div>'+(run.errors.length?'<small>'+run.errors.length+' setup errors</small>':'')+'</div></label>';
 }).join('');
 $('runList').querySelectorAll('input').forEach(input=>input.onchange=()=>{
  state.excluded=input.checked?state.excluded.filter(r=>r!==input.dataset.run):[...new Set([...state.excluded,input.dataset.run])];save();render();
 });
}
function buildFilters(){
 const open=new Set([...document.querySelectorAll('.filter[open]')].map(x=>x.dataset.field));
 function markup([field,label]){
  const values=[...new Set(enriched.map(r=>String(r[field]??'unknown')))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  const selected=state.filters[field]||[];
  // Keep stale selections visible and removable after the source run disappears.
  for(const v of selected)if(!values.includes(v))values.push(v);
  return '<details class="filter" data-field="'+field+'" '+(open.has(field)?'open':'')+'><summary>'+label+(selected.length?' · '+selected.length:'')+'</summary><div class="filter-menu"><button data-clear="'+field+'">Any '+label.toLowerCase()+'</button>'+values.map(v=>'<label><input type="checkbox" data-field="'+field+'" value="'+esc(v)+'" '+(selected.includes(v)?'checked':'')+'><span>'+esc(v)+'</span></label>').join('')+'</div></details>';
 }
 $('filters').innerHTML=fieldDefs.map(markup).join('');
 $('advancedFilters').innerHTML=advancedDefs.map(markup).join('');
 document.querySelectorAll('.filter-menu input').forEach(input=>input.onchange=()=>{
  const key=input.dataset.field,values=state.filters[key]||[];
  state.filters[key]=input.checked?[...new Set([...values,input.value])]:values.filter(x=>x!==input.value);
  page=0;save();buildFilters();render();
 });
 document.querySelectorAll('[data-clear]').forEach(button=>button.onclick=()=>{delete state.filters[button.dataset.clear];page=0;save();buildFilters();render()});
}
function selectedRows(){
 const allCounts=new Map();
 enriched.forEach(r=>{const k=JSON.stringify([r.run,r.model]);allCounts.set(k,(allCounts.get(k)||0)+1)});
 return enriched.filter(r=>{
  if(state.excluded.includes(r.run))return false;
  for(const [key,values] of Object.entries(state.filters))if(values.length&&!values.includes(String(r[key]??'unknown')))return false;
  if(state.search&&!JSON.stringify([r.model,r.run,r.task,r.error,r.checks]).toLowerCase().includes(state.search.toLowerCase()))return false;
  if(state.from&&r.saved.slice(0,10)<state.from||state.to&&r.saved.slice(0,10)>state.to)return false;
  if(state.minSpeed!==''&&(!Number.isFinite(r.tokens_s)||r.tokens_s<Number(state.minSpeed)))return false;
  if(state.maxTime!==''&&(!Number.isFinite(r.wall_s)||r.wall_s>Number(state.maxTime)))return false;
  if(state.completeOnly){
   const cfg=data.runs.find(x=>x.id===r.run).config;
   if((allCounts.get(JSON.stringify([r.run,r.model]))||0)<cfg.tasks.length*(cfg.repeats||1))return false;
  }
  return true;
 });
}
function groups(rows){
 const map=new Map();

 for(const r of rows){
  const k=fullkey(r);
  if(!map.has(k))map.set(k,[]);
  map.get(k).push(r);
 }

 return [...map].map(([key,rs])=>{
  const first=rs[0];
  const run=data.runs.find(x=>x.id===first.run);
  const planned=run.config.tasks.length*(run.config.repeats||1);

  // Number of actually saved results for this model/run
  const savedCount=enriched.filter(r=>fullkey(r)===key).length;

  // Latest saved timestamp from currently matching rows
  const saved=rs
   .map(r=>r.saved)
   .filter(Boolean)
   .sort()
   .pop() || null;

  const passed=rs.filter(r=>r.passed).length;

  return {
   key,
   model:first.model,
   run:first.run,
   rows:rs,
   planned,
   savedCount,
   saved,
   passed,
   rate:100*passed/rs.length,
   compile:100*rs.filter(r=>r.compiled).length/rs.length,
   speed:median(rs.map(r=>r.tokens_s)),
   ttft:median(rs.map(r=>r.ttft_s)),
   sample:first,
   partial:savedCount<planned
  };
 });
}
function recordedTime(rows){
 const times=rows.map(r=>r.end_to_end_s??r.wall_s).filter(t=>Number.isFinite(t)&&t>=0);
 return {seconds:times.length?times.reduce((sum,t)=>sum+t,0):null,missing:rows.length-times.length};
}
function duration(seconds){
 if(!Number.isFinite(seconds))return '—';
 return seconds<60?fmt(seconds)+' s':seconds<3600?Math.floor(seconds/60)+'m '+Math.floor(seconds%60)+'s':Math.floor(seconds/3600)+'h '+Math.floor(seconds%3600/60)+'m';
}
function metric(label,value,caption,feature=false){return '<div class="metric '+(feature?'feature':'')+'"><div class="label">'+label+'</div><strong>'+value+'</strong><small>'+caption+'</small></div>'}
function render(){
 matching=selectedRows();grouped=groups(matching);
 grouped.forEach(g=>{const t=recordedTime(g.rows);g.totalTime=t.seconds;g.missingTime=t.missing});
 const passed=matching.filter(r=>r.passed).length,compiled=matching.filter(r=>r.compiled).length;
 $('metrics').innerHTML=metric('Task pass rate',matching.length?fmt(100*passed/matching.length)+'%':'—',passed+' / '+matching.length+' saved attempts',true)+
  metric('Generation speed',fmt(median(matching.map(r=>r.tokens_s)))+' <small>tok/s</small>','Median over selected attempts')+
  metric('Answer / agent latency',fmt(median(matching.map(r=>r.wall_s)))+' <small>s</small>','Direct: model request. DSH: complete agent session.')+
  metric('Strict compilation',matching.length?fmt(100*compiled/matching.length)+'%':'—',new Set(matching.map(r=>r.model)).size+' models · '+new Set(matching.map(r=>r.run)).size+' runs')+
  metric('Total recorded attempt time',duration(recordedTime(matching).seconds),recordedTime(matching).missing+' attempts without timing · DSH includes grading; direct runs record generation only');
 const agentRows=matching.filter(r=>r.backend==='dsh');
 if(agentRows.length)$('metrics').innerHTML+=metric('DSH first submission',fmt(100*agentRows.filter(r=>r.first_passed===true).length/agentRows.length)+'<small>%</small>','Private pass rate before public-feedback repairs; no submission counts as unsolved');
 $('empty').hidden=matching.length>0||view==='runs';
 renderBoard();renderScatter();renderTotalTime();renderOutcomes();renderMatrix();renderLatency();renderTimeline();renderAttempts();renderRuns();
 $('diagnosticLabel').textContent='Import diagnostics · '+data.warnings.length+' warnings';
 $('diagnostics').textContent=JSON.stringify(data.warnings,null,2);
}

function renderBoard(){
 const sorted=[...grouped].sort((a,b)=>{
  if(a[sortKey]==null)return b[sortKey]==null?0:1;
  if(b[sortKey]==null)return -1;

  return (
   typeof a[sortKey]==='string'
    ? a[sortKey].localeCompare(b[sortKey])
    : a[sortKey]-b[sortKey]
  )*sortDir;
 });

 $('groupCount').textContent=grouped.length+' GROUPS';

 $('board').innerHTML=sorted.map(g=>
  '<tr>'+
   '<td class="model-name">'+
    esc(g.model)+
    '<small>'+esc(g.sample.digest.slice(0,12))+' · '+esc(g.sample.harnessHash.slice(0,8))+'</small>'+
   '</td>'+

   '<td>'+
    esc(g.run)+
    '<small>'+esc(g.sample.suite)+' / '+esc(g.sample.backend)+'</small>'+
   '</td>'+

   '<td>'+
    fmt(g.rate)+'%'+
    '<div class="ratebar"><i style="width:'+g.rate+'%"></i></div>'+
    '<small>'+g.passed+'/'+g.rows.length+' filtered</small>'+
   '</td>'+

   '<td>'+fmt(g.compile)+'%</td>'+

   '<td>'+fmt(g.speed)+'</td>'+
   '<td>'+duration(g.totalTime)+'<small>'+g.missingTime+' missing timings</small></td>'+

   // SAVED column
   '<td>'+esc(fmtDate(g.saved))+'</td>'+

   '<td>'+fmt(g.ttft,2)+'</td>'+

   '<td>'+
    '<span class="badge '+(g.partial?'fail':'pass')+'">'+
     (g.partial?'Partial':'Complete')+
     ' · '+g.savedCount+'/'+g.planned+
    '</span>'+
    '<small>'+
     esc(g.sample.context)+' ctx · T '+
     esc(g.sample.temperature)+' · thinking '+
     esc(g.sample.thinking)+
    '</small>'+
   '</td>'+
  '</tr>'
 ).join('');
}
function svg(content,w=650,h=270){return '<svg viewBox="0 0 '+w+' '+h+'" role="img">'+content+'</svg>'}
function renderScatter(){
 const gs=grouped.filter(g=>g.speed!=null),max=Math.max(10,...gs.map(g=>g.speed))*1.15;
 let s='<text x="9" y="14">PASS RATE</text>';
 for(let i=0;i<=4;i++){const y=225-i*48;s+='<line class="gridline" x1="45" x2="625" y1="'+y+'" y2="'+y+'"/><text x="9" y="'+(y+4)+'">'+i*25+'%</text>'}
 for(let i=0;i<=4;i++)s+='<text x="'+(45+i*140)+'" y="246">'+fmt(max*i/4,0)+'</text>';
 s+='<text x="255" y="266">GENERATION TOKENS / SECOND</text>';
 gs.forEach((g,i)=>{const x=45+560*g.speed/max,y=225-192*(g.rate/100);s+='<circle cx="'+x+'" cy="'+y+'" r="'+(g.partial?5:7)+'" fill="'+color(i)+'" opacity=".85" stroke="white" stroke-width="2"><title>'+esc(g.model+' | '+g.run+' | '+fmt(g.rate)+'% | '+fmt(g.speed)+' tok/s | '+g.rows.length+' saved attempts')+'</title></circle>'});
 $('scatter').innerHTML=svg(s);
}
function renderTotalTime(){
 const gs=grouped.filter(g=>g.totalTime!=null&&g.missingTime===0),max=Math.max(1,...gs.map(g=>g.totalTime))*1.1;
 let s='<text x="9" y="14">PASS RATE</text>';
 for(let i=0;i<=4;i++){const y=225-i*48;s+='<line class="gridline" x1="45" x2="625" y1="'+y+'" y2="'+y+'"/><text x="9" y="'+(y+4)+'">'+i*25+'%</text>'}
 for(let i=0;i<=4;i++)s+='<text x="'+(45+i*140)+'" y="246">'+fmt(max*i/240,1)+'</text>';
 s+='<text x="165" y="266">TOTAL RECORDED ATTEMPT TIME (MINUTES)</text>';
 gs.forEach((g,i)=>{
  const x=45+560*g.totalTime/max,y=225-192*g.rate/100;
  s+='<circle cx="'+x+'" cy="'+y+'" r="7" fill="'+color(i)+'" fill-opacity="'+(g.partial?'.35':'.9')+'" stroke="'+color(i)+'"><title>'+esc(g.model+' | '+g.run+' | '+fmt(g.rate)+'% | '+duration(g.totalTime)+' | '+g.rows.length+' filtered attempts'+(g.partial?' | PARTIAL SUITE':''))+'</title></circle>';
 });
 $('totalTimeChart').innerHTML=svg(s)+'<p class="note">'+(grouped.length-gs.length)+' groups excluded because timing is missing. Faded points are partial suites. Compare equal task sets; filters change both time totals and pass rates.</p>';
}
function renderOutcomes(){
 const counts=new Map();matching.forEach(r=>counts.set(r.status,(counts.get(r.status)||0)+1));
 $('outcomes').innerHTML=[...counts].sort((a,b)=>b[1]-a[1]).map(([status,n],i)=>'<div class="outcome"><div class="outcome-label"><span>'+esc(nice(status))+'</span><strong>'+n+' <small>('+fmt(100*n/matching.length)+'%)</small></strong></div><div class="outcome-track"><i style="width:'+100*n/matching.length+'%;background:'+(status==='pass'?'#399d7e':color(i+2))+'"></i></div></div>').join('')||'<p>No outcomes yet.</p>';
}
function renderMatrix(){
 const tasks=[...new Set(data.runs.filter(r=>!state.excluded.includes(r.id)).flatMap(r=>r.config.tasks||[]))].sort();
 let s='<table class="matrix"><thead><tr><th>RUN / MODEL</th>'+tasks.map(t=>'<th>'+esc(t)+'</th>').join('')+'</tr></thead><tbody>';
 grouped.forEach((g,gi)=>{s+='<tr><td>'+esc(g.model)+'<small>'+esc(g.run)+' · '+esc(g.sample.harnessHash.slice(0,8))+'</small></td>';
 tasks.forEach(t=>{const rs=g.rows.filter(r=>r.task===t),n=rs.filter(r=>r.passed).length,rate=rs.length?n/rs.length:null;
  s+='<td><button class="cell" data-group="'+gi+'" data-task="'+esc(t)+'" '+(!rs.length?'disabled':'')+' style="background:'+(rate==null?'#f0f2ec':rate===1?'#b1dec1':rate===0?'#f1d6c6':'#e7dda0')+'" title="'+n+'/'+rs.length+' saved attempts">'+(rate==null?'—':Math.round(rate*100)+'%')+'</button></td>'});
 s+='</tr>'});s+='</tbody></table>';$('matrix').innerHTML=s;
 $('matrix').querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>{const g=grouped[Number(b.dataset.group)];state.filters.model=[g.model];state.filters.task=[b.dataset.task];state.excluded=data.runs.filter(r=>r.id!==g.run).map(r=>r.id);save();runSidebar();buildFilters();setView('attempts');render()});
}
function renderLatency(){
 const values=matching
  .map(r=>r.wall_s)
  .filter(Number.isFinite);

 const max=Math.max(1,...values);
 const bins=Array(8).fill(0);

 values.forEach(v=>{
  bins[Math.min(7,Math.floor(v/max*8))]++;
 });

 const peak=Math.max(1,...bins);
 let s='';

 bins.forEach((n,i)=>{
  const h=145*n/peak;
  const x=35+i*72;

  s+=
   '<rect x="'+x+'" y="'+(185-h)+'" width="51" height="'+h+'" rx="4" fill="#8eb6a0">'+
    '<title>'+
     fmt(max*i/8)+'–'+fmt(max*(i+1)/8)+' s: '+n+' attempts'+
    '</title>'+
   '</rect>'+
   '<text x="'+(x+17)+'" y="'+(179-h)+'">'+n+'</text>'+
   '<text x="'+x+'" y="205">'+fmt(max*i/8)+'</text>';
 });

 s+='<text x="240" y="233">ANSWER TIME (SECONDS)</text>';

 $('latencyChart').innerHTML=svg(s,650,245);
}
function renderTimeline(){
 const days=new Map();matching.forEach(r=>{const day=r.saved.slice(0,10);if(!days.has(day))days.set(day,[0,0]);days.get(day)[r.passed?0:1]++});
 const ds=[...days].sort((a,b)=>a[0].localeCompare(b[0])),peak=Math.max(1,...ds.map(x=>x[1][0]+x[1][1]));
 const width=Math.max(650,ds.length*70),step=(width-55)/Math.max(1,ds.length);
 let s='';
 ds.forEach(([day,[pass,fail]],i)=>{const x=35+i*step,hp=145*pass/peak,hf=145*fail/peak,w=Math.min(45,step-12);
  s+='<g><title>'+day+': '+pass+' passed, '+fail+' failed</title><rect x="'+x+'" y="'+(180-hp)+'" width="'+w+'" height="'+hp+'" fill="#559d83"/><rect x="'+x+'" y="'+(180-hp-hf)+'" width="'+w+'" height="'+hf+'" rx="2" fill="#e2b297"/><text x="'+x+'" y="203">'+day.slice(5)+'</text></g>'});
 s+='<text x="35" y="231">GREEN: PASSED · PEACH: FAILED · UTC DATES</text>';
 $('timeline').innerHTML='<div class="table-scroll">'+svg(s,width,245)+'</div>';
}
function renderAttempts(){
 const rs=[...matching],mode=$('attemptSort').value;
 rs.sort((a,b)=>mode==='slow'?(b.wall_s??-1)-(a.wall_s??-1):mode==='fast'?(b.tokens_s??-1)-(a.tokens_s??-1):mode==='failed'?Number(a.passed)-Number(b.passed):a.saved.localeCompare(b.saved)*(mode==='old'?1:-1));
 page=Math.min(page,Math.max(0,Math.ceil(rs.length/30)-1));
 $('attemptList').innerHTML=rs.slice(page*30,(page+1)*30).map(r=>'<button class="attempt" data-id="'+esc(r.id)+'"><div>'+esc(r.task)+' <span class="badge '+(r.passed?'pass':'fail')+'">'+esc(nice(r.status))+'</span><small>'+esc(r.model)+' · '+esc(r.run)+' · repeat '+((r.repeat||0)+1)+'</small></div><div class="attempt-right">'+fmt(r.tokens_s)+' tok/s · '+fmt(r.wall_s)+' s<small>'+esc(fmtDate(r.saved))+' ↗</small></div></button>').join('');
 $('attemptList').querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>openDetail(enriched.find(r=>r.id===b.dataset.id)));
 $('pageInfo').textContent=rs.length?'Page '+(page+1)+' / '+Math.ceil(rs.length/30)+' · '+rs.length+' attempts':'No matching attempts';
 $('prev').disabled=page===0;$('next').disabled=(page+1)*30>=rs.length;
}
function renderRuns(){
 $('notebooks').innerHTML=data.runs.filter(run=>!state.excluded.includes(run.id)).map(run=>{
  const rs=enriched.filter(r=>r.run===run.id),passed=rs.filter(r=>r.passed).length;
  const timing=Number.isFinite(run.timing?.total_suite_s)?'<p>Total suite time: <strong>'+duration(run.timing.total_suite_s)+'</strong> including setup, downloads and grading. '+(run.timing.segments?.at(-1)?.active?'Last saved checkpoint; run may still be active.':'Saved across invocations.')+'</p>':'';
  return '<article class="run-card"><div class="panel-title"><div><h2>'+esc(run.id)+'</h2><p>'+esc(fmtDate(run.created))+'</p></div><span class="tag">'+esc(run.config.suite||'typescript')+'</span></div><div class="run-stats"><span>'+rs.length+' saved</span><span>'+passed+' passed</span><span>'+run.config.models.length+' planned models</span><span>'+run.errors.length+' setup errors</span></div>'+timing+'<p class="note">Notebook follows run toggles; task and outcome filters apply to the comparison views.</p><details><summary>Settings, hardware and revision history</summary><pre>'+esc(JSON.stringify(run,null,2))+'</pre></details>'+(run.errors.length?'<details open><summary>Model setup errors</summary><pre>'+esc(JSON.stringify(run.errors,null,2))+'</pre></details>':'')+'</article>';
 }).join('');
}
function setView(v){
 view=v;for(const id of ['overview','attempts','runs'])$(id).hidden=id!==v;
 document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===v));
 $('heading').innerHTML=({overview:'The bigger picture',attempts:'Every answer, up close',runs:'Your experiment notebook'})[v]+'<span>.</span>';
 $('empty').hidden=matching.length>0||v==='runs';
}
async function openDetail(r){
 detailRow=r;$('detailRun').textContent=r.run+' / '+r.model;$('detailTitle').textContent=r.task;
 $('detailSummary').textContent=nice(r.status)+' · '+fmt(r.tokens_s)+' tok/s · '+fmt(r.wall_s)+' s · thinking '+r.thinking+' · '+(r.checks||[]).filter(c=>c.pass).length+'/'+r.total_checks+' check groups passed';
 const tabs=r.backend==='dsh'?
  [['Final result','result.json'],['Final source','solution.ts'],['First result','first-result.json'],['First source','first-solution.ts'],['Prompt','request.json'],['Tools','tool-events.jsonl'],['DSH session','dsh-events.jsonl'],['DSH errors','dsh-stderr.log'],['Provider errors','provider-errors.jsonl'],['Compiler','compile.log']]:
  [['Result','result.json'],['Source','solution.ts'],['Prompt','request.json'],['Thinking','thinking.txt'],['Compiler','compile.log'],['Checks','checks.json'],['Types','typechecks.ts'],['Raw answer','answer.txt']];
 if(r.backend==='dsh')$('detailSummary').textContent+=' · first: '+String(r.first_passed??'no submission')+' · '+(r.submissions||0)+' submissions · '+(r.tool_calls||0)+' tools · stop: '+nice(r.agent_stop_reason);
 $('detailTabs').innerHTML=tabs.map(([name,file])=>'<button data-file="'+file+'">'+name+'</button>').join('');
 $('detailTabs').querySelectorAll('button').forEach(b=>b.onclick=()=>loadArtifact(b.dataset.file));
 $('detail').showModal();await loadArtifact('result.json');
}
async function loadArtifact(file){
 const version=++artifactVersion;$('artifactName').textContent=file;$('code').textContent='Loading…';
 $('detailTabs').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.file===file));
 try{const response=await fetch('/api/artifact?path='+encodeURIComponent(detailRow.artifact+'/'+file));const text=await response.text();if(version!==artifactVersion)return;$('code').textContent=response.ok?(text||'(Empty file)'):'Unavailable: '+text}catch(e){if(version===artifactVersion)$('code').textContent=String(e)}
}
async function refresh(){
 if(busy)return;busy=true;$('refresh').disabled=true;
 try{const response=await fetch('/api/results');if(!response.ok)throw Error('HTTP '+response.status);data=await response.json();prepare();runSidebar();buildFilters();render();
 $('connection').textContent='● Connected · '+data.rows.length+' saved attempts · '+data.runs.length+' runs';$('updated').textContent='Updated '+new Date().toLocaleTimeString();
 }catch(e){$('connection').textContent='Connection interrupted — showing last loaded results. '+e.message}
 finally{busy=false;$('refresh').disabled=false}
}
function downloadCSV(){
 const keys=['run','suite','backend','model','task','repeat','status','passed','first_passed','compiled','tokens_s','wall_s','end_to_end_s','grading_wall_s','tool_calls','submissions','model_requests','input_tokens','output_tokens','agent_stop_reason','ttft_s','thinking','context','tokens','temperature','seed','digest','suiteHash','harnessHash','saved'];
 const quote=x=>{let s=String(x??'');if(/^[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};
 const text=[keys.map(quote).join(','),...matching.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='benchroom-filtered.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>setView(b.dataset.view));
document.querySelectorAll('[data-sort]').forEach(th=>th.onclick=()=>{sortDir=sortKey===th.dataset.sort?-sortDir:-1;sortKey=th.dataset.sort;renderBoard()});
for(const id of ['search','from','to','minSpeed','maxTime','completeOnly']){
 $(id)[id==='completeOnly'?'checked':'value']=state[id];$(id).addEventListener('input',()=>{state[id]=id==='completeOnly'?$(id).checked:$(id).value;page=0;save();render()});
}
$('live').checked=state.live;$('live').onchange=()=>{state.live=$('live').checked;save()};
$('refresh').onclick=refresh;$('export').onclick=downloadCSV;
$('allRuns').onclick=()=>{state.excluded=[];page=0;save();runSidebar();render()};
$('noRuns').onclick=()=>{state.excluded=data.runs.map(r=>r.id);page=0;save();runSidebar();render()};
$('reset').onclick=()=>{state={...state,excluded:[],filters:{},search:'',from:'',to:'',minSpeed:'',maxTime:'',completeOnly:false};for(const id of ['search','from','to','minSpeed','maxTime'])$(id).value='';$('completeOnly').checked=false;page=0;save();runSidebar();buildFilters();render()};
$('prev').onclick=()=>{page--;renderAttempts()};$('next').onclick=()=>{page++;renderAttempts()};$('attemptSort').onchange=()=>{page=0;renderAttempts()};
$('close').onclick=()=>{$('detail').close();artifactVersion++};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('code').textContent);$('copy').textContent='Copied';setTimeout(()=>$('copy').textContent='Copy',1200)}catch{$('copy').textContent='Select text to copy'}};
setInterval(()=>{if(state.live&&!document.hidden)refresh()},10000);
refresh();
