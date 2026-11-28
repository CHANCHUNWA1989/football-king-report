import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,openSync,closeSync,fsyncSync,linkSync,unlinkSync,mkdirSync,rmdirSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const ZERO='0'.repeat(64), MAX_RECORDS=10000, MAX_BYTES=65536;
const FLAGS={release:'HOLD',production_recommendations:'DISABLED',certified:false};
const hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const token=x=>typeof x==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/.test(x);
const require=(ok,reason)=>{if(!ok)throw Error(reason);};
function exact(x,keys){return x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).length===keys.length&&keys.every(k=>Object.hasOwn(x,k));}
function canonical(x){
 if(x===null||typeof x==='boolean'||typeof x==='string'||(typeof x==='number'&&Number.isFinite(x)))return JSON.stringify(x);
 if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';
 require(x&&typeof x==='object'&&Object.getPrototypeOf(x)===Object.prototype,'INVALID_CANONICAL_OBJECT');
 return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';
}
export const digest=x=>createHash('sha256').update(canonical(x)).digest('hex');
function utc(x){
 require(typeof x==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(x),'UTC_REQUIRED');
 const t=Date.parse(x);require(Number.isFinite(t)&&new Date(t).toISOString().replace('.000Z','Z')===x,'INVALID_UTC');return t;
}
export function validate(x){
 require(exact(x,['kind','fixture','kickoff','sealed','forecast','featureCutoff','modelId','modelSha256','featureSha256','sources','release','production_recommendations']),'CANDIDATE_SCHEMA');
 require(x.kind==='candidate'&&token(x.fixture)&&token(x.modelId)&&x.release==='HOLD'&&x.production_recommendations==='DISABLED','CANDIDATE_FLAGS');
 const kickoff=utc(x.kickoff),sealed=utc(x.sealed),cutoff=utc(x.featureCutoff);
 require(cutoff<=sealed&&sealed<kickoff,'TIME_ORDER');
 require(hex(x.modelSha256)&&hex(x.featureSha256),'MODEL_FEATURE_HASH_REQUIRED');
 require(Array.isArray(x.forecast)&&x.forecast.length===3&&x.forecast.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)&&Math.abs(x.forecast.reduce((s,v)=>s+v,0)-1)<=1e-8,'INVALID_PROBABILITIES');
 require(Array.isArray(x.sources)&&x.sources.length===2,'TWO_SOURCE_REQUIRED');
 for(const s of x.sources){
  require(exact(s,['publisher','upstream','role','fixture','kickoff','observed','bodySha256','licence']),'SOURCE_SCHEMA');
  require(token(s.publisher)&&token(s.upstream)&&['official','independent'].includes(s.role)&&s.fixture===x.fixture&&s.kickoff===x.kickoff&&hex(s.bodySha256)&&s.licence==='research-review-required','SOURCE_METADATA');
  require(utc(s.observed)<=cutoff,'SOURCE_AFTER_FEATURE_CUTOFF');
 }
 const norm=v=>v.toLowerCase();
 require(new Set(x.sources.map(s=>norm(s.publisher))).size===2&&new Set(x.sources.map(s=>norm(s.upstream))).size===2&&new Set(x.sources.map(s=>s.role)).size===2,'SOURCE_INDEPENDENCE_SHAPE');
 return {...FLAGS,classification:'UNAUTHENTICATED_CANDIDATE',externalTimestampVerified:false,sourceAuthenticityVerified:false};
}
function stateDir(dir){
 const p=resolve(dir);require(p===realpathSync(p)&&p!==ROOT&&!p.startsWith(ROOT+'/'),'STATE_OUTSIDE_REPO_REQUIRED');
 const s=lstatSync(p);require(s.isDirectory()&&(s.mode&0o077)===0&&s.uid===process.getuid(),'PRIVATE_STATE_DIRECTORY_REQUIRED');return p;
}
function readRecord(path){
 const s=lstatSync(path);require(s.isFile()&&!s.isSymbolicLink()&&s.nlink===1&&s.uid===process.getuid()&&(s.mode&0o077)===0&&s.size<=MAX_BYTES,'UNSAFE_RECORD');
 return JSON.parse(readFileSync(path,'utf8'));
}
function name(i){return String(i).padStart(8,'0')+'.json';}
function scan(dir,anchor,locked=false){
 const files=readdirSync(dir).filter(n=>!(locked&&n==='.append-lock')).sort();
 require(files.length<=MAX_RECORDS,'CHAIN_LIMIT');
 require(anchor===null?files.length===0:exact(anchor,['count','tip'])&&Number.isInteger(anchor.count)&&anchor.count===files.length&&hex(anchor.tip),'ANCHOR_COUNT_MISMATCH');
 let prev=ZERO;const seen=new Set();
 for(let i=0;i<files.length;i++){
  require(files[i]===name(i+1),'CHAIN_SEQUENCE');
  const rec=readRecord(join(dir,files[i]));
  require(exact(rec,['seq','prev','payload','hash'])&&rec.seq===i+1&&rec.prev===prev&&hex(rec.hash),'CHAIN_LINK');
  validate(rec.payload);const id=rec.payload.fixture.toLowerCase()+'|'+rec.payload.modelId.toLowerCase();
  require(!seen.has(id),'DUPLICATE_CANDIDATE');seen.add(id);
  require(digest({seq:rec.seq,prev:rec.prev,payload:rec.payload})===rec.hash,'CHAIN_HASH');prev=rec.hash;
 }
 require(anchor===null||anchor.tip===prev,'EXTERNAL_TIP_MISMATCH');
 return {count:files.length,tip:prev,seen};
}
export function verify(dir,anchor){
 const p=stateDir(dir),r=scan(p,anchor);return {count:r.count,tip:r.tip,certifiedN:0,...FLAGS,anchorAuthenticated:false};
}
function syncDir(p){const fd=openSync(p,'r');try{fsyncSync(fd)}finally{closeSync(fd)}}
export function append(dir,payload,anchor){
 const p=stateDir(dir);validate(payload);
 const lock=join(p,'.append-lock');mkdirSync(lock,{mode:0o700});
 const stage=join(lock,'stage');let linked=false;
 try{
  const r=scan(p,anchor,true),id=payload.fixture.toLowerCase()+'|'+payload.modelId.toLowerCase();
  require(r.count<MAX_RECORDS&&!r.seen.has(id),'DUPLICATE_OR_FULL');
  const body={seq:r.count+1,prev:r.tip,payload},rec={...body,hash:digest(body)},bytes=canonical(rec)+'\n';
  require(Buffer.byteLength(bytes)<=MAX_BYTES,'RECORD_SIZE');
  const fd=openSync(stage,'wx',0o600);try{writeFileSync(fd,bytes);fsyncSync(fd)}finally{closeSync(fd)}
  linkSync(stage,join(p,name(body.seq)));linked=true;unlinkSync(stage);syncDir(p);
  const next={count:body.seq,tip:rec.hash};scan(p,next,true);return next;
 }finally{
  // If a crash occurs, the lock or unanchored record is deliberately not auto-recovered.
  try{unlinkSync(stage)}catch(e){if(e.code!=='ENOENT')throw e;}
  rmdirSync(lock);syncDir(p);
 }
}
export function auditLedger(doc){
 require(doc&&doc.production_recommendations==='DISABLED'&&Array.isArray(doc.samples)&&doc.n===doc.samples.length,'LEDGER_INVALID');
 const claimed=doc.samples.filter(x=>x?.fixture_result_source_independently_verified===true).length;
 return {historicalN:doc.n,claimedIndependentN:claimed,certifiedN:0,certifiedMetrics:null,...FLAGS,classification:'HISTORICAL_UNAUTHENTICATED_ONLY',reason:'No independently authenticated source bytes, pre-kickoff external timestamp and trusted anchor supplied. Existing ledger untouched.'};
}
function readBounded(p){const s=lstatSync(p);require(s.isFile()&&s.size<=MAX_BYTES,'INPUT_TOO_LARGE');return JSON.parse(readFileSync(p,'utf8'))}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const [cmd,...args]=process.argv.slice(2);
 try{
  let result;
  if(cmd==='--audit'&&args.length===0){const bytes=readFileSync(join(ROOT,'evidence/settled.json'));result={ledgerSha256:createHash('sha256').update(bytes).digest('hex'),...auditLedger(JSON.parse(bytes))};}
  else if(cmd==='--verify'&&args.length===2){result=verify(args[0],args[1]==='GENESIS'?null:readBounded(args[1]));}
  else if(cmd==='--append'&&args.length===3){const anchor=append(args[0],readBounded(args[1]),args[2]==='GENESIS'?null:readBounded(args[2]));result={anchor,...FLAGS,classification:'UNAUTHENTICATED_CANDIDATE',anchorAuthenticated:false};}
  else throw Error('INVALID_COMMAND');
  console.log(JSON.stringify(result,null,2));
 }catch(e){console.log(JSON.stringify({...FLAGS,status:'BLOCKED',reason:e.message}));process.exitCode=1;}
}
