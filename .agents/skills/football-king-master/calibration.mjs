import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
function prob(p){return Array.isArray(p)&&p.length===3&&p.every(v=>typeof v==="number"&&Number.isFinite(v)&&v>=0&&v<=1)&&Math.abs(p.reduce((a,b)=>a+b,0)-1)<=1e-6;}
function temp(p,t){if(!prob(p)||!Number.isFinite(t)||t<=0)throw Error("INVALID_TEMPERATURE_INPUT");const l=p.map(v=>Math.log(Math.max(v,1e-15))/t),mx=Math.max(...l),q=l.map(x=>Math.exp(x-mx)),s=q.reduce((a,b)=>a+b,0);return q.map(x=>x/s);}
function drift(ws){return ws.length!==2||ws.some(x=>x.n<10||!Number.isFinite(x.gap))?"INSUFFICIENT_WINDOWS":ws.every(x=>x.gap>=.05)?"RESEARCH_PAUSE_CANDIDATE":"MONITOR_ONLY";}
function rolling(doc){
 const D=86400000,W=7*D,MON=Date.parse("1970-01-05T00:00:00Z"),grid=[.5,.75,1,1.25,1.5,2];
 const o={valid:false,archiveN:0,acceptedN:0,evaluatedN:0,certifiedN:0,certifiedMetrics:null,metrics:null,folds:[],exclusions:{invalid:0,duplicate:0},release:"HOLD",production_recommendations:"DISABLED",canPromote:false,canChangeWeights:false,classification:"RETROSPECTIVE_PROXY_ONLY",policy:{availability:"kickoff plus 72 hours assumed; not actual result availability",window:"UTC Monday forecast issue time",lookbackDays:28,minTrain:20,temperatureGrid:grid}};
 const ts=v=>typeof v==="string"&&/T\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
 if(!doc||doc.schema!=="football-king-forward-research-1"||doc.production_recommendations!=="DISABLED"||!Array.isArray(doc.samples)||doc.n!==doc.samples.length||!Number.isFinite(ts(doc.checked_utc)))return o;
 o.valid=true;o.archiveN=doc.n;const counts=new Map();
 for(const r of doc.samples)if(typeof r?.key==="string")counts.set(r.key,(counts.get(r.key)||0)+1);
 const rows=[];
 for(const r of doc.samples){
 if(!r||typeof r.key!=="string"){o.exclusions.invalid++;continue;}
 if(counts.get(r.key)>1){o.exclusions.duplicate++;continue;}
 let id;try{id=JSON.parse(r.key)}catch{}
 const k=ts(r.kickoff_utc),f=ts(r.forecast_utc),m=ts(r.market_utc);
 if(!Array.isArray(id)||id.length!==4||id[0]!==r.league||!id.slice(0,3).every(x=>typeof x==="string"&&x.trim())||id[1]===id[2]||ts(id[3])!==k||![k,f,m].every(Number.isFinite)||!(m<=f&&f<k&&k<ts(doc.checked_utc))||!Number.isInteger(r.y)||r.y<0||r.y>2||r.production_recommendations!=="DISABLED"||!prob(r.p)||!prob(r.m)){o.exclusions.invalid++;continue;}
 rows.push({k,f,available:k+3*D,y:r.y,p:r.p,m:r.m});
 }
 o.acceptedN=rows.length;o.unauthenticatedAvailabilityN=rows.length;
 const loss=(p,y)=>-Math.log(Math.max(p[y],1e-15));
 function score(rs){if(!rs.length)return null;const res={};for(const key of ["original","calibrated","market"]){let l=0,b=0;const bins=Array.from({length:3},()=>Array.from({length:5},()=>({n:0,p:0,hits:0})));for(const r of rs){const p=r[key];l+=loss(p,r.y);b+=p.reduce((a,v,i)=>a+(v-Number(i===r.y))**2,0);p.forEach((v,i)=>{const z=bins[i][Math.min(4,Math.floor(v*5))];z.n++;z.p+=v;z.hits+=Number(i===r.y);});}
 const calibration=bins.map(bs=>bs.map(z=>({n:z.n,meanP:z.n?z.p/z.n:null,observed:z.n?z.hits/z.n:null})));
 res[key]={logLoss:l/rs.length,brier:b/rs.length,calibration};}return res;}
 const groups=new Map();for(const r of rows){const w=MON+Math.floor((r.f-MON)/W)*W;if(!groups.has(w))groups.set(w,[]);groups.get(w).push(r);}
 const all=[];
 for(const [start,ev] of [...groups.entries()].sort((a,b)=>a[0]-b[0])){
 const train=rows.filter(r=>r.available<start&&r.available>=start-28*D&&r.f<start);
 const fold={start:new Date(start).toISOString(),n:ev.length,trainN:train.length,status:"INSUFFICIENT_TRAIN"};
 if(train.length<20){o.folds.push(fold);continue;}
 const candidates=grid.map(t=>({t,l:train.reduce((a,r)=>a+loss(temp(r.p,t),r.y),0)/train.length})).sort((a,b)=>a.l-b.l||Math.abs(a.t-1)-Math.abs(b.t-1)||a.t-b.t);
 const t=candidates[0].t,scored=ev.map(r=>({y:r.y,original:r.p,calibrated:temp(r.p,t),market:r.m})),metrics=score(scored);
 Object.assign(fold,{status:"EVALUATED",temperature:t,earliestTrainingProxy:new Date(Math.min(...train.map(r=>r.available))).toISOString(),latestTrainingProxy:new Date(Math.max(...train.map(r=>r.available))).toISOString(),metrics:Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,{logLoss:v.logLoss,brier:v.brier}])),gap:metrics.calibrated.logLoss-metrics.market.logLoss});
 all.push(...scored);o.folds.push(fold);
 }
 o.evaluatedN=all.length;o.metrics=score(all);const tail=o.folds.slice(-2);
 o.drift={status:drift(tail.length===2&&Date.parse(tail[1].start)-Date.parse(tail[0].start)===W&&tail.every(f=>f.status==="EVALUATED")?tail:[]),threshold:.05,minN:10,productionChange:false};
 return o;
}
function tests(){
 const D=86400000,start=Date.parse("2026-10-05T00:00:00Z");
 const mk=i=>{const k=start+i*D,p=[.8,.1,.1],m=[.5,.25,.25];return {key:JSON.stringify(["epl","h"+i,"a"+i,new Date(k).toISOString()]),league:"epl",kickoff_utc:new Date(k).toISOString(),forecast_utc:new Date(k-D).toISOString(),market_utc:new Date(k-D-1000).toISOString(),y:i%3,p,m,production_recommendations:"DISABLED"};};
 const rows=Array.from({length:45},(_,i)=>mk(i));
 const doc=samples=>({schema:"football-king-forward-research-1",checked_utc:"2026-12-01T00:00:00Z",n:samples.length,samples,production_recommendations:"DISABLED"});
 const run=rs=>rolling(doc(rs)),r=run(rows);
 const checks=[
 ["identity",Math.abs(temp([.8,.1,.1],1)[0]-.8)<1e-12],
 ["soften",temp([.8,.1,.1],2)[0]<.8],
 ["sharpen",temp([.8,.1,.1],.5)[0]>.8],
 ["normalize",Math.abs(temp([1,0,0],2).reduce((a,b)=>a+b,0)-1)<1e-12],
 ["paired coverage",r.evaluatedN>0&&r.folds.filter(f=>f.status==="EVALUATED").reduce((n,f)=>n+f.n,0)===r.evaluatedN],
 ["past availability",r.folds.filter(f=>f.status==="EVALUATED").every(f=>f.latestTrainingProxy<f.start)],
 ["lookback",r.folds.filter(f=>f.status==="EVALUATED").every(f=>Date.parse(f.earliestTrainingProxy)>=Date.parse(f.start)-28*D)],
 ["sparse train",r.folds.some(f=>f.status==="INSUFFICIENT_TRAIN")],
 ["future outcomes cannot alter past fit",r.folds.filter(f=>Date.parse(f.start)<start+35*D).every(f=>f.temperature===run(rows.map((x,i)=>i>=35?{...x,y:(x.y+1)%3}:x)).folds.find(z=>z.start===f.start)?.temperature)],
 ["forecast issue boundary",run([mk(7)]).folds[0].start==="2026-10-05T00:00:00.000Z"],
 ["duplicate quarantine",run([rows[0],rows[0],...rows.slice(1)]).exclusions.duplicate===2],
 ["late market",run([{...rows[0],market_utc:rows[0].kickoff_utc}]).acceptedN===0],
 ["late forecast",run([{...rows[0],forecast_utc:rows[0].kickoff_utc}]).acceptedN===0],
 ["boolean outcome",run([{...rows[0],y:true}]).acceptedN===0],
 ["unsafe row",run([{...rows[0],production_recommendations:"ENABLED"}]).acceptedN===0],
 ["no certified flag bypass",run(rows.map(x=>({...x,fixture_result_source_independently_verified:true}))).certifiedN===0],
 ["empty",run([]).metrics===null],
 ["count mismatch",rolling({...doc(rows),n:0}).valid===false],
 ["one window",drift([{n:20,gap:.1}])==="INSUFFICIENT_WINDOWS"],
 ["two poor windows",drift([{n:20,gap:.08},{n:20,gap:.09}])==="RESEARCH_PAUSE_CANDIDATE"],
 ["low coverage",drift([{n:9,gap:.2},{n:20,gap:.2}])==="INSUFFICIENT_WINDOWS"],
 ["good windows",drift([{n:20,gap:-.1},{n:20,gap:-.1}])==="MONITOR_ONLY"],
 ["fixed safety",r.release==="HOLD"&&r.production_recommendations==="DISABLED"&&!r.canPromote&&!r.canChangeWeights]
 ];return checks.map(([name,pass])=>({name,pass}));
}
if(process.argv[2]==='--selftest'){const t=tests();console.log(JSON.stringify({passed:t.filter(x=>x.pass).length,total:t.length,tests:t},null,2));if(t.some(x=>!x.pass))process.exitCode=1;}else if(process.argv[2]==='--ledger'&&process.argv[3]){const b=readFileSync(process.argv[3]);const o=rolling(JSON.parse(b));console.log(JSON.stringify({ledgerSha256:createHash('sha256').update(b).digest('hex'),...o},null,2));if(!o.valid)process.exitCode=1;}else process.exitCode=2;
