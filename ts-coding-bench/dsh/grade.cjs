// Trusted grader entry. Receives source + checks on stdin in a fresh container.
const fs=require('node:fs'),cp=require('node:child_process');
let text='';
process.stdin.setEncoding('utf8');
process.stdin.on('data',chunk=>{text+=chunk;if(text.length>2000000)process.exit(2)});
process.stdin.on('end',()=>{
 const result={compiled:false,types_pass:null,checks:[],passed:false};
 try{
  const input=JSON.parse(text),root='/tmp/grading';
  if(typeof input.source!=='string'||input.source.length>262144)throw Error('Invalid source');
  if(/@ts-(?:nocheck|ignore|expect-error)|\/\/\/\s*<reference/.test(input.source)){
   process.stdout.write(JSON.stringify({...result,status:'invalid_output',error:'Compiler suppression/reference directives are forbidden.'}));return;
  }
  fs.mkdirSync(root,{recursive:true});
  fs.writeFileSync(root+'/solution.ts',input.source);
  fs.writeFileSync(root+'/typechecks.ts',input.types||'');
  fs.writeFileSync(root+'/checks.json',JSON.stringify(input.tests||[]));
  const flags=['--strict','--target','ES2022','--module','commonjs','--lib','ES2022','--skipLibCheck','--noEmitOnError','--pretty','false'];
  function compile(extra){return cp.spawnSync('/usr/local/bin/node',['/opt/compiler/node_modules/typescript/bin/tsc',...flags,...extra],{cwd:root,encoding:'utf8',timeout:20000,maxBuffer:100000})}
  const c=compile(['solution.ts']);
  result.compile_log=(c.stdout||'')+(c.stderr||'');
  if(c.error)throw c.error;
  if(c.status!==0){process.stdout.write(JSON.stringify({...result,status:'compile_error',error:result.compile_log}));return}
  result.compiled=true;
  if(input.types){
   const t=compile(['--noEmit','solution.ts','typechecks.ts']);
   if(t.error)throw t.error;
   result.types_pass=t.status===0;result.type_error=(t.stdout||'')+(t.stderr||'');
  }
  const c2=cp.spawnSync('/usr/local/bin/node',['--permission','--allow-fs-read='+root,'--allow-fs-read=/opt/bench/evaluate.cjs','--max-old-space-size=128','/opt/bench/evaluate.cjs',root+'/solution.js',root+'/checks.json'],{encoding:'utf8',timeout:12000,maxBuffer:100000});
  if(c2.error||c2.status!==0||!c2.stdout.trim()){
   result.status=c2.error?.code==='ETIMEDOUT'?'execution_timeout':'runtime_error';
   result.error=String(c2.error||c2.stderr||'Candidate did not finish its asynchronous work.');
  }else{
   result.checks=JSON.parse(c2.stdout);
   if(!Array.isArray(result.checks)||result.checks.length!==(input.tests||[]).length)throw Error('Invalid evaluator response');
   result.passed=result.checks.every(c=>c.pass===true)&&result.types_pass!==false;
   result.status=result.passed?'pass':'test_failure';
  }
 }catch(e){result.status='harness_error';result.error=String(e)}
 process.stdout.write(JSON.stringify(result));
});
