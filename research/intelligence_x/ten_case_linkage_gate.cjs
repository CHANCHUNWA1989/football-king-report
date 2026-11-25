'use strict';
// Research-only metadata linkage; never an admission credential.
function audit(d, hashes) {
  const fail=(why)=>{throw new Error(why)};
  const schemas=["intelligence-x-forecast-content-linkage-v1","intelligence-x-fresh-witness-execution-record-v1","intelligence-x-public-ft-observation-review-v1","intelligence-x-api-probe-log-observation-v1","intelligence-x-source-origin-qualification-review-v1"];
  if(!Array.isArray(d)||d.length!==5||!Array.isArray(hashes)||hashes.length!==5||hashes.some(x=>typeof x!=="string"||!/^[a-f0-9]{40}$/.test(x)))fail("INPUT_CONTRACT");
  const [f,w,t,a,s]=d;
  for(let i=0;i<5;i++){const v=d[i];if(!v||v.schema!==schemas[i]||v.status!=="HOLD"||v.production_recommendations!=="DISABLED"||v.authenticated_settlements!==0||!Array.isArray(v.cases)||v.cases.length!==10)fail("UNSAFE_OR_INCOMPLETE_REPORT_"+i);}
  if(f.public_ft_review_blob!==hashes[2]||w.linkage_blob!==hashes[0]||a.observation_blob!==hashes[2]||s.api_observation_blob!==hashes[3])fail("BLOB_LINK_MISMATCH");
  const maps=d.map(v=>{const m=new Map();for(const c of v.cases){if(!c||typeof c.archive_key!=="string"||m.has(c.archive_key)||c.independently_verified!==false||c.eligible_for_model_scoring!==false)fail("DUPLICATE_OR_UNSAFE_CASE");m.set(c.archive_key,c)}return m;});
  const ids=new Set(),providerIds=new Set(),rows=[];
  for(const [key,fc] of maps[0]){
    if(maps.some(m=>!m.has(key)))fail("COHORT_MISMATCH");
    const [,wc,tc,ac,sc]=maps.map(m=>m.get(key));
    const k=JSON.parse(key);
    if(!Array.isArray(k)||k.length!==4||k[0]!=="bundesliga"||typeof k[1]!=="string"||typeof k[2]!=="string"||!k[1]||!k[2]||k[1]===k[2]||typeof k[3]!=="string"||!k[3].endsWith("+00:00")||!Number.isFinite(Date.parse(k[3])))fail("BAD_ARCHIVE_KEY");
    const id=tc.provider_fixture_id_hint;
    if(typeof id!=="string"||!/^[1-9]\d*$/.test(id)||providerIds.has(id)||fc.forecast_event_id_claim!=="openligadb:"+id||ac.provider_fixture_id_hint!==id||sc.provider_fixture_id_hint!==id||!Number.isSafeInteger(ac.api_observation?.match_id)||String(ac.api_observation.match_id)!==id)fail("PROVIDER_ID_MISMATCH");
    if(typeof fc.case_id!=="string"||!/^[a-f0-9]{64}$/.test(fc.case_id)||ids.has(fc.case_id)||fc.case_id!==wc.case_id||!Number.isSafeInteger(fc.run_id)||fc.run_id!==wc.forecast_run_id||fc.matched_rows!==1||fc.all_content_checks_match!==true||fc.public_ft_observation_matches!==true)fail("FORECAST_LINK_MISMATCH");
    const score=tc.published_score_ft;
    if(!Array.isArray(score)||score.length!==2||score.some(x=>!Number.isSafeInteger(x)||x<0)||tc.archive_y!==(score[0]>score[1]?0:score[0]===score[1]?1:2)||tc.observed_y!==tc.archive_y||tc.publisher_agreement!==true||tc.archive_y_matches_observation!==true||tc.recorded_kickoff_utc!==k[3])fail("SCORE_OR_SCHEDULE_MISMATCH");
    const ao=ac.api_observation;
    if(!["matched","finished","full_time_match","league_season_match","scheduled_utc_match","teams_match"].every(x=>ao[x]===true)||ac.public_ft_agreement!==true||ao.independently_verified!==false||ao.eligible_for_model_scoring!==false||ao.production_recommendations!=="DISABLED"||ao.status!=="HOLD")fail("API_OBSERVATION_MISMATCH");
    const witness=wc.verified_tlog_utc;
    if(typeof witness!=="string"||!witness.endsWith("+00:00")||!Number.isFinite(Date.parse(witness))||Date.parse(witness)>=Date.parse(k[3])||wc.covered_by_successful_fixed_cohort_verification!==true)fail("WITNESS_SCHEDULE_MISMATCH");
    if(sc.first_half_kickoff_marker_observed!==true||sc.actual_kickoff_utc!==null||sc.actual_kickoff_authenticated!==false||sc.source_independence_authenticated!==false||sc.raw_result_replayable!==false||tc.raw_capture_authenticated!==false||wc.actual_kickoff_authenticated!==false||wc.result_origin_authenticated!==false||fc.source_independence_authenticated!==false||ac.source_independence_authenticated!==false)fail("UNEXPECTED_AUTHENTICATION_CLAIM");
    ids.add(fc.case_id);providerIds.add(id);
    rows.push({archive_key:key,case_id:fc.case_id,provider_id_claim:id,forecast_run_id:fc.run_id,observed_score_ft:score,recorded_kickoff_utc:k[3],observed_witness_utc:witness,identity_linkage_consistent:true,actual_kickoff_authenticated:false,source_independence_authenticated:false,independently_verified:false,eligible_for_model_scoring:false,status:"HOLD"});
  }
  return {schema:"intelligence-x-ten-case-linkage-audit-v1",status:"HOLD",production_recommendations:"DISABLED",input_blob_ids:hashes,matched_research_cases:rows.length,authenticated_settlements:0,eligible_for_model_scoring:false,positive_ev_verified:false,limitations:["Metadata/transcript consistency only; no raw result bodies or new signature verification.","Publisher origin independence and actual UTC kickoff remain unproven.","No prediction scoring, calibration, or executable odds certification."],cases:rows};
}
module.exports={audit};
