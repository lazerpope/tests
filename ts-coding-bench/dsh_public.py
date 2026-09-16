"""Public specification examples/contracts. Never import private checks or answers here."""
PUBLIC = {
 'group-by': ('import {groupBy} from "./solution";const r:Record<string,number[]>=groupBy([4,7] as const,x=>String(x%2));',
  ['eq(exports.groupBy([4,7,8],x=>String(x%2)),{"0":[4,8],"1":[7]});', 'const r=exports.groupBy([9],()=>"constructor");assert(Object.hasOwn(r,"constructor"));eq(r.constructor,[9]);']),
 'merge-intervals': ('import {mergeIntervals} from "./solution";const r:[number,number][]=mergeIntervals([[2,5],[5,8]] as const);',
  ['eq(exports.mergeIntervals([[2,5],[5,8],[12,14]]),[[2,8],[12,14]]);', 'const a=Object.freeze([Object.freeze([2,5]),Object.freeze([4,9])]);eq(exports.mergeIntervals(a),[[2,9]]);']),
 'lru-cache': ('import {LRUCache} from "./solution";const c=new LRUCache<string,number>(2);c.set("p",3);const v:number|undefined=c.get("p");const n:number=c.size;',
  ['const c=new exports.LRUCache(2);c.set("p",3);c.set("q",4);eq(c.get("p"),3);c.set("r",5);eq(c.get("q"),undefined);eq(c.size,2);', 'throws(()=>new exports.LRUCache(0));']),
 'topological-sort': ('import {topologicalSort} from "./solution";const r:string[]=topologicalSort(["p","q"],[["p","q"]] as const);',
  ['eq(exports.topologicalSort(["r","q","p"],[["p","r"]]),["p","q","r"]);', 'throws(()=>exports.topologicalSort(["p","q"],[["p","q"],["q","p"]]));']),
 'parse-csv': ('import {parseCSV} from "./solution";const r:string[][]=parseCSV("red,blue");',
  ['eq(exports.parseCSV(\'red,"blue,green"\\n\'),[["red","blue,green"]]);', 'eq(exports.parseCSV(""),[]);throws(()=>exports.parseCSV(\'"unfinished\'));']),
 'json-merge-patch': ('import {mergePatch} from "./solution";const r:unknown=mergePatch({n:1},{n:null});',
  ['eq(exports.mergePatch({color:"red",n:2},{color:null,n:3}),{n:3});', 'const a={nested:{n:5}};const r=exports.mergePatch(a,{});eq(r,a);assert(r!==a&&r.nested!==a.nested);']),
 'concurrency-pool': ('import {mapLimit} from "./solution";const r:Promise<string[]>=mapLimit([3,6] as const,2,async(x,i)=>String(x+i));',
  ['eq(await exports.mapLimit([3,6,9],2,async(x,i)=>x+i),[3,7,11]);', 'let rejected=false;try{await exports.mapLimit([],0,async x=>x)}catch{rejected=true}assert(rejected);']),
 'retry': ('import {retry} from "./solution";const r:Promise<number>=retry(async n=>n,2,(e:unknown)=>true);',
  ['const seen=[];eq(await exports.retry(async n=>{seen.push(n);if(n<2)throw Error("again");return 17},3,()=>true),17);eq(seen,[1,2]);', 'let called=0;const original={message:"stop"};let caught;try{await exports.retry(()=>{throw original},1,()=>{called++;return true})}catch(e){caught=e}assert(caught===original);eq(called,0);']),
 'event-emitter': ('import {Emitter} from "./solution";const e=new Emitter<{value:number}>();const off:()=>void=e.on("value",n=>{const x:number=n});e.emit("value",5);',
  ['const e=new exports.Emitter();const got=[];const off=e.on("v",x=>got.push(x));e.emit("v",3);off();off();e.emit("v",4);eq(got,[3]);', 'const e=new exports.Emitter();let n=0;const fn=()=>n++;e.on("v",fn);e.on("v",fn);e.emit("v",0);eq(n,2);']),
 'binary-search-fix': ('import {lowerBound} from "./solution";const n:number=lowerBound([2,4,4,9] as const,4);',
  ['eq(exports.lowerBound([2,4,4,9],4),1);eq(exports.lowerBound([2,4,4,9],10),4);', 'eq(exports.lowerBound([],7),0);eq(exports.lowerBound([2,4],1),0);']),
 'query-parser': ('import {parseQuery} from "./solution";const r:Record<string,string[]>=parseQuery("?x=one");',
  ['eq(exports.parseQuery("?city=New+York&city=Rome&flag"),{city:["New York","Rome"],flag:[""]});', 'throws(()=>exports.parseQuery("x=%ZZ"));']),
 'immutable-update': ('import {setIn} from "./solution";const r:unknown=setIn({},["a",0] as const,8);',
  ['const root={x:{n:3},y:{n:7}};const r=exports.setIn(root,["x","n"],4);eq(r,{x:{n:4},y:{n:7}});assert(r.y===root.y);eq(root.x.n,3);', 'eq(exports.setIn(null,["items",0],8),{items:[8]});throws(()=>exports.setIn({},["prototype"],1));']),
 'result-types': ('import {Result,mapResult,unwrapOr} from "./solution";const a:Result<number,string>={ok:true,value:8};const b:Result<string,string>=mapResult<number,string,string>(a,String);const n:number=unwrapOr<number,string>(a,0);if(b.ok){const s:string=b.value}else{const s:string=b.error}',
  ['eq(exports.mapResult({ok:true,value:8},x=>x+2),{ok:true,value:10});eq(exports.unwrapOr({ok:false,error:"oops"},6),6);', 'const error={message:"keep"};const r=exports.mapResult({ok:false,error},()=>{throw Error("not called")});assert(r.error===error);']),
 'dependency-memo': ('import {memoizeAsync} from "./solution";const f:(k:string)=>Promise<number>=memoizeAsync(async(k:string)=>k.length);',
  ['let n=0;const f=exports.memoizeAsync(async x=>{n++;return x+4});const a=f(7);assert(a===f(7));eq(await a,11);eq(n,1);', 'const f=exports.memoizeAsync(()=>{throw Error("sync")});let p;try{p=f("x")}catch{assert(false,"must return a rejected promise")}let rejected=false;try{await p}catch{rejected=true}assert(rejected);']),
 'path-normalize': ('import {normalizePath} from "./solution";const r:string=normalizePath("/home/../tmp");',
  ['eq(exports.normalizePath("/home//./user/../tmp/"),"/home/tmp");', 'eq(exports.normalizePath("../../src/.."),"../..");eq(exports.normalizePath(""),".");']),
 'typed-pick': ('import {pick} from "./solution";const r:{x:number}=pick({x:2,y:"q"},["x"] as const);',
  ['const a={x:2,y:3};eq(exports.pick(a,["y"]),{y:3});eq(a,{x:2,y:3});', 'const s=Symbol("s");const a=Object.create({inherited:4});a[s]=7;const r=exports.pick(a,[s,"inherited"]);eq(r[s],7);assert(!Object.hasOwn(r,"inherited"));']),
}


def public_task(task_id):
    types, tests = PUBLIC[task_id]
    return {'types': types, 'tests': tests}
