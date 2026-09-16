// Source-only DSH tool. Candidate code executes ONLY in isolated Docker graders.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(process.env.BENCH_DSH_BIN);
const {defineTool}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-tools')).href);
const cfg=JSON.parse(fs.readFileSync(process.env.BENCH_TOOL_CONFIG,'utf8'));
let count=0,submission=0,duplicates=0,chain=Promise.resolve();
const seen=new Map();
const log=record=>fs.appendFileSync(cfg.log,JSON.stringify({at:new Date().toISOString(),...record})+'\n');
function state(value){
 const tmp=cfg.state+'.tmp';
 fs.writeFileSync(tmp,JSON.stringify({submissions:submission,tool_calls:count,duplicates,...value}));
 fs.renameSync(tmp,cfg.state);
}
function grade(source){
 return new Promise((resolve,reject)=>{
  const args=['run','--rm','-i','--name',cfg.publicContainer,'--network','none','--read-only',
   '--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
   '--pids-limit','64','--memory','512m','--cpus','1','--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
   cfg.image,'/usr/local/bin/node','/opt/bench/grade.cjs'];
  const child=execFile(cfg.docker,args,{timeout:70000,maxBuffer:300000,encoding:'utf8',windowsHide:true},(error,stdout,stderr)=>{
   if(error)return reject(Error('Public grader failed: '+String(error)+' '+stderr.slice(0,1500)));
   try{resolve(JSON.parse(stdout))}catch(e){reject(Error('Invalid public grader response: '+e))}
  });
  child.stdin.on('error',()=>{});
  child.stdin.end(JSON.stringify({source,types:cfg.publicTypes,tests:cfg.publicTests}));
 });
}
function serial(fn){const p=chain.then(fn);chain=p.catch(()=>{});return p}
export const name='bench-isolated-source-tool';
export const inject=['tools'];
export function apply(ctx){
 ctx.tools.register(defineTool({
  name:'submit_solution',
  description:'Submit complete solution.ts source. The preinstalled offline TypeScript compiler and public checks run automatically. Read feedback and submit corrected source if needed. No shell, internet, installs or hidden checks. At most '+cfg.maxSubmissions+' distinct candidates; never submit unchanged code.',
  parameters:{source:{type:'string',required:true,description:'Entire TypeScript implementation without markdown. Exactly this argument; no command or paths.'}},
  output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},
  execute:args=>serial(async()=>{
   if(count>=cfg.maxCalls||submission>=cfg.maxSubmissions||Date.now()>=cfg.deadline){
    state({stop_reason:'submission_budget'});throw Error('Submission/tool/time budget exhausted.');
   }
   count++;log({type:'tool_start',tool:'submit_solution',call:count});
   if(Object.keys(args).length!==1||typeof args.source!=='string'||!args.source.trim()||Buffer.byteLength(args.source)>262144){
    log({type:'protocol_error',error:'Expected exactly one nonempty source argument'});
    throw Error('Expected exactly source containing the complete TypeScript file, at most 256 KiB. There is no shell or internet.');
   }
   const source=args.source.replace(/\r\n/g,'\n').trim()+'\n';
   const stripped=source.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g,'').trim();
   if(!stripped||/^export\s*\{\s*\}\s*;?$/.test(stripped)){
    log({type:'protocol_error',error:'Empty starter'});throw Error('The empty starter is not a solution. Implement the requested exports.');
   }
   const hash=createHash('sha256').update(source).digest('hex');
   if(seen.has(hash)){
    duplicates++;log({type:'duplicate_submission',source_hash:hash});
    state({stop_reason:duplicates>=2?'repeated_source':null});
    return 'Unchanged source rejected; no new repair counted. Change code using this earlier public feedback: '+seen.get(hash);
   }
   submission++;
   const target=path.join(cfg.snapshots,String(submission).padStart(3,'0')+'.ts');
   fs.writeFileSync(target+'.tmp',source);fs.renameSync(target+'.tmp',target);
   seen.set(hash,'Grading pending.');
   let result;
   try{result=await grade(source)}catch(error){
    log({type:'environment_error',error:String(error)});state({stop_reason:'public_grader_error',error:String(error)});throw error;
   }
   const publicPath=target.replace(/\.ts$/,'.public.json');
   fs.writeFileSync(publicPath+'.tmp',JSON.stringify(result,null,2));
   fs.renameSync(publicPath+'.tmp',publicPath);
   const feedback=JSON.stringify({submission,remaining:cfg.maxSubmissions-submission,
    compiled:result.compiled,types_pass:result.types_pass,
    checks:(result.checks||[]).map(c=>({...c,...(c.error?{error:String(c.error).slice(0,300)}:{})})),
    passed:result.passed,status:result.status,error:(result.error||'').slice(0,1000),
    type_error:(result.type_error||'').slice(0,1200),
    next:result.passed?'Public checks passed. Finish; hidden grading happens separately.':'Correct your code and submit the complete revised source. Do not install anything or access the internet.'});
   seen.set(hash,feedback);
   log({type:'submission',submission,source_hash:hash,public_passed:result.passed});
   state({public_passed:result.passed,stop_reason:result.status==='harness_error'?'public_grader_error':
    result.passed?'public_checks_passed':submission>=cfg.maxSubmissions?'submission_budget':null});
   return feedback;
  })
 }));
}
