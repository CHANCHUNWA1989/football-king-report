import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
// Fixed research-only subprocesses. No user-controlled commands or paths.
function cases(){
 const safe={release:"HOLD",production_recommendations:"DISABLED",automaticProductionRepair:false,issues:[],sourceHashes:{"sources/seven_quality_gates_latest.json":"a".repeat(64),"market/latest.json":"b".repeat(64),"evidence/settled.json":"c".repeat(64)}};
 const unit=n=>({passed:n,total:n,tests:Array.from({length:n},(_,i)=>({name:"t"+i,pass:true}))});
 const route={route:"upgrade",steps:["read-project-policy"],release:"HOLD",production_recommendations:"DISABLED"};
 const historical={...unit(26),historical:{release:"HOLD",production_recommendations:"DISABLED",forwardEligible:false,liveEligible:false}};
 const arena={valid:true,archiveN:129,pairedN:90,certifiedN:0,certifiedMetrics:null,canPromote:false,classification:"DESCRIPTIVE_UNAUTHENTICATED_REPLAY",release:"HOLD",production_recommendations:"DISABLED"};
 const good={"diagnose":safe,"core":unit(22),"dispatch":unit(27),"route":route,"source":historical,"arena-tests":unit(24),"arena":arena,"recovery":unit(25)};
 const c=[];const add=(name,mut,expected)=>c.push([name,mut,expected]);
 add("healthy integrated pipeline",{},o=>o.status==="RESEARCH_COMPLETE"&&o.completed===8&&o.checksPassed===124);
 add("external evidence blocker",{"diagnose":{...safe,issues:[{code:"INDEPENDENT_RESULTS_MISSING",action:"EXTERNAL_EVIDENCE_REQUIRED"}]}},o=>o.status==="RESEARCH_COMPLETE"&&o.queue[0].code==="INDEPENDENT_RESULTS_MISSING");
 add("unsafe diagnostic flag",{"diagnose":{...safe,release:"READY"}},o=>o.status==="BLOCKED"&&o.completed===0);
 add("unsafe state issue",{"diagnose":{...safe,issues:[{code:"SAFETY_STATE_MISMATCH",action:"QUARANTINE_NO_WRITE"}]}},o=>o.status==="BLOCKED"&&o.completed===1);
 add("bad source hashes",{"diagnose":{...safe,sourceHashes:{}}},o=>o.status==="BLOCKED");
 add("unknown issue",{"diagnose":{...safe,issues:[{code:"UNKNOWN",action:"GO"}]}},o=>o.status==="BLOCKED");
 add("failed child",{"core":{error:"CHILD_EXIT"}},o=>o.status==="BLOCKED"&&o.completed===1);
 add("timeout",{"core":{error:"TIMEOUT"}},o=>o.status==="BLOCKED"&&o.completed===1);
 add("invalid JSON",{"dispatch":{error:"INVALID_JSON"}},o=>o.status==="BLOCKED"&&o.completed===2);
 add("empty green",{"core":unit(0)},o=>o.status==="BLOCKED");
 add("false test pass",{"core":{...unit(22),tests:[...unit(21).tests,{name:"bad",pass:false}]}},o=>o.status==="BLOCKED");
 add("duplicate test names",{"core":{...unit(22),tests:Array.from({length:22},()=>({name:"same",pass:true}))}},o=>o.status==="BLOCKED");
 add("blocked route",{"route":{...route,route:"blocked"}},o=>o.status==="BLOCKED");
 add("historical spoof",{"source":{...historical,historical:{...historical.historical,forwardEligible:true}}},o=>o.status==="BLOCKED");
 add("arena promotion",{"arena":{...arena,canPromote:true}},o=>o.status==="BLOCKED");
 add("arena false certified",{"arena":{...arena,certifiedN:1}},o=>o.status==="BLOCKED");
 add("arena count impossible",{"arena":{...arena,pairedN:130}},o=>o.status==="BLOCKED");
 add("recovery failure",{"recovery":{...unit(25),passed:24}},o=>o.status==="BLOCKED"&&o.completed===7);
 add("priority order",{"diagnose":{...safe,issues:[{code:"QUALITY_GATES_INCOMPLETE",action:"EXTERNAL_EVIDENCE_REQUIRED"},{code:"QUOTA_NEAR_BOUNDARY",action:"NO_EXTRA_VENDOR_CALL"},{code:"MARKET_OLDER_THAN_RESEARCH_CANDIDATE_LIMIT",action:"REFRESH_VIA_APPROVED_COLLECTOR_ONLY"}]}},o=>o.queue.map(x=>x.code).join(",")==="QUOTA_NEAR_BOUNDARY,MARKET_OLDER_THAN_RESEARCH_CANDIDATE_LIMIT,QUALITY_GATES_INCOMPLETE");
 add("duplicate issue",{"diagnose":{...safe,issues:Array(2).fill({code:"QUALITY_GATES_INCOMPLETE",action:"EXTERNAL_EVIDENCE_REQUIRED"})}},o=>o.status==="BLOCKED");
 add("bad action",{"diagnose":{...safe,issues:[{code:"QUOTA_BOUNDARY",action:"GO"}]}},o=>o.status==="BLOCKED");
 add("no mutation authorization",{},o=>o.release==="HOLD"&&o.production_recommendations==="DISABLED"&&!o.canPromote&&!o.mergeAuthorized&&!o.automaticProductionRepair);
 return {c,good};
}
function orchestrate(run){
 const out={status:"BLOCKED",completed:0,checksPassed:0,modules:[],queue:[],release:"HOLD",production_recommendations:"DISABLED",canPromote:false,mergeAuthorized:false,automaticProductionRepair:false};
 const order=["diagnose","core","dispatch","route","source","arena-tests","arena","recovery"];
 const count={"core":22,"dispatch":27,"source":26,"arena-tests":24,"recovery":25};
 const policies={SAFETY_STATE_MISMATCH:[0,"QUARANTINE_NO_WRITE"],LEDGER_STRUCTURE_INVALID:[0,"QUARANTINE_NO_WRITE"],MARKET_TIME_INVALID:[0,"QUARANTINE_NO_WRITE"],QUOTA_UNKNOWN:[1,"NO_VENDOR_CALL"],QUOTA_BOUNDARY:[1,"NO_VENDOR_CALL"],QUOTA_NEAR_BOUNDARY:[1,"NO_EXTRA_VENDOR_CALL"],MARKET_OLDER_THAN_RESEARCH_CANDIDATE_LIMIT:[2,"REFRESH_VIA_APPROVED_COLLECTOR_ONLY"],INDEPENDENT_RESULTS_MISSING:[3,"EXTERNAL_EVIDENCE_REQUIRED"],QUALITY_GATES_INCOMPLETE:[4,"EXTERNAL_EVIDENCE_REQUIRED"]};
 const safe=x=>x&&x.release==="HOLD"&&x.production_recommendations==="DISABLED";
 const validTests=(x,n)=>{const t=x?.tests??x?.results;return x?.passed===n&&x.total===n&&Array.isArray(t)&&t.length===n&&t.every(z=>z?.pass===true&&typeof z.name==="string"&&z.name.length>0)&&new Set(t.map(z=>z.name)).size===n;};
 const fail=(id,reason)=>{out.modules.push({id,status:"BLOCKED",reason});out.blockedAt=id;return out;};
 for(const id of order){
  let x;try{x=run(id)}catch{return fail(id,"CHILD_EXCEPTION")}
  if(!x||typeof x!=="object"||x.error)return fail(id,["TIMEOUT","CHILD_EXIT","INVALID_JSON","OUTPUT_LIMIT","SPAWN_ERROR"].includes(x?.error)?x.error:"INVALID_OUTPUT");
  if(id==="diagnose"){
   const hashes=x.sourceHashes;
   if(!safe(x)||x.automaticProductionRepair!==false||!hashes||!["sources/seven_quality_gates_latest.json","market/latest.json","evidence/settled.json"].every(k=>typeof hashes[k]==="string"&&/^[a-f0-9]{64}$/.test(hashes[k]))||!Array.isArray(x.issues)||x.issues.some(z=>!z||!Object.hasOwn(policies,z.code)||policies[z.code][1]!==z.action)||new Set(x.issues.map(z=>z.code)).size!==x.issues.length)return fail(id,"DIAGNOSTIC_CONTRACT");
   out.sourceHashes=hashes;out.queue=x.issues.map(z=>({code:z.code,action:z.action,priority:policies[z.code][0]})).sort((a,b)=>a.priority-b.priority||a.code.localeCompare(b.code));
   out.modules.push({id,status:"PASS"});out.completed++;
   if(out.queue.some(z=>z.priority===0)){out.blockedAt=id;return out;}continue;
  }
  if(Object.hasOwn(count,id)&&!validTests(x,count[id]))return fail(id,"TEST_CONTRACT");
  if(id==="route"&&(!safe(x)||x.route!=="upgrade"||!Array.isArray(x.steps)||!x.steps.includes("read-project-policy")))return fail(id,"ROUTE_CONTRACT");
  if(id==="source"&&(!safe(x.historical)||x.historical.forwardEligible!==false||x.historical.liveEligible!==false))return fail(id,"SOURCE_CONTRACT");
  if(id==="arena"&&(!safe(x)||x.valid!==true||x.canPromote!==false||x.certifiedN!==0||x.certifiedMetrics!==null||x.classification!=="DESCRIPTIVE_UNAUTHENTICATED_REPLAY"||!Number.isInteger(x.archiveN)||!Number.isInteger(x.pairedN)||x.archiveN<0||x.pairedN<0||x.pairedN>x.archiveN))return fail(id,"ARENA_CONTRACT");
  if(id==="arena")out.arena={archiveN:x.archiveN,pairedN:x.pairedN,certifiedN:x.certifiedN,classification:x.classification};
  out.modules.push({id,status:"PASS",...(Object.hasOwn(count,id)?{checks:count[id]}:{})});out.completed++;out.checksPassed+=count[id]??0;
 }
 out.status="RESEARCH_COMPLETE";return out;
}
function selftest(){const {c,good}=cases();return c.map(([name,mut,p])=>{try{return {name,pass:p(orchestrate(id=>Object.hasOwn(mut,id)?mut[id]:good[id]))===true}}catch{return {name,pass:false}}});}
const dir=dirname(fileURLToPath(import.meta.url)),root=resolve(dir,'../../..');
const commands={diagnose:['recovery.mjs','--diagnose'],core:['selftest.mjs'],dispatch:['dispatch.mjs','--selftest'],route:['dispatch.mjs','--route','下一階段'],source:['source-audit.mjs'],'arena-tests':['arena.mjs','--selftest'],arena:['arena.mjs','--ledger','evidence/settled.json'],recovery:['recovery.mjs','--selftest']};
function run(id){
 const [file,...args]=commands[id];
 const r=spawnSync(process.execPath,[resolve(dir,file),...args],{cwd:root,encoding:'utf8',timeout:15000,maxBuffer:2*1024*1024,env:{LANG:'C.UTF-8'},shell:false});
 if(r.error)return {error:r.error.code==='ETIMEDOUT'?'TIMEOUT':r.error.code==='ENOBUFS'?'OUTPUT_LIMIT':'SPAWN_ERROR'};
 if(r.status!==0)return {error:'CHILD_EXIT'};
 try{return JSON.parse(r.stdout)}catch{return {error:'INVALID_JSON'};}
}
const files=['sources/seven_quality_gates_latest.json','market/latest.json','evidence/settled.json'];
const hashes=()=>Object.fromEntries(files.map(p=>[p,createHash('sha256').update(readFileSync(resolve(root,p))).digest('hex')]));
const eq=(a,b)=>files.every(p=>a?.[p]===b?.[p]);
if(process.argv[2]==='--selftest'&&process.argv.length===3){
 const tests=selftest();console.log(JSON.stringify({passed:tests.filter(x=>x.pass).length,total:tests.length,tests},null,2));if(tests.some(x=>!x.pass))process.exitCode=1;
}else if(process.argv[2]==='--run'&&process.argv.length===3){
 let result;
 try{const before=hashes();result=orchestrate(run);const after=hashes();result.inputsUnchanged=eq(before,after);result.diagnosticHashesMatch=eq(before,result.sourceHashes);if(!result.inputsUnchanged||!result.diagnosticHashesMatch){result.status='BLOCKED';result.blockedAt='input-integrity';}}
 catch{result={status:'BLOCKED',blockedAt:'input-read',release:'HOLD',production_recommendations:'DISABLED',canPromote:false,mergeAuthorized:false,automaticProductionRepair:false};}
 console.log(JSON.stringify(result,null,2));if(result.status!=='RESEARCH_COMPLETE')process.exitCode=1;
}else{console.error('Use --selftest or --run');process.exitCode=2;}
