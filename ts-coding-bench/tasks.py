"""Original TypeScript tasks. Reference solutions and checks are never sent to models."""
TASKS = []
def task(id, category, prompt, reference, tests, types=''):
    TASKS.append(dict(id=id, category=category, prompt=prompt, reference=reference, tests=tests, types=types))

task('group-by','generics',
'''Export function groupBy<T>(items: readonly T[], key: (item:T)=>string): Record<string,T[]>.
Preserve order within groups, support arbitrary keys including __proto__ and constructor, and do not mutate inputs.''',
'''export function groupBy<T>(items:readonly T[],key:(item:T)=>string):Record<string,T[]> {const out:Record<string,T[]>=Object.create(null);for(const x of items)(out[key(x)]??=[]).push(x);return out;}''',
['eq(Object.keys(exports.groupBy([],x=>x)),[]);',
 'const xs=Object.freeze([1,2,3,4]);const g=exports.groupBy(xs,x=>String(x%2));eq(g["1"],[1,3]);eq(g["0"],[2,4]);',
 'const g=exports.groupBy(["a","b"],()=>"__proto__");eq(g["__proto__"],["a","b"]);eq(exports.groupBy([1],()=>"constructor")["constructor"],[1]);'],
'''import {groupBy} from './solution'; const g:Record<string,number[]>=groupBy([1,2] as const,x=>String(x));
// @ts-expect-error callback must accept a number
groupBy([1],(x:string)=>x);''')

task('merge-intervals','algorithms',
'''Export mergeIntervals(items: readonly (readonly [number,number])[]): [number,number][]. Merge overlapping or touching closed intervals, sorted ascending; do not mutate input. Each start <= end.''',
'''export function mergeIntervals(items:readonly (readonly [number,number])[]):[number,number][]{const out:[number,number][]=[];for(const [s,e] of [...items].sort((a,b)=>a[0]-b[0])){const last=out[out.length-1];if(last&&s<=last[1])last[1]=Math.max(last[1],e);else out.push([s,e]);}return out;}''',
['eq(exports.mergeIntervals([]),[]);','eq(exports.mergeIntervals([[5,7],[1,3],[3,6],[10,10]]),[[1,7],[10,10]]);',
 'const a=Object.freeze([Object.freeze([1,9]),Object.freeze([2,3]),Object.freeze([-5,-2])]);eq(exports.mergeIntervals(a),[[-5,-2],[1,9]]);'])

task('lru-cache','data-structures',
'''Export class LRUCache<K,V> with constructor(capacity:number), get(key:K):V|undefined, set(key:K,value:V):void, and readonly size:number. get and set refresh recency; evict least recent on overflow. Capacity must be a positive integer or throw RangeError. Use O(1) get/set.''',
'''export class LRUCache<K,V>{private m=new Map<K,V>();constructor(private capacity:number){if(!Number.isInteger(capacity)||capacity<1)throw new RangeError();}get size(){return this.m.size;}get(k:K):V|undefined{if(!this.m.has(k))return undefined;const v=this.m.get(k)!;this.m.delete(k);this.m.set(k,v);return v;}set(k:K,v:V){this.m.delete(k);this.m.set(k,v);if(this.m.size>this.capacity)this.m.delete(this.m.keys().next().value!);}}''',
['for(const n of [0,-1,1.5,NaN,Infinity])throws(()=>new exports.LRUCache(n));',
 'const c=new exports.LRUCache(2);c.set("a",1);c.set("b",2);eq(c.get("a"),1);c.set("c",3);assert(c.get("b")===undefined);eq(c.size,2);',
 'const c=new exports.LRUCache(2);c.set("a",undefined);c.set("b",2);c.get("a");c.set("c",3);assert(c.get("b")===undefined);c.set("c",4);eq(c.size,2);eq(c.get("c"),4);'],
'''import {LRUCache} from './solution';const c=new LRUCache<string,number>(2);c.set('x',1);const n:number|undefined=c.get('x');
// @ts-expect-error wrong value
c.set('x','wrong');
// @ts-expect-error readonly
c.size=1;''')

task('topological-sort','algorithms',
'''Export topologicalSort(nodes: readonly string[], edges: readonly (readonly [string,string])[]):string[]. An edge [a,b] means a must precede b. Throw on unknown endpoints, duplicate nodes, or cycles. Duplicate edges count once. Choose the lexicographically smallest available node at each step (JS default string sort).''',
'''export function topologicalSort(nodes:readonly string[],edges:readonly (readonly [string,string])[]):string[]{const adj=new Map(nodes.map(n=>[n,new Set<string>()]));if(adj.size!==nodes.length)throw Error();const deg=new Map(nodes.map(n=>[n,0]));for(const [a,b]of edges){if(!adj.has(a)||!adj.has(b))throw Error();if(!adj.get(a)!.has(b)){adj.get(a)!.add(b);deg.set(b,deg.get(b)!+1);}}const ready=nodes.filter(n=>deg.get(n)===0).sort(),out:string[]=[];while(ready.length){const n=ready.shift()!;out.push(n);for(const b of adj.get(n)!){deg.set(b,deg.get(b)!-1);if(!deg.get(b)){ready.push(b);ready.sort();}}}if(out.length!==nodes.length)throw Error();return out;}''',
['eq(exports.topologicalSort([],[]),[]);eq(exports.topologicalSort(["z","a","b"],[]),["a","b","z"]);',
 'eq(exports.topologicalSort(["c","b","a"],[["a","c"],["a","c"]]),["a","b","c"]);',
 'throws(()=>exports.topologicalSort(["a","b"],[["a","b"],["b","a"]]));throws(()=>exports.topologicalSort(["a"],[["a","x"]]));throws(()=>exports.topologicalSort(["a","a"],[]));'])

task('parse-csv','parsing',
'''Export parseCSV(text:string):string[][]. Comma-separated fields; LF or CRLF ends a row outside quotes. A quoted field may contain commas, newlines, and doubled quotes representing one quote. Preserve whitespace and quoted CRLF exactly. Reject unclosed quotes, quotes in unquoted fields, or characters after closing quote other than delimiter/newline/end. Empty input returns []; final newline does not add a row; a blank line is [''].''',
'''export function parseCSV(text:string):string[][]{if(!text)return [];const rows:string[][]=[];let row:string[]=[],field='',state=0;for(let i=0;i<text.length;i++){const c=text[i];if(state===1){if(c==='"'){if(text[i+1]==='"'){field+='"';i++;}else state=2;}else field+=c;continue;}if(c===','||c==='\\n'||(c==='\\r'&&text[i+1]==='\\n')){row.push(field);field='';state=0;if(c!==','){rows.push(row);row=[];if(c==='\\r')i++;}continue;}if(state===2)throw Error();if(c==='"'){if(field!=='')throw Error();state=1;}else field+=c;}if(state===1)throw Error();if(row.length||field!==''||state===2||!text.endsWith('\\n')){row.push(field);rows.push(row);}return rows;}''',
['eq(exports.parseCSV(""),[]);eq(exports.parseCSV("a,b\\r\\n1,2\\r\\n"),[["a","b"],["1","2"]]);',
 r'''eq(exports.parseCSV('"a,b","c""d"\n"x\ny",z'),[['a,b','c"d'],['x\ny','z']]);''',
 r'''eq(exports.parseCSV(",\n\n"),[["",""],[""]]);eq(exports.parseCSV("a,"),[["a",""]]);eq(exports.parseCSV('"a\r\nb"'),[["a\r\nb"]]);''',
 '''for(const s of ['"abc','a"b','"a"x'])throws(()=>exports.parseCSV(s));'''])

task('json-merge-patch','data-transformation',
'''Export mergePatch(target:unknown, patch:unknown):unknown. JSON merge patch: non-object or array patch replaces target; object patch recursively merges into object target (or {} if target is not an object), null-valued properties delete keys. Inputs contain only JSON values. Deep-copy output; never mutate or share nested objects with inputs. Handle __proto__ as an own data property.''',
'''const obj=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);const copy=(v:unknown):unknown=>JSON.parse(JSON.stringify(v));export function mergePatch(target:unknown,patch:unknown):unknown{if(!obj(patch))return copy(patch);const out:Record<string,unknown>=Object.create(null);if(obj(target))for(const k of Object.keys(target))out[k]=copy(target[k]);for(const k of Object.keys(patch)){if(patch[k]===null)delete out[k];else out[k]=mergePatch(out[k]??null,patch[k]);}return out;}''',
['eq(exports.mergePatch({a:1,b:2},{a:null,c:3}),{b:2,c:3});eq(exports.mergePatch([1],{x:2}),{x:2});eq(exports.mergePatch({a:1},[2]),[2]);',
 'const t={x:{a:1},y:[1]},p={x:{b:2}};const r=exports.mergePatch(t,p);eq(r,{x:{a:1,b:2},y:[1]});r.x.a=9;r.y.push(2);eq(t,{x:{a:1},y:[1]});eq(p,{x:{b:2}});',
 '''const r=exports.mergePatch({},JSON.parse('{"__proto__":{"polluted":true}}'));assert(Object.hasOwn(r,"__proto__"));assert(({}).polluted===undefined);'''])

task('concurrency-pool','async',
'''Export async function mapLimit<T,R>(items:readonly T[], limit:number, fn:(item:T,index:number)=>Promise<R>):Promise<R[]>.
Run at most limit callbacks concurrently, preserve result order, reject if any callback fails. Throw/reject RangeError for non-positive or non-integer limit even for empty input. Do not mutate items.''',
'''export async function mapLimit<T,R>(items:readonly T[],limit:number,fn:(item:T,index:number)=>Promise<R>):Promise<R[]>{if(!Number.isInteger(limit)||limit<1)throw new RangeError();const out:R[]=[];let next=0;async function worker(){while(next<items.length){const i=next++;out[i]=await fn(items[i],i);}}await Promise.all(Array.from({length:Math.min(limit,items.length)},worker));return out;}''',
['eq(await exports.mapLimit([],2,async x=>x),[]);for(const n of [0,-1,1.2]){let ok=false;try{await exports.mapLimit([],n,async x=>x)}catch{ok=true}assert(ok);}',
 'let active=0,peak=0;const xs=Object.freeze([3,1,2,4]);const r=await exports.mapLimit(xs,2,async(x,i)=>{active++;peak=Math.max(peak,active);for(let j=0;j<x;j++)await Promise.resolve();active--;return x+i;});eq(r,[3,2,4,7]);eq(peak,2);',
 'let ok=false;try{await exports.mapLimit([1,2],1,async x=>{throw Error("bad")})}catch{ok=true}assert(ok);'],
'''import {mapLimit} from './solution';const r:Promise<string[]>=mapLimit([1],1,async n=>String(n));
// @ts-expect-error invalid callback argument
mapLimit([1],1,async (n:string)=>n);''')

task('retry','async',
'''Export retry<T>(operation:(attempt:number)=>Promise<T>, maxAttempts:number, shouldRetry:(error:unknown)=>boolean):Promise<T>. Attempts are 1-based. Validate positive integer maxAttempts before calling operation. Stop at first success, when predicate returns false, or at maxAttempts. Rethrow the original last error. Do not call shouldRetry after the final allowed attempt. Also handle synchronous operation throws.''',
'''export async function retry<T>(operation:(attempt:number)=>Promise<T>,maxAttempts:number,shouldRetry:(error:unknown)=>boolean):Promise<T>{if(!Number.isInteger(maxAttempts)||maxAttempts<1)throw new RangeError();for(let a=1;;a++){try{return await operation(a);}catch(e){if(a>=maxAttempts||!shouldRetry(e))throw e;}}}''',
['let a=[];eq(await exports.retry(async n=>{a.push(n);if(n<3)throw Error();return 7;},3,()=>true),7);eq(a,[1,2,3]);',
 'const err={x:1};let p=0;let caught=false;try{await exports.retry(()=>{throw err},2,()=>{p++;return true})}catch(e){caught=true;assert(e===err)}assert(caught);eq(p,1);',
 'let count=0;try{await exports.retry(async()=>{count++;throw Error()},4,()=>false)}catch{}eq(count,1);for(const n of [0,1.2]){let ok=false;try{await exports.retry(async()=>{count++;},n,()=>true)}catch{ok=true}assert(ok)}eq(count,1);'])

task('event-emitter','api-design',
'''Export class Emitter<E extends Record<string,unknown>> with on<K extends keyof E>(event:K, listener:(payload:E[K])=>void):()=>void and emit<K extends keyof E>(event:K,payload:E[K]):void. Listeners run in registration order. Each registration is independent even for identical callbacks. Unsubscribe is idempotent. emit uses a snapshot: changes during emit affect only later emits. Listener errors propagate.''',
'''export class Emitter<E extends Record<string,unknown>>{private events=new Map<keyof E,Array<{fn:(p:any)=>void}>>();on<K extends keyof E>(event:K,listener:(payload:E[K])=>void):()=>void{const entry={fn:listener};const list=this.events.get(event)??[];list.push(entry);this.events.set(event,list);return()=>{const i=list.indexOf(entry);if(i>=0)list.splice(i,1);};}emit<K extends keyof E>(event:K,payload:E[K]):void{for(const x of [...(this.events.get(event)??[])])x.fn(payload);}}''',
['const e=new exports.Emitter();const got=[];const f=x=>got.push(x);const off=e.on("x",f);e.on("x",f);e.emit("x",1);off();off();e.emit("x",2);eq(got,[1,1,2]);',
 'const e=new exports.Emitter();let got=[];let off=()=>{};e.on("x",()=>{got.push("a");off();e.on("x",()=>got.push("c"));});off=e.on("x",()=>got.push("b"));e.emit("x",0);eq(got,["a","b"]);got=[];e.emit("x",0);eq(got,["a","c"]);'],
'''import {Emitter} from './solution';const e=new Emitter<{done:number}>();e.on('done',n=>n.toFixed());e.emit('done',1);
// @ts-expect-error wrong payload
e.emit('done','x');
// @ts-expect-error unknown event
e.emit('missing',1);''')

task('binary-search-fix','bug-fixing',
'''Fix and export lowerBound(xs:readonly number[],target:number):number. Return the first index i with xs[i]>=target, or length if absent. Sorted ascending input, duplicates allowed. O(log n), no mutation. Buggy code: function lowerBound(xs:number[],target:number){let lo=0,hi=xs.length-1;while(lo<hi){const m=(lo+hi)>>1;if(xs[m]<=target)lo=m;else hi=m-1;}return lo;}''',
'''export function lowerBound(xs:readonly number[],target:number):number{let lo=0,hi=xs.length;while(lo<hi){const m=lo+Math.floor((hi-lo)/2);if(xs[m]<target)lo=m+1;else hi=m;}return lo;}''',
['eq(exports.lowerBound([],3),0);eq(exports.lowerBound([1],2),1);eq(exports.lowerBound([1],1),0);',
 'for(let n=0;n<80;n++){const xs=Object.freeze(Array.from({length:n},(_,i)=>Math.floor(i/3)-5));for(let t=-7;t<30;t++){const found=xs.findIndex(x=>x>=t);eq(exports.lowerBound(xs,t),found<0?n:found);}}'])

task('query-parser','web-utilities',
'''Export parseQuery(query:string):Record<string,string[]>. Strip at most one leading ?. Split on &, skip empty segments, split each segment on first = only; missing value becomes empty string. Decode percent escapes and + as space in keys and values. Preserve duplicate value order. Throw URIError on invalid percent encoding; handle arbitrary property names safely.''',
'''export function parseQuery(query:string):Record<string,string[]>{const out:Record<string,string[]>=Object.create(null);const dec=(s:string)=>decodeURIComponent(s.replace(/\\+/g,' '));for(const s of (query.startsWith('?')?query.slice(1):query).split('&')){if(!s)continue;const i=s.indexOf('=');const k=dec(i<0?s:s.slice(0,i)),v=dec(i<0?'':s.slice(i+1));(out[k]??=[]).push(v);}return out;}''',
['eq(exports.parseQuery("?a=1&a=2&x=a=b&flag"),{a:["1","2"],x:["a=b"],flag:[""]});eq(exports.parseQuery("&&"),{});',
 'eq(exports.parseQuery("a+b=%E2%9C%93+ok&=v"),{"a b":["✓ ok"],"":["v"]});throws(()=>exports.parseQuery("x=%ZZ"));',
 'eq(exports.parseQuery("__proto__=a&constructor=b")["__proto__"],["a"]);'])

task('immutable-update','bug-fixing',
'''Export setIn(root:unknown,path:readonly (string|number)[],value:unknown):unknown. Immutably replace a nested value. Empty path returns value. Clone only containers along path, preserve other references. Existing containers are plain objects or arrays. Missing/null/primitive containers become [] for nonnegative integer numeric key, {} for string key. Reject negative/fractional numeric keys and __proto__, prototype, constructor anywhere in path. Do not mutate inputs.''',
'''export function setIn(root:unknown,path:readonly (string|number)[],value:unknown):unknown{for(const k of path)if(typeof k==='number'?(!Number.isInteger(k)||k<0):['__proto__','prototype','constructor'].includes(k))throw Error();function go(node:any,i:number):any{if(i===path.length)return value;const k=path[i];const out:any=Array.isArray(node)?node.slice():node!==null&&typeof node==='object'?{...node}:typeof k==='number'?[]:{};out[k]=go(node!==null&&typeof node==='object'?node[k]:undefined,i+1);return out;}return go(root,0);}''',
['const root={a:{x:1},b:{y:2}};const r=exports.setIn(root,["a","x"],9);eq(r,{a:{x:9},b:{y:2}});assert(r!==root&&r.a!==root.a&&r.b===root.b);eq(root.a.x,1);',
 'eq(exports.setIn(null,["a",0,"x"],3),{a:[{x:3}]});eq(exports.setIn({},[],7),7);const a=[1,2];eq(exports.setIn(a,[1],4),[1,4]);eq(a,[1,2]);',
 'for(const p of [["__proto__"],["x","constructor"],[-1],[0.5]])throws(()=>exports.setIn({},p,1));'])

task('result-types','type-safety',
'''Export type Result<T,E> = {ok:true,value:T}|{ok:false,error:E}; export mapResult<A,B,E>(r:Result<A,E>,fn:(a:A)=>B):Result<B,E>; export unwrapOr<T,E>(r:Result<T,E>,fallback:T):T. Transform only successes; propagate errors unchanged. Preserve discriminated-union narrowing and generic types.''',
'''export type Result<T,E>={ok:true,value:T}|{ok:false,error:E};export function mapResult<A,B,E>(r:Result<A,E>,fn:(a:A)=>B):Result<B,E>{return r.ok?{ok:true,value:fn(r.value)}:r;}export function unwrapOr<T,E>(r:Result<T,E>,fallback:T):T{return r.ok?r.value:fallback;}''',
['eq(exports.mapResult({ok:true,value:2},x=>String(x)),{ok:true,value:"2"});const error={message:"bad"};const e={ok:false,error};const mapped=exports.mapResult(e,()=>{throw Error("must not map an error")});eq(mapped,{ok:false,error});assert(mapped.error===error,"preserve the error value; copying the result wrapper is allowed");',
 'eq(exports.unwrapOr({ok:true,value:0},9),0);eq(exports.unwrapOr({ok:false,error:"e"},9),9);'],
'''import {Result,mapResult,unwrapOr} from './solution';const r:Result<number,string>={ok:true,value:2};const m:Result<string,string>=mapResult<number,string,string>(r,String);if(m.ok){const v:string=m.value;
// @ts-expect-error errors are absent on successes
m.error;
}else{const e:string=m.error;}
// @ts-expect-error invalid discriminant
const bad:Result<number,string>={ok:'yes',value:1};
// @ts-expect-error incompatible callback
mapResult(r,(x:boolean)=>x);''')

task('dependency-memo','async',
'''Export memoizeAsync<K,V>(fn:(key:K)=>Promise<V>):(key:K)=>Promise<V>. Share the exact same in-flight promise for equal keys (Map equality). Cache successful promises. Evict rejected promises so a later call retries. Handle synchronous throws by returning a rejected promise, never throwing synchronously.''',
'''export function memoizeAsync<K,V>(fn:(key:K)=>Promise<V>):(key:K)=>Promise<V>{const cache=new Map<K,Promise<V>>();return k=>{const old=cache.get(k);if(old)return old;const p=Promise.resolve().then(()=>fn(k));cache.set(k,p);p.catch(()=>{if(cache.get(k)===p)cache.delete(k);});return p;};}''',
['let calls=0;const f=exports.memoizeAsync(async x=>{calls++;return x*2;});const a=f(2),b=f(2);assert(a===b);eq(await a,4);assert(f(2)===a);eq(calls,1);eq(await f(3),6);',
 'let n=0;const f=exports.memoizeAsync(()=>{if(++n===1)throw Error("first");return Promise.resolve(7);});let p;try{p=f("x")}catch{assert(false,"synchronous throw")}let rejected=false;try{await p}catch{rejected=true}assert(rejected);eq(await f("x"),7);eq(n,2);'])

task('path-normalize','parsing',
'''Export normalizePath(path:string):string for POSIX paths. Collapse repeated /, remove . segments, resolve .. against a preceding normal segment. Absolute paths cannot go above root. Relative paths preserve unresolved leading .. . Remove trailing slash except root. Empty normalized relative path is '.'. Treat backslashes as ordinary characters.''',
'''export function normalizePath(path:string):string{const abs=path.startsWith('/'),out:string[]=[];for(const s of path.split('/')){if(!s||s==='.')continue;if(s==='..'){if(out.length&&out[out.length-1]!=='..')out.pop();else if(!abs)out.push(s);}else out.push(s);}return (abs?'/':'')+out.join('/')||(abs?'/':'.');}''',
['eq(exports.normalizePath("/a//b/../c/"),"/a/c");eq(exports.normalizePath("/../../a"),"/a");eq(exports.normalizePath(""),".");',
 r'eq(exports.normalizePath("../../a/../b"),"../../b");eq(exports.normalizePath("a/.."),".");eq(exports.normalizePath("///"),"/");eq(exports.normalizePath("a\\b"),"a\\b");'])

task('typed-pick','type-safety',
'''Export pick<T extends object,K extends keyof T>(object:T, keys:readonly K[]):Pick<T,K>. Copy only requested own properties, ignore inherited ones, preserve values and support symbols. Handle __proto__ safely. Do not mutate input.''',
'''export function pick<T extends object,K extends keyof T>(object:T,keys:readonly K[]):Pick<T,K>{const out=Object.create(null);for(const k of keys)if(Object.prototype.hasOwnProperty.call(object,k))Object.defineProperty(out,k,{value:object[k],enumerable:true,writable:true,configurable:true});return out;}''',
['const x={a:1,b:2};eq(exports.pick(x,["a"]),{a:1});eq(x,{a:1,b:2});',
 'const s=Symbol("x"),o=Object.create({a:1});o[s]=9;o.b=2;const r=exports.pick(o,["a","b",s]);assert(!Object.hasOwn(r,"a"));eq(r[s],9);eq(r.b,2);',
 '''const o=JSON.parse('{"__proto__":3}');const r=exports.pick(o,["__proto__"]);assert(Object.hasOwn(r,"__proto__"));eq(r["__proto__"],3);'''],
'''import {pick} from './solution';const p=pick({a:1,b:'x'},['a'] as const);const n:number=p.a;
// @ts-expect-error omitted key
p.b;
// @ts-expect-error unknown key
pick({a:1},['b']);''')
