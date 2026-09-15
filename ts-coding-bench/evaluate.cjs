// Defense in depth for locally generated code; not a hostile-code security boundary.
const fs = require('node:fs');
const vm = require('node:vm');
const [candidate, tests] = process.argv.slice(2);
const context = vm.createContext({}, {codeGeneration:{strings:false,wasm:false}});
vm.runInContext("const exports = {}; const module = {exports};" +
  "const console = {log(){},warn(){},error(){}};" +
  "function assert(v,m='assertion failed'){if(!v)throw new Error(m)}" +
  "function same(a,b){if(Object.is(a,b))return true;if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;if(Array.isArray(a)&&a.length!==b.length)return false;const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();return JSON.stringify(ak)===JSON.stringify(bk)&&ak.every(k=>same(a[k],b[k]));}" +
  "function eq(a,b){assert(same(a,b),'expected '+JSON.stringify(b)+' got '+JSON.stringify(a))}" +
  "function throws(fn){let ok=false;try{fn()}catch{ok=true}assert(ok,'expected throw')}", context);
try {
  vm.runInContext(fs.readFileSync(candidate,'utf8'),context,{timeout:2000});
  const checks = JSON.parse(fs.readFileSync(tests,'utf8'));
  (async()=>{
    const results=[];
    for (const check of checks) {
      try {
        await vm.runInContext('(async()=>{'+check+'})()',context,{timeout:2000});
        results.push({pass:true});
      } catch(e) {results.push({pass:false,error:String(e).slice(0,2000)});}
    }
    process.stdout.write(JSON.stringify(results));
  })().catch(e=>{process.stderr.write(String(e));process.exitCode=1});
} catch(e) {process.stderr.write(String(e));process.exitCode=1;}
