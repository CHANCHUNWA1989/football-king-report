const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const w = require('./n8n_rehearsal_guard.json');
assert.equal(w.active,false);
assert.equal(w.settings.timezone,'Asia/Hong_Kong');
assert.deepEqual(w.nodes.map(n=>n.type),['n8n-nodes-base.executeWorkflowTrigger','n8n-nodes-base.code']);
assert.deepEqual(w.pinData,{});
const guard = new Function('$input',w.nodes[1].parameters.jsCode);
const run = r=>guard({all:()=>[{json:r}]})[0].json;
const cli = path.resolve(__dirname,'../../ops/intelligence_x_rehearsal.py');
const registry = Object.fromEntries(['a','b'].map(s=>[s,{publisher_group:'p'+s,origin_group:'o'+s,provider_fixture_id:s}]));
const a = {source:'a',fixture_id:'m',provider_fixture_id:'a',phase:'SECOND_HALF',home_score:1,away_score:0,home_red_cards:0,away_red_cards:1,updated_at:'2026-11-24T13:49:00Z',observed_at:'2026-11-24T13:49:20Z',payload_sha256:'a'.repeat(64)};
const batch = {kind:'SNAPSHOTS',snapshots:[a,{...a,source:'b',provider_fixture_id:'b',payload_sha256:'b'.repeat(64)}]};
const unavailable = {kind:'UNAVAILABLE'};
const blocked = {kind:'SNAPSHOTS',snapshots:[a,{...batch.snapshots[1],home_score:0}]};
const invoke = attempts=>{
  const p=spawnSync(process.env.PYTHON || 'python',['-S',cli],{input:JSON.stringify({fixture_id:'m',registry,now_utc:'2026-11-24T13:50:00Z',attempts}),encoding:'utf8',timeout:5000,maxBuffer:65536});
  assert.equal(p.status,0,p.stderr);return JSON.parse(p.stdout);
};
const cases=[[[batch],'RESEARCH_ONLY'],[[unavailable,batch],'RECOVERED_RESEARCH_ONLY'],[[unavailable,unavailable,batch],'RECOVERED_RESEARCH_ONLY'],[[unavailable],'SOURCE_OUTAGE'],[[unavailable,unavailable,unavailable],'SOURCE_OUTAGE'],[[blocked],'DATA_REJECTED'],[[unavailable,blocked],'DATA_REJECTED']];
for(const [attempts,alert] of cases){const out=run(invoke(attempts));assert.equal(out.alert,alert);assert.equal(out.status,'HOLD');assert.equal(out.production_recommendations,'DISABLED');assert.equal(out.external_calls,0);assert.equal(out.eligible_for_model_scoring,false);assert(!('snapshots' in out));}
const valid=invoke([batch]);
const changes=[['status','PASS'],['source_authorized',true],['independently_verified',true],['eligible_for_model_scoring',true],['production_recommendations','ENABLED'],['external_calls',1],['attempts',4],['attempts',true],['unavailable_attempts',1],['diagnostic','UNAVAILABLE'],['input_kind','LIVE'],['raw','x']];
for(let i=0;i<10000;i++){const [k,v]=changes[i%changes.length];assert.throws(()=>run({...valid,[k]:v}));}
for(const k of Object.keys(valid)){const x={...valid};delete x[k];assert.throws(()=>run(x));}
for(const items of [[],[{json:valid},{json:valid}],[{json:null}],[{json:valid,binary:{x:{}}}]]) assert.throws(()=>guard({all:()=>items}));
console.log(JSON.stringify({cli_guard_cases:cases.length,repeated_mutation_rejections:10000,missing_field_rejections:Object.keys(valid).length,invalid_item_rejections:4,node:process.version}));
