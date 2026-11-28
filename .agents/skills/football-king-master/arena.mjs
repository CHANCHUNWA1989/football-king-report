import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
// Diagnostic only: never changes ledger or promotes models.
function testCases(){
 const cutoff="2026-11-01T00:00:00Z";
 const mk=(id,day)=>{const p=[.6,.2,.2],m=[.4,.3,.3];return {key:JSON.stringify(["epl","home"+id,"away"+id,day+"T12:00:00+00:00"]),league:"epl",kickoff_utc:day+"T12:00:00+00:00",forecast_utc:day+"T10:00:00+00:00",market_utc:day+"T09:00:00+00:00",y:0,p,m,ab:p.map(x=>.85*x+.15/3),ab_model:"probability-shrink-to-uniform-fixed-0.15-v1",c:p.map((x,i)=>.25*x+.75*m[i]),c_model:"market-anchored-fixed-25pct-model-75pct-consensus-v1",fixture_result_source_independently_verified:false,production_recommendations:"DISABLED"}};
 const make=samples=>({schema:"football-king-forward-research-1",checked_utc:"2026-11-30T00:00:00Z",samples,n:samples.length,results_independently_verified:false,production_recommendations:"DISABLED"});
 const a=mk("1","2026-10-10"),b=mk("2","2026-11-10"),c=mk("3","2026-11-12");
 const cases=[];
 const add=(name,d,p)=>cases.push([name,d,p]);
 add("same cases and split",make([a,b,c]),o=>o.pairedN===3&&o.earlier.n===1&&o.later.n===2);
 add("Brier convention",make([b]),o=>Math.abs(o.later.metrics.A.brier-.24)<1e-10);
 add("log loss convention",make([b]),o=>Math.abs(o.later.metrics.A.logLoss+Math.log(.6))<1e-10);
 add("market comparison",make([b]),o=>Math.abs(o.later.metrics.market.brier-.54)<1e-10);
 add("no certified samples",make([b]),o=>o.certifiedN===0&&o.certifiedMetrics===null);
 add("no empty zero metrics",make([]),o=>o.later.metrics===null);
 add("missing C",make([{...b,c:undefined}]),o=>o.pairedN===0&&o.exclusions.incomplete===1);
 add("wrong B formula",make([{...b,ab:[.6,.2,.2]}]),o=>o.pairedN===0);
 add("wrong C model",make([{...b,c_model:"unsealed"}]),o=>o.pairedN===0);
 add("future market",make([{...b,market_utc:"2026-11-10T11:00:00Z"}]),o=>o.pairedN===0);
 add("late forecast",make([{...b,forecast_utc:b.kickoff_utc}]),o=>o.pairedN===0);
 add("missing offset",make([{...b,forecast_utc:"2026-11-10T10:00:00"}]),o=>o.pairedN===0);
 add("duplicate quarantine",make([b,b,c]),o=>o.pairedN===1&&o.exclusions.duplicate===2);
 add("boolean outcome",make([{...b,y:true}]),o=>o.pairedN===0);
 add("invalid probability",make([{...b,p:[-.1,.5,.6]}]),o=>o.pairedN===0);
 add("row enable",make([{...b,production_recommendations:"ENABLED"}]),o=>o.pairedN===0);
 add("doc enable",{...make([b]),production_recommendations:"ENABLED"},o=>o.valid===false);
 add("count mismatch",{...make([b]),n:5},o=>o.valid===false);
 add("false provenance promotion",make([{...b,fixture_result_source_independently_verified:true,eligible_for_model_scoring:true}]),o=>o.certifiedN===0&&o.certifiedMetrics===null);
 add("future kickoff",make([{...b,kickoff_utc:"2027-01-01T00:00:00Z"}]),o=>o.pairedN===0);
 add("key mismatch",make([{...b,key:a.key}]),o=>o.pairedN===0);
 add("null row",make([null,b]),o=>o.pairedN===1&&o.exclusions.invalid===1);
 add("calibration bins count",make([b,c]),o=>o.later.metrics.A.calibration.every(x=>x.reduce((s,v)=>s+v.n,0)===2));
 add("constant safety",make([a,b,c]),o=>o.release==="HOLD"&&o.production_recommendations==="DISABLED"&&o.canPromote===false);
 return cases;
}
function arena(doc){
 const cutoff="2026-11-01T00:00:00Z",cut=Date.parse(cutoff), names={A:"p",B:"ab",C:"c",market:"m"};
 const exclusions={invalid:0,duplicate:0,incomplete:0};
 const out={valid:false,cutoff,archiveN:0,pairedN:0,certifiedN:0,certifiedMetrics:null,exclusions,earlier:{n:0,metrics:null},later:{n:0,metrics:null},release:"HOLD",production_recommendations:"DISABLED",canPromote:false,classification:"DESCRIPTIVE_UNAUTHENTICATED_REPLAY",notes:["No source authentication or forecast seal revalidation here; no certified forward admission.","Calendar split is retrospective; no fitting or tuning, not a blinded out-of-sample trial.","No Dixon-Coles or red-card challenger probabilities in this ledger; no reconstructed probabilities."]};
 const ts=x=>typeof x==="string"&&/T\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(x)?Date.parse(x):NaN;
 if(!doc||doc.schema!=="football-king-forward-research-1"||doc.production_recommendations!=="DISABLED"||!Array.isArray(doc.samples)||doc.n!==doc.samples.length||!Number.isFinite(ts(doc.checked_utc)))return out;
 out.valid=true;out.archiveN=doc.n;out.claimedIndependentN=doc.samples.filter(x=>x?.fixture_result_source_independently_verified===true).length;
 const counts=new Map();for(const r of doc.samples)if(typeof r?.key==="string")counts.set(r.key,(counts.get(r.key)||0)+1);
 const prob=p=>Array.isArray(p)&&p.length===3&&p.every(x=>typeof x==="number"&&Number.isFinite(x)&&x>=0&&x<=1)&&Math.abs(p.reduce((a,b)=>a+b,0)-1)<=1e-6;
 const same=(x,y)=>x.every((v,i)=>Math.abs(v-y[i])<=1e-6);
 const rows=[];
 for(const r of doc.samples){
  if(!r||typeof r.key!=="string"){exclusions.invalid++;continue;}
  if(counts.get(r.key)>1){exclusions.duplicate++;continue;}
  const k=ts(r.kickoff_utc),f=ts(r.forecast_utc),m=ts(r.market_utc);
  let id;try{id=JSON.parse(r.key)}catch{}
  if(!Array.isArray(id)||id.length!==4||id[0]!==r.league||!id.slice(0,3).every(v=>typeof v==="string"&&v.trim())||id[1]===id[2]||ts(id[3])!==k||![k,f,m].every(Number.isFinite)||!(m<=f&&f<k&&k<ts(doc.checked_utc))||!Number.isInteger(r.y)||r.y<0||r.y>2||r.production_recommendations!=="DISABLED"||!prob(r.p)||!prob(r.m)){exclusions.invalid++;continue;}
  if(!prob(r.ab)||!prob(r.c)||r.ab_model!=="probability-shrink-to-uniform-fixed-0.15-v1"||r.c_model!=="market-anchored-fixed-25pct-model-75pct-consensus-v1"||!same(r.ab,r.p.map(v=>.85*v+.15/3))||!same(r.c,r.p.map((v,i)=>.25*v+.75*r.m[i]))){exclusions.incomplete++;continue;}
  rows.push(r);
 }
 function summarize(rs){
  if(!rs.length)return {n:0,metrics:null,leagues:{},first:null,last:null};
  const metrics={};const leagues={};for(const r of rs)leagues[r.league]=(leagues[r.league]||0)+1;
  for(const [name,key] of Object.entries(names)){
   let brier=0,logLoss=0,hits=0;const calibration=Array.from({length:3},()=>Array.from({length:5},()=>({n:0,sumP:0,hits:0})));
   for(const r of rs){const p=r[key];brier+=p.reduce((a,v,i)=>a+(v-Number(i===r.y))**2,0);logLoss-=Math.log(Math.max(p[r.y],1e-15));if(p.indexOf(Math.max(...p))===r.y)hits++;for(let i=0;i<3;i++){const b=calibration[i][Math.min(4,Math.floor(p[i]*5))];b.n++;b.sumP+=p[i];b.hits+=Number(i===r.y);}}
   metrics[name]={brier:brier/rs.length,logLoss:logLoss/rs.length,top1Accuracy:hits/rs.length,calibration:calibration.map(bins=>bins.map(b=>({n:b.n,meanP:b.n?b.sumP/b.n:null,observed:b.n?b.hits/b.n:null})))};
  }
  const sorted=rs.map(r=>r.kickoff_utc).sort();return {n:rs.length,metrics,leagues,first:sorted[0],last:sorted.at(-1)};
 }
 out.pairedN=rows.length;out.earlier=summarize(rows.filter(r=>ts(r.kickoff_utc)<cut));out.later=summarize(rows.filter(r=>ts(r.kickoff_utc)>=cut));return out;
}
const arg=process.argv[2];
if(arg==='--selftest'){const tests=testCases().map(([name,d,p])=>({name,pass:!!p(arena(d))}));console.log(JSON.stringify({passed:tests.filter(x=>x.pass).length,total:tests.length,tests},null,2));if(tests.some(x=>!x.pass))process.exitCode=1;}
else if(arg==='--ledger'&&process.argv[3]){const data=readFileSync(process.argv[3]);const result=arena(JSON.parse(data));const gitBlob=createHash('sha1').update('blob '+data.length+'\0').update(data).digest('hex');console.log(JSON.stringify({gitBlob,...result},null,2));if(!result.valid)process.exitCode=1;}
else{console.error('Use --selftest or --ledger PATH');process.exitCode=2;}
