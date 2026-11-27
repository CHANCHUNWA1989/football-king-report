"use strict";
// Research only. A supplied chain head is not authenticated or evidence of publication.
const {createHash}=require("node:crypto");
const {reconcile}=require("./recap_completeness_20261127.cjs");
const sha256=s=>createHash("sha256").update(s,"utf8").digest("hex");
function crossWindow(windows, scope, expectedHead, outcomes, digest, reconcile) {
  const fail = m => { throw new Error(m); };
  const exact = (v,ks) => v && typeof v==="object" && !Array.isArray(v) && Object.keys(v).sort().join(",")===ks.slice().sort().join(",");
  const ts = v => typeof v==="string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString()===v;
  const hex = v => typeof v==="string" && /^[a-f0-9]{64}$/.test(v);
  const id = v => typeof v==="string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v);
  if(!exact(scope,["start","end","window_count"])||!ts(scope.start)||!ts(scope.end)||scope.start>=scope.end||!Number.isSafeInteger(scope.window_count)||scope.window_count<1||scope.window_count>366||!Array.isArray(windows)||windows.length!==scope.window_count||!hex(expectedHead))fail("INVALID_SCOPE");
  let cursor=scope.start, prev=digest(JSON.stringify(["recap-window-chain-v1",scope.start,scope.end,scope.window_count]));
  const records=[], anchors=[];
  for(let i=0;i<windows.length;i++){
    const w=windows[i];
    if(!exact(w,["window_start","window_end","records"])||!ts(w.window_start)||!ts(w.window_end)||w.window_start!==cursor||w.window_end<=cursor||w.window_end>scope.end||!Array.isArray(w.records)||records.length+w.records.length>10000)fail("WINDOW_GAP_OVERLAP_OR_INVALID");
    for(const r of w.records){
      if(!exact(r,["record_id","fixture_id","market_id","revision","issued_at","action"])||!id(r.record_id)||!id(r.fixture_id)||!id(r.market_id)||!Number.isSafeInteger(r.revision)||r.revision<1||!ts(r.issued_at)||r.issued_at<w.window_start||r.issued_at>=w.window_end||!["CLAIMED_PICK","HOLD","RESEARCH_ONLY","EXTERNAL_TIP","UNKNOWN"].includes(r.action))fail("WINDOW_RECORD_INVALID");
      records.push(r);
    }
    const canonical=w.records.map(r=>[r.record_id,r.fixture_id,r.market_id,r.revision,r.issued_at,r.action]).sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
    prev=digest(JSON.stringify(["recap-window-chain-v1",i,prev,w.window_start,w.window_end,canonical]));
    if(!hex(prev))fail("INVALID_DIGEST");
    anchors.push({window_start:w.window_start,window_end:w.window_end,record_count:w.records.length,head:prev});
    cursor=w.window_end;
  }
  if(cursor!==scope.end)fail("WINDOW_END_MISMATCH");
  if(prev!==expectedHead)fail("EXPECTED_HEAD_MISMATCH");
  const report=reconcile({window_start:scope.start,window_end:scope.end,records},outcomes);
  return {...report,schema:"recap-cross-window-research-v1",chain_matches_supplied_head:true,external_anchor_authenticated:false,window_completeness_verified:false,window_count:windows.length,empty_window_count:anchors.filter(a=>a.record_count===0).length,chain_head:prev,anchors};
}
function testCrossWindow(digest,reconcile) {
  const scope={start:"2026-11-26T00:00:00.000Z",end:"2026-11-29T00:00:00.000Z",window_count:3};
  const mk=()=>[
    {window_start:scope.start,window_end:"2026-11-27T00:00:00.000Z",records:[{record_id:"a",fixture_id:"f",market_id:"m",revision:1,issued_at:"2026-11-26T23:59:59.000Z",action:"CLAIMED_PICK"},{record_id:"c",fixture_id:"f",market_id:"n",revision:1,issued_at:"2026-11-26T18:00:00.000Z",action:"RESEARCH_ONLY"}]},
    {window_start:"2026-11-27T00:00:00.000Z",window_end:"2026-11-28T00:00:00.000Z",records:[{record_id:"b",fixture_id:"f",market_id:"m",revision:2,issued_at:"2026-11-27T00:00:00.000Z",action:"HOLD"}]},
    {window_start:"2026-11-28T00:00:00.000Z",window_end:scope.end,records:[]}
  ];
  const headFor=ws=>{
    let p=digest(JSON.stringify(["recap-window-chain-v1",scope.start,scope.end,scope.window_count]));
    ws.forEach((w,i)=>{const rows=w.records.slice().sort((a,b)=>a.record_id<b.record_id?-1:a.record_id>b.record_id?1:0).map(r=>[r.record_id,r.fixture_id,r.market_id,r.revision,r.issued_at,r.action]);p=digest(JSON.stringify(["recap-window-chain-v1",i,p,w.window_start,w.window_end,rows]));});
    return p;
  };
  const anchor=headFor(mk()), run=(ws=mk(),s=scope,h=anchor,o=[])=>crossWindow(ws,s,h,o,digest,reconcile);
  let n=0;
  const check=c=>{if(!c)throw new Error("CROSS_TEST_FAILED_"+n);n++;};
  const rejects=(fn,msg)=>{let got;try{fn()}catch(e){got=e.message}check(got===msg);};
  let r=run();
  check(r.chain_head===anchor&&r.window_count===3&&r.empty_window_count===1);
  check(r.expected_record_count===3&&r.distinct_fixture_count===1&&r.distinct_market_count===2);
  check(r.latest_action_counts.HOLD===1&&r.latest_action_counts.CLAIMED_PICK===0);
  check(r.external_anchor_authenticated===false&&r.window_completeness_verified===false&&r.production_recommendations==="DISABLED");
  check(r.counts.MISSING===3&&r.roi===null&&r.hit_rate===null);
  let w=mk();w[0].records.reverse();check(run(w).chain_head===anchor);
  w=mk();w[0].records[0].action="HOLD";rejects(()=>run(w),"EXPECTED_HEAD_MISMATCH");
  check(run(w,scope,headFor(w)).external_anchor_authenticated===false);
  w=mk();w[2].records.push({...w[1].records[0],record_id:"d",issued_at:"2026-11-28T00:00:00.000Z",revision:3});rejects(()=>run(w),"EXPECTED_HEAD_MISMATCH");
  rejects(()=>run(mk().slice(0,2)),"INVALID_SCOPE");
  w=mk();w[1].window_start="2026-11-27T00:00:01.000Z";rejects(()=>run(w),"WINDOW_GAP_OVERLAP_OR_INVALID");
  w=mk();w[1].window_start="2026-11-26T23:59:59.000Z";rejects(()=>run(w),"WINDOW_GAP_OVERLAP_OR_INVALID");
  w=mk();w[2].window_end="2026-11-28T23:59:59.000Z";rejects(()=>run(w),"WINDOW_END_MISMATCH");
  w=mk();w[0].records[0].issued_at=w[0].window_end;rejects(()=>run(w),"WINDOW_RECORD_INVALID");
  w=mk();w[1].records[0].revision=3;rejects(()=>run(w,scope,headFor(w)),"REVISION_GAP_OR_ORDER");
  w=mk();w[1].records[0].record_id="a";rejects(()=>run(w,scope,headFor(w)),"DUPLICATE_RECORD");
  rejects(()=>run(mk(),scope,"f".repeat(64)),"EXPECTED_HEAD_MISMATCH");
  rejects(()=>run(mk(),{...scope,authenticated:true}),"INVALID_SCOPE");
  rejects(()=>run(mk(),scope,anchor,[{record_id:"a",status:"REPORTED_FINAL",score90:[1,0]},{record_id:"b",status:"REPORTED_FINAL",score90:[0,1]}]),"CONFLICTING_FIXTURE_SCORES");
  check(run(mk(),scope,anchor,[{record_id:"a",status:"REPORTED_FINAL",score90:[1,0]}]).final_record_coverage===1/3);
  return n;
}
module.exports={audit:(windows,scope,head,outcomes)=>crossWindow(windows,scope,head,outcomes,sha256,reconcile)};
if(require.main===module){if(sha256("abc")!=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")throw Error("SHA256_VECTOR");console.log(`PASS ${testCrossWindow(sha256,reconcile)+1} cross-window assertions`);}
