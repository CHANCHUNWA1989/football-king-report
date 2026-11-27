"use strict";
// Research only: caller-supplied pseudonymous manifest, no external source or time attestation.
function reconcile(manifest, outcomes) {
  const fail = (msg) => { throw new Error(msg); };
  const token = (v) => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v);
  const stamp = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString() === v;
  const fields = (v, keys) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join(",") === keys.slice().sort().join(",");
  if (!fields(manifest, ["window_start","window_end","records"]) || !stamp(manifest.window_start) || !stamp(manifest.window_end) || manifest.window_start >= manifest.window_end || !Array.isArray(manifest.records) || manifest.records.length > 10000 || !Array.isArray(outcomes) || outcomes.length > 10000) fail("INVALID_BATCH");
  const records = new Map(), groups = new Map(), results = new Map(), fixtureScores = new Map();
  const actions = ["CLAIMED_PICK","HOLD","RESEARCH_ONLY","EXTERNAL_TIP","UNKNOWN"];
  for (const r of manifest.records) {
    if (!fields(r, ["record_id","fixture_id","market_id","revision","issued_at","action"]) || !token(r.record_id) || !token(r.fixture_id) || !token(r.market_id) || !Number.isSafeInteger(r.revision) || r.revision < 1 || !stamp(r.issued_at) || r.issued_at < manifest.window_start || r.issued_at >= manifest.window_end || !actions.includes(r.action)) fail("INVALID_MANIFEST_RECORD");
    if (records.has(r.record_id)) fail("DUPLICATE_RECORD");
    records.set(r.record_id,r);
    const key = JSON.stringify([r.fixture_id,r.market_id]);
    if (!groups.has(key)) groups.set(key,[]);
    groups.get(key).push(r);
  }
  const active = new Set();
  for (const g of groups.values()) {
    g.sort((a,b)=>a.revision-b.revision);
    for (let i=0;i<g.length;i++) if (g[i].revision !== i+1 || (i && g[i].issued_at <= g[i-1].issued_at)) fail("REVISION_GAP_OR_ORDER");
    active.add(g[g.length-1].record_id);
  }
  for (const o of outcomes) {
    if (!fields(o,["record_id","status","score90"]) || !token(o.record_id) || !["REPORTED_FINAL","PENDING","CONFLICT","UNAVAILABLE"].includes(o.status)) fail("INVALID_OUTCOME");
    if (!records.has(o.record_id)) fail("UNEXPECTED_OUTCOME");
    if (results.has(o.record_id)) fail("DUPLICATE_OUTCOME");
    if (o.status === "REPORTED_FINAL") {
      if (!Array.isArray(o.score90) || o.score90.length!==2 || !o.score90.every(x=>Number.isSafeInteger(x)&&x>=0&&x<=30)) fail("INVALID_SCORE");
      const f=records.get(o.record_id).fixture_id, score=JSON.stringify(o.score90);
      if (fixtureScores.has(f)&&fixtureScores.get(f)!==score) fail("CONFLICTING_FIXTURE_SCORES");
      fixtureScores.set(f,score);
    } else if (o.score90 !== null) fail("NONFINAL_SCORE");
    results.set(o.record_id,o);
  }
  const rows = [...records.values()].sort((a,b)=>a.record_id<b.record_id?-1:a.record_id>b.record_id?1:0).map(r=>({...r,latest_revision:active.has(r.record_id),result_status:results.get(r.record_id)?.status ?? "MISSING",reported_score90:results.get(r.record_id)?.score90 ?? null}));
  const counts={REPORTED_FINAL:0,PENDING:0,CONFLICT:0,UNAVAILABLE:0,MISSING:0};
  const latestActionCounts=Object.fromEntries(actions.map(a=>[a,0]));
  for (const r of rows) {counts[r.result_status]++; if(r.latest_revision) latestActionCounts[r.action]++;}
  return {schema:"recap-completeness-research-v1",status:"HOLD",production_recommendations:"DISABLED",manifest_authenticated:false,source_independence_verified:false,window_completeness_verified:false,expected_record_count:rows.length,distinct_fixture_count:new Set(rows.map(r=>r.fixture_id)).size,distinct_market_count:groups.size,latest_action_counts:latestActionCounts,counts,record_coverage:rows.length?results.size/rows.length:null,final_record_coverage:rows.length?counts.REPORTED_FINAL/rows.length:null,missing_record_ids:rows.filter(r=>r.result_status==="MISSING").map(r=>r.record_id),formal_bet_count:0,certified_forward_samples:0,hit_rate:null,roi:null,ev:null,rows};
}
function selfTest() {
  const m=()=>({window_start:"2026-11-26T00:00:00.000Z",window_end:"2026-11-27T00:00:00.000Z",records:[{record_id:"a",fixture_id:"f",market_id:"m",revision:1,issued_at:"2026-11-26T01:00:00.000Z",action:"CLAIMED_PICK"},{record_id:"b",fixture_id:"f",market_id:"m",revision:2,issued_at:"2026-11-26T02:00:00.000Z",action:"HOLD"},{record_id:"c",fixture_id:"f",market_id:"n",revision:1,issued_at:"2026-11-26T01:00:00.000Z",action:"RESEARCH_ONLY"}]});
  const o=(id="a",score=[2,1])=>({record_id:id,status:"REPORTED_FINAL",score90:score});
  let n=0;
  const check=(condition)=>{if(!condition)throw new Error("TEST_FAILED_"+n);n++;};
  const rejects=(fn,expected)=>{let error;try{fn()}catch(e){error=e.message}check(error===expected);};
  let r=reconcile(m(),[o()]);
  check(r.expected_record_count===3&&r.distinct_fixture_count===1&&r.distinct_market_count===2);
  check(r.counts.MISSING===2&&r.missing_record_ids.join(",")==="b,c");
  check(r.latest_action_counts.CLAIMED_PICK===0&&r.latest_action_counts.HOLD===1);
  check(r.record_coverage===1/3&&r.final_record_coverage===1/3);
  check(r.hit_rate===null&&r.roi===null&&r.ev===null&&r.production_recommendations==="DISABLED");
  check(reconcile(m(),[o(),{record_id:"b",status:"PENDING",score90:null}]).record_coverage===2/3);
  check(reconcile({...m(),records:[]},[]).record_coverage===null);
  check(JSON.stringify(reconcile(m(),[o()]))===JSON.stringify(reconcile({...m(),records:m().records.reverse()},[o()])));
  rejects(()=>reconcile(m(),[o("x")]),"UNEXPECTED_OUTCOME");
  rejects(()=>reconcile(m(),[o(),o()]),"DUPLICATE_OUTCOME");
  rejects(()=>reconcile(m(),[o(),o("c",[1,2])]),"CONFLICTING_FIXTURE_SCORES");
  rejects(()=>reconcile(m(),[o("a",[true,2])]),"INVALID_SCORE");
  rejects(()=>reconcile(m(),[{record_id:"a",status:"PENDING",score90:[0,0]}]),"NONFINAL_SCORE");
  for (const [key,value,error] of [["revision",3,"REVISION_GAP_OR_ORDER"],["issued_at","2026-11-26T01:00:00.000Z","REVISION_GAP_OR_ORDER"],["issued_at","2026-11-27T00:00:00.000Z","INVALID_MANIFEST_RECORD"],["issued_at","2026-11-26T25:00:00.000Z","INVALID_MANIFEST_RECORD"],["action","CERTIFIED","INVALID_MANIFEST_RECORD"],["record_id","a","DUPLICATE_RECORD"]]) {
    const x=m();x.records[1][key]=value;rejects(()=>reconcile(x,[]),error);
  }
  rejects(()=>reconcile({...m(),authenticated:true},[]),"INVALID_BATCH");
  for(const status of ["PENDING","CONFLICT","UNAVAILABLE"])check(reconcile(m(),[{record_id:"a",status,score90:null}]).counts[status]===1);
  return n;
}
module.exports={reconcile,selfTest};
if(require.main===module) console.log(`PASS ${selfTest()} assertions`);
