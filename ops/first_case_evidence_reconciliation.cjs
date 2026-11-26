// Offline evidence reconciliation, not certification.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const refs=[["evidence/settled.json","f546c96def382659ee9d74d6ef40e823a223e4a9"],["research/intelligence_x/settlement_evidence_worklist_20261125.json","382a3d4e0ee15e90c7548018ee82e584d07b3e21"],["research/intelligence_x/openligadb_probe_evidence_20261125.json","d645d500ca140d3a4c716f7a9d48ebf692c883a5"],["research/intelligence_x/source_origin_review_20261125.json","68d617f1f02f3fbbe43c0c107a327cc4ec6bf8a8"]];
function audit(archive,work,api,origin){
 const idx=(rows,key)=>{if(!Array.isArray(rows))throw Error("rows");const m=new Map();for(const r of rows){if(typeof r[key]!=="string"||!r[key]||m.has(r[key]))throw Error("identity");m.set(r[key],r)}return m};
 const a=idx(archive.samples,"key"),w=idx(work.cases,"archive_key"),p=idx(api.cases,"archive_key"),o=idx(origin.cases,"archive_key");
 if(a.size!==105||w.size!==a.size||p.size!==10||o.size!==10||[...a.keys()].some(k=>!w.has(k)))throw Error("scope");
 const selected=[...w.values()].filter(r=>r.priority===1);if(selected.length!==10)throw Error("priority");
 const rows=selected.map(r=>{const k=r.archive_key,z=a.get(k),q=p.get(k),v=o.get(k),id=r.provider_fixture_hint?.match_id;
 if(!q||!v||!z||typeof id!=="string"||q.provider_fixture_id_hint!==id||v.provider_fixture_id_hint!==id||String(q.api_observation?.match_id)!==id||r.forecast_event_id_claim!=="openligadb:"+id||z.league!==r.league||z.kickoff_utc!==r.recorded_kickoff_utc||z.forecast_utc!==r.recorded_forecast_utc||z.market_utc!==r.recorded_market_utc)throw Error("binding");
 if(z.fixture_result_source_independently_verified!==false||[r,q,v].some(x=>x.independently_verified!==false||x.eligible_for_model_scoring!==false))throw Error("unsafe claims");
 const apiMatch=["matched","finished","full_time_match","league_season_match","scheduled_utc_match","teams_match"].every(t=>q.api_observation[t]===true);
 return {archive_key:k,provider_id_hint:id,observed_api_match:apiMatch,reported_public_ft_agreement:q.public_ft_agreement===true,observed_kickoff_marker:v.first_half_kickoff_marker_observed===true,actual_kickoff_authenticated:false,independent_source_origin_authenticated:false,raw_result_replay_authenticated:false,independent_prematch_witness_authenticated:false,source_rights_approved:false,independent_review_complete:false,blockers:["AUTHENTICATED_ACTUAL_KICKOFF","INDEPENDENT_SOURCE_ORIGIN_AND_RIGHTS","REPLAYABLE_RAW_REGULATION_FT","INDEPENDENT_PREMATCH_WITNESS","INDEPENDENT_REVIEW"],eligible_for_model_scoring:false,certified:false};});
 return {archive_rows:a.size,priority_candidates:rows.length,matched_api:rows.filter(r=>r.observed_api_match).length,reported_public_ft_agreement:rows.filter(r=>r.reported_public_ft_agreement).length,kickoff_markers:rows.filter(r=>r.observed_kickoff_marker).length,authenticated_cases:0,rows,status:"HOLD",production_recommendations:"DISABLED"};
}
if(require.main===module){const root=process.argv[2]||'.';const docs=refs.map(([f,p])=>{const b=fs.readFileSync(path.join(root,f));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==p)throw Error('pin');return JSON.parse(b)});console.log(JSON.stringify(audit(...docs),null,2))}
module.exports={audit};
