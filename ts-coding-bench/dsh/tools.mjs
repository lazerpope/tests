// Trusted DSH plugin: the only model tools. Every command runs in Docker.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(process.env.BENCH_DSH_BIN);
const {defineTool}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-tools')).href);
const cfg=JSON.parse(fs.readFileSync(process.env.BENCH_TOOL_CONFIG,'utf8'));
let count=0,submission=0,chain=Promise.resolve();
const log=record=>fs.appendFileSync(cfg.log,JSON.stringify({at:new Date().toISOString(),...record})+'\n');
function docker(args,input){
 return new Promise((resolve,reject)=>{
  const child=execFile(cfg.docker,args,{timeout:45000,maxBuffer:300000,encoding:'utf8',windowsHide:true},(err,stdout,stderr)=>{
   if(err?.killed||err?.code==='ERR_CHILD_PROCESS_STDIO_MAXBUFFER')reject(Error('Tool process timed out or output overflowed'));
   else resolve({code:err?.code||0,stdout,stderr});
  });
  child.stdin.on('error',()=>{});
  child.stdin.end(input||'');
 });
}
function serial(fn){
 const p=chain.then(async()=>{
  if(count>=cfg.maxCalls||Date.now()>=cfg.deadline){log({type:'budget_exhausted'});throw Error('Tool-call/time budget exhausted. Finish now.')}
  count++;return fn();
 });
 chain=p.catch(()=>{});return p;
}
export const name='bench-isolated-tools';
export const inject=['tools'];
export function apply(ctx){
 const output={schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]};
 ctx.tools.register(defineTool({
  name:'bash',
  description:'Run bash inside the isolated task container, starting in /workspace each call. Files persist; shell variables do not. No network or host files. Write solution.ts, inspect TASK.md and public-checks.json, and use tsc. Call submit for trusted public feedback.',
  parameters:{command:{type:'string',required:true,description:'Bash command; at most 20 seconds and 12000 output characters.'}},
  output,
  execute:args=>serial(async()=>{
   if(typeof args.command!=='string'||args.command.length>30000)throw Error('Invalid command');
   log({type:'tool_start',tool:'bash',call:count,command:args.command});
   const r=await docker(['exec','--workdir','/workspace',cfg.container,'/usr/bin/timeout','-k','1','20','/bin/bash','--noprofile','--norc','-c',args.command]);
   log({type:'tool_end',tool:'bash',call:count,code:r.code});
   return ('Exit '+r.code+'\n'+r.stdout+r.stderr).slice(0,12000);
  })
 }));
 ctx.tools.register(defineTool({
  name:'submit',
  description:'Save the current solution.ts as a submission and run trusted strict compilation plus public examples. You may repair and submit again. No private tests or reference answers are returned. Submit at least once before your final reply.',
  parameters:{},output,
  execute:()=>serial(async()=>{
   log({type:'tool_start',tool:'submit',call:count});
   const source=await docker(['exec',cfg.container,'/usr/local/bin/node','/opt/bench/extract.cjs']);
   if(source.code!==0)throw Error('Cannot submit: '+source.stderr.slice(0,1000));
   submission++;
   const target=path.join(cfg.snapshots,String(submission).padStart(3,'0')+'.ts');
   fs.writeFileSync(target+'.tmp',source.stdout);
   fs.renameSync(target+'.tmp',target);
   // A fresh no-network container grades public examples only. Agent edits to
   // its public-checks.json or package scripts cannot alter this feedback.
   const publicResult=await docker(['run','--rm','-i','--name',cfg.publicContainer,
    '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
    '--pids-limit','64','--memory','512m','--cpus','1','--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
    cfg.image,'/usr/local/bin/node','/opt/bench/grade.cjs'],
    JSON.stringify({source:source.stdout,types:'',tests:cfg.publicTests}));
   log({type:'submission',submission,call:count});
   if(publicResult.code!==0)throw Error('Public grader failed: '+publicResult.stderr.slice(0,1000));
   return 'Submission '+submission+'\n'+publicResult.stdout.slice(0,12000);
  })
 }));
}
