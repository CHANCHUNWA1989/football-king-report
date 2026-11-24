const assert = require('node:assert/strict');
const { performance } = require('node:perf_hooks');
const w = require('./n8n_offline_demo.json');
const fixture = new Function(w.nodes[1].parameters.jsCode)()[0].json;
const guard = new Function('$input', w.nodes[2].parameters.jsCode);
const run = items => guard({all:()=>items})[0].json;
let count=0; const start=performance.now();
for(let total=0;total<=32;total++)for(let c=0;c<=total;c++){
 const r=run([{json:{...fixture,total,candidates:c,rejected:total-c}}]);
 assert.equal(r.status,'HOLD');assert.equal(r.production_recommendations,'DISABLED');assert.equal(r.external_calls,0);assert.equal(r.alert,total===0?'EMPTY_BATCH':total>c?'REJECTED_CAPTURE':'RESEARCH_ONLY');count++;
}
const mutations=[['status','PASS'],['source_authorized',true],['independently_verified',true],['eligible_for_model_scoring',true],['production_recommendations','ENABLED'],['external_calls',1],['corroboration_executed',true],['total',33],['candidates',-1],['rejected',0.5]];
for(let i=0;i<10000;i++){let [k,v]=mutations[i%mutations.length];assert.throws(()=>run([{json:{...fixture,[k]:v}}]));count++}
for(const items of [[],[{json:fixture},{json:fixture}],[{json:null}],[{}]]){assert.throws(()=>run(items));count++}
for(const k of ['token','live_execution_allowed','raw','price','order']){assert.throws(()=>run([{json:{...fixture,[k]:true}}]));count++}
for(const k of Object.keys(fixture)){const r={...fixture};delete r[k];assert.throws(()=>run([{json:r}]));count++}
console.log({count,ms:performance.now()-start,node:process.version,heap:process.memoryUsage().heapUsed});
