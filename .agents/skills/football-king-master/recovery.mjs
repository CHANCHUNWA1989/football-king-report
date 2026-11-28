import {mkdtempSync,readFileSync,writeFileSync,renameSync,rmSync,existsSync,unlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
// No caller-controlled repair paths. All mutations are inside a newly created private temp directory.
// Synthetic derived cache only. No production writes, secrets, network, or retries.
function diagnose(g,m,e,asOf){
 const t=x=>typeof x==="string"&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(x)?Date.parse(x):NaN;
 const issues=[];const add=(code,action)=>issues.push({code,action});
 if(!g||g.status!=="HOLD"||g.production_recommendations!=="DISABLED"||g.can_promote_model!==false||g.can_recommend_bets!==false||e?.production_recommendations!=="DISABLED")add("SAFETY_STATE_MISMATCH","QUARANTINE_NO_WRITE");
 if(!Array.isArray(g?.checks)||g.checks.some(x=>x.state!=="PASS"))add("QUALITY_GATES_INCOMPLETE","EXTERNAL_EVIDENCE_REQUIRED");
 if(!Number.isFinite(t(asOf))||!Number.isFinite(t(m?.as_of_utc))||t(m.as_of_utc)>t(asOf))add("MARKET_TIME_INVALID","QUARANTINE_NO_WRITE");
 else if(t(asOf)-t(m.as_of_utc)>4*3600000)add("MARKET_OLDER_THAN_RESEARCH_CANDIDATE_LIMIT","REFRESH_VIA_APPROVED_COLLECTOR_ONLY");
 const q=m?.quota,p=m?.quota_policy;
 if(!q||!p||![q.used,q.remaining,p.max_monthly_used,p.remaining_floor].every(x=>Number.isInteger(x)&&x>=0))add("QUOTA_UNKNOWN","NO_VENDOR_CALL");
 else if(q.used>=p.max_monthly_used||q.remaining<=p.remaining_floor)add("QUOTA_BOUNDARY","NO_VENDOR_CALL");
 else if(p.max_monthly_used-q.used<=2||q.remaining-p.remaining_floor<=2)add("QUOTA_NEAR_BOUNDARY","NO_EXTRA_VENDOR_CALL");
 if(!Array.isArray(e?.samples)||e.n!==e.samples.length)add("LEDGER_STRUCTURE_INVALID","QUARANTINE_NO_WRITE");
 else if(e.results_independently_verified!==true||e.samples.some(r=>r.fixture_result_source_independently_verified!==true))add("INDEPENDENT_RESULTS_MISSING","EXTERNAL_EVIDENCE_REQUIRED");
 return {asOf,issues,release:"HOLD",production_recommendations:"DISABLED",automaticProductionRepair:false};
}
function expectedCache(source){
 if(!source||source.schema!=="synthetic-fixture-v1"||source.production_recommendations!=="DISABLED"||source.release!=="HOLD"||!Array.isArray(source.items)||!source.items.every(x=>typeof x==="string"&&x.length>0)||new Set(source.items).size!==source.items.length)throw Error("SOURCE_INVALID");
 return JSON.stringify({schema:"synthetic-derived-cache-v1",count:source.items.length,release:"HOLD",production_recommendations:"DISABLED"})+"\n";
}
const sha=b=>createHash('sha256').update(b).digest('hex');
const safe={schema:'synthetic-fixture-v1',items:['a','b'],release:'HOLD',production_recommendations:'DISABLED'};
function transact(source,original,{failValidation=false,failBeforeRename=false,corruptBackup=false,failRollback=false}={}){
 const dir=mkdtempSync(join(tmpdir(),'fk-v14-'));
 const src=join(dir,'source.json'),cache=join(dir,'cache.json'),backup=join(dir,'backup.bin'),stage=join(dir,'stage.tmp'),restore=join(dir,'restore.tmp');
 const sourceBytes=Buffer.from(JSON.stringify(source)),originalBytes=Buffer.from(original);
 const result={status:'HOLD',release:'HOLD',production_recommendations:'DISABLED',before:sha(originalBytes),sourceBefore:sha(sourceBytes),repairApplied:false,rollbackVerified:false,rollbackAttempted:false,quarantined:false};
 try{
  writeFileSync(src,sourceBytes,{flag:'wx',mode:0o600});writeFileSync(cache,originalBytes,{flag:'wx',mode:0o600});
  let target;
  try{target=expectedCache(JSON.parse(readFileSync(src,'utf8')));}catch{result.status='SOURCE_INVALID';return result;}
  if(readFileSync(cache,'utf8')===target){result.status='HEALTHY';return result;}
  result.rootCause='DERIVED_CACHE_MISMATCH';
  writeFileSync(backup,readFileSync(cache),{flag:'wx',mode:0o600});
  if(corruptBackup)writeFileSync(backup,'corrupted');
  if(sha(readFileSync(backup))!==result.before){result.status='BACKUP_INVALID';return result;}
  writeFileSync(stage,target,{flag:'wx',mode:0o600});
  if(failBeforeRename){result.status='STAGE_ABORTED';return result;}
  renameSync(stage,cache);result.repairApplied=true;
  try{
   assert.equal(readFileSync(cache,'utf8'),expectedCache(JSON.parse(readFileSync(src,'utf8'))));
   assert.equal(sha(readFileSync(src)),result.sourceBefore);
   if(failValidation)throw Error('INJECTED_POST_WRITE_FAILURE');
   result.status='REPAIRED_SANDBOX';
  }catch{
   result.rollbackAttempted=true;
   try{
    if(failRollback)throw Error('INJECTED_ROLLBACK_FAILURE');
    const bytes=readFileSync(backup);assert.equal(sha(bytes),result.before);
    writeFileSync(restore,bytes,{flag:'wx',mode:0o600});renameSync(restore,cache);
    assert.equal(sha(readFileSync(cache)),result.before);result.rollbackVerified=true;result.status='ROLLED_BACK_SANDBOX';
   }catch{result.status='ROLLBACK_FAILED_QUARANTINED';result.quarantined=true;}
  }
  return result;
 }finally{
  result.after=existsSync(cache)?sha(readFileSync(cache)):null;
  result.sourceAfter=existsSync(src)?sha(readFileSync(src)):null;
  result.restoredOriginal=result.after===result.before;
  result.sourceUnchanged=result.sourceAfter===result.sourceBefore;
  rmSync(dir,{recursive:true,force:true});
  result.sandboxRemoved=!existsSync(dir);
 }
}
function selftest(){
 const good=expectedCache(safe),bad='{"count":999}\n',broken='{broken',tests=[];
 const test=(name,fn)=>{try{fn();tests.push({name,pass:true})}catch(e){tests.push({name,pass:false,error:String(e.message)})}};
 function run(source,bytes,opts){const o=transact(source,bytes,opts);assert.equal(o.release,'HOLD');assert.equal(o.production_recommendations,'DISABLED');assert.equal(o.sourceUnchanged,true);assert.equal(o.sandboxRemoved,true);return o;}
 test('healthy no write',()=>{const o=run(safe,good);assert.equal(o.status,'HEALTHY');assert(o.restoredOriginal&&!o.repairApplied)});
 test('wrong count corrected',()=>{const o=run(safe,bad);assert.equal(o.status,'REPAIRED_SANDBOX');assert.equal(o.after,sha(good));assert(o.repairApplied)});
 test('invalid JSON cache rebuilt',()=>{const o=run(safe,broken);assert.equal(o.status,'REPAIRED_SANDBOX');assert.equal(o.after,sha(good))});
 test('unsafe cache flags removed',()=>{const o=run(safe,'{"release":"READY","production_recommendations":"ENABLED"}');assert.equal(o.after,sha(good))});
 test('invalid source blocks repair',()=>{const o=run({...safe,items:null},bad);assert.equal(o.status,'SOURCE_INVALID');assert(o.restoredOriginal&&!o.repairApplied)});
 test('duplicate source blocks repair',()=>{const o=run({...safe,items:['a','a']},bad);assert.equal(o.status,'SOURCE_INVALID');assert(o.restoredOriginal)});
 test('unsafe source blocks repair',()=>{const o=run({...safe,release:'READY'},bad);assert.equal(o.status,'SOURCE_INVALID');assert(o.restoredOriginal)});
 test('corrupt backup blocks write',()=>{const o=run(safe,bad,{corruptBackup:true});assert.equal(o.status,'BACKUP_INVALID');assert(o.restoredOriginal&&!o.repairApplied)});
 test('stage failure leaves original intact',()=>{const o=run(safe,bad,{failBeforeRename:true});assert.equal(o.status,'STAGE_ABORTED');assert(o.restoredOriginal&&!o.repairApplied)});
 test('post-write failure rolls back exact bytes',()=>{const o=run(safe,bad,{failValidation:true});assert.equal(o.status,'ROLLED_BACK_SANDBOX');assert(o.repairApplied&&o.rollbackAttempted&&o.rollbackVerified&&o.restoredOriginal)});
 test('rollback preserves malformed original bytes',()=>{const o=run(safe,broken,{failValidation:true});assert(o.rollbackVerified&&o.restoredOriginal)});
 test('rollback failure quarantines',()=>{const o=run(safe,bad,{failValidation:true,failRollback:true});assert.equal(o.status,'ROLLBACK_FAILED_QUARANTINED');assert(o.quarantined&&!o.rollbackVerified&&!o.restoredOriginal)});
 test('source and cache separate',()=>{const o=run(safe,bad);assert.equal(o.sourceBefore,o.sourceAfter);assert.notEqual(o.before,o.after)});
 test('idempotent rebuild',()=>{const a=run(safe,bad),b=run(safe,good);assert.equal(a.after,b.after);assert.equal(b.status,'HEALTHY')});
 const g={status:'HOLD',production_recommendations:'DISABLED',can_promote_model:false,can_recommend_bets:false,checks:[{state:'HOLD'}]},m={as_of_utc:'2026-11-20T08:00:00Z',quota:{used:358,remaining:142},quota_policy:{max_monthly_used:360,remaining_floor:140}},e={n:1,samples:[{fixture_result_source_independently_verified:false}],production_recommendations:'DISABLED',results_independently_verified:false},at='2026-11-28T10:02:00Z';
 const has=(g,m,e,code)=>diagnose(g,m,e,at).issues.some(x=>x.code===code);
 test('stale market diagnosis',()=>assert(has(g,m,e,'MARKET_OLDER_THAN_RESEARCH_CANDIDATE_LIMIT')));
 test('quota near boundary',()=>assert(has(g,m,e,'QUOTA_NEAR_BOUNDARY')));
 test('quota at boundary',()=>assert(has(g,{...m,quota:{used:360,remaining:140}},e,'QUOTA_BOUNDARY')));
 test('unknown quota fail closed',()=>assert(has(g,{...m,quota:null},e,'QUOTA_UNKNOWN')));
 test('future timestamp',()=>assert(has(g,{...m,as_of_utc:'2027-01-01T00:00:00Z'},e,'MARKET_TIME_INVALID')));
 test('invalid timestamp',()=>assert(has(g,{...m,as_of_utc:'nope'},e,'MARKET_TIME_INVALID')));
 test('unverified results require external evidence',()=>assert(has(g,m,e,'INDEPENDENT_RESULTS_MISSING')));
 test('unsafe flags quarantine',()=>assert(has({...g,can_promote_model:true},m,e,'SAFETY_STATE_MISMATCH')));
 test('invalid ledger count',()=>assert(has(g,m,{...e,n:2},'LEDGER_STRUCTURE_INVALID')));
 test('incomplete quality gates',()=>assert(has(g,m,e,'QUALITY_GATES_INCOMPLETE')));
 test('diagnostics never authorize production repair',()=>{const o=diagnose(g,m,e,at);assert.equal(o.automaticProductionRepair,false);assert.equal(o.release,'HOLD')});
 return tests;
}
const args=process.argv.slice(2);
if(args[0]==='--selftest'){const tests=selftest();console.log(JSON.stringify({passed:tests.filter(x=>x.pass).length,total:tests.length,tests},null,2));if(tests.some(x=>!x.pass))process.exitCode=1;}
else if(args[0]==='--diagnose'&&args.length===1){const paths=['sources/seven_quality_gates_latest.json','market/latest.json','evidence/settled.json'];const bytes=paths.map(p=>readFileSync(p));const out=diagnose(...bytes.map(b=>JSON.parse(b)),new Date().toISOString());console.log(JSON.stringify({sourceHashes:Object.fromEntries(paths.map((p,i)=>[p,sha(bytes[i])])),...out},null,2));}
else{console.error('Use --selftest or --diagnose from repository root');process.exitCode=2;}
