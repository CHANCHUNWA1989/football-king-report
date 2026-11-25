'use strict';
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {audit}=require('./ten_case_linkage_gate.cjs');
const files=["forecast_content_linkage_20261125.json","fresh_witness_execution_20261125.json","ft_observation_review_20261125.json","openligadb_probe_evidence_20261125.json","source_origin_review_20261125.json"];
const expected=["95f59f7528bb31557768014dcb87f6117055f353","f25cfab76cafd2f7a2a417d13d9a63f886f31a1f","12e72d988ae80081376f43aa510e910239c9d3f4","d645d500ca140d3a4c716f7a9d48ebf692c883a5","68d617f1f02f3fbbe43c0c107a327cc4ec6bf8a8"];
const raw=files.map(f=>fs.readFileSync(path.join(__dirname,f)));
const hashes=raw.map(b=>crypto.createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex'));
if(JSON.stringify(hashes)!==JSON.stringify(expected))throw Error('PINNED_BLOB_MISMATCH');
const data=raw.map(b=>JSON.parse(b.toString('utf8')));
function test(audit,data,blobs){
 const copy=x=>JSON.parse(JSON.stringify(x));let count=0;
 if(audit(data,blobs).matched_research_cases!==10||audit(data,blobs).authenticated_settlements!==0)throw Error("positive");count++;
 const cases=[["duplicate",d=>{d[1].cases[1]=d[1].cases[0]}],["missing",d=>{d[4].cases.pop()}],["wrong fixture",d=>{d[3].cases[0].api_observation.match_id=9999}],["wrong forecast",d=>{d[1].cases[0].case_id=d[1].cases[1].case_id}],["wrong score",d=>{d[2].cases[0].published_score_ft=[0,8]}],["late witness",d=>{d[1].cases[0].verified_tlog_utc="2026-12-01T00:00:00+00:00"}],["forged eligibility",d=>{d[4].cases[0].eligible_for_model_scoring=true}],["claimed actual kickoff",d=>{d[4].cases[0].actual_kickoff_utc="2026-11-06T19:30:00+00:00"}],["wrong blob link",d=>{d[4].api_observation_blob="0".repeat(40)}],["forged certification",d=>{d[0].authenticated_settlements=10}]];
 for(const [name,mutate] of cases){let d=copy(data);mutate(d);let rejected=false;try{audit(d,blobs)}catch{rejected=true}if(!rejected)throw Error("not rejected: "+name);count++}
 return count;
}
console.log('Passed '+test(audit,data,hashes)+' checks. HOLD.');
const saved=JSON.parse(fs.readFileSync(path.join(__dirname,'ten_case_linkage_audit_20261125.json'),'utf8'));
if(JSON.stringify(saved)!==JSON.stringify(audit(data,hashes)))throw Error('SAVED_AUDIT_MISMATCH');
