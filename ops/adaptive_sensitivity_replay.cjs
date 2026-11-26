// Research only. Offline pinned data. No release evidence.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const files=["2023-24/en.1.json","2023-24/de.1.json","2024-25/en.1.json","2024-25/de.1.json"];const pins=["f62b11dfaf06cffd1236c2777caebb880a0cfea1","2c41078e751d914f24bfe7e55c5567cea70a4aee","504f2e732fbc3c9caeb98e4382b13b094453b840","9921b1d8485429913ff6d161500beb519d8b0e51"];
function replay(doc,expected,anchor,temperature,shrink){
  const clip=x=>Math.max(.2,Math.min(5,x));
  function prob(h,a){
    function pois(l){let x=[Math.exp(-l)];for(let k=1;k<=30;k++)x.push(x[k-1]*l/k);return x;}
    const H=pois(clip(h)),A=pois(clip(a)),p=[0,0,0];for(let i=0;i<H.length;i++)for(let j=0;j<A.length;j++)p[i>j?0:i===j?1:2]+=H[i]*A[j];const s=p.reduce((a,b)=>a+b,0);return p.map(x=>x/s);
  }
  const rows=doc.matches.slice().sort((a,b)=>a.date.localeCompare(b.date)||a.team1.localeCompare(b.team1)||a.team2.localeCompare(b.team2));
  if(rows.length!==expected)throw Error("count");
  const seen=new Set(),teams=new Map();
  for(const r of rows){const f=r.score?.ft,k=r.team1+"\0"+r.team2;if(!/^\d{4}-\d{2}-\d{2}$/.test(r.date)||!Array.isArray(f)||f.length!==2||f.some(x=>!Number.isInteger(x)||x<0)||!r.team1||!r.team2||r.team1===r.team2||seen.has(k))throw Error("fixture");seen.add(k);}
  const get=t=>{if(!teams.has(t))teams.set(t,{hn:0,an:0,hf:0,ha:0,af:0,aa:0,elo:1500});return teams.get(t);};
  const keys=["baseline","venue","elo","fixed","adaptive"],scores=Object.fromEntries(keys.map(k=>[k,{ll:0,br:0,hit:0}]));let n=0,gh=0,ga=0,assessed=0,prior=0,week=null,weights=[1,0,0],loss=[0,0,0],pending=[],weeks=0;
  const mix=(p,w)=>[0,1,2].map(j=>p.reduce((s,v,k)=>s+w[k]*v[j],0));
  for(let i=0;i<rows.length;){
    let j=i+1;while(j<rows.length&&rows[j].date===rows[i].date)j++;
    const day=Date.parse(rows[i].date+"T00:00:00Z"),w=Math.floor((day/86400000+3)/7);
    if(w!==week){for(const item of pending){prior++;for(let z=0;z<3;z++)loss[z]+=item[z];}pending=[];week=w;weights=[1,0,0];if(prior>=60){const min=Math.min(...loss),raw=loss.map(x=>Math.exp(-(x-min)/prior/temperature)),den=raw.reduce((a,b)=>a+b,0);weights=raw.map(x=>(1-anchor)*x/den);weights[0]+=anchor;}weeks++;}
    const changes=new Map();
    for(const r of rows.slice(i,j)){
      const [x,y]=r.score.ft,o=x>y?0:x===y?1:2,h=get(r.team1),a=get(r.team2);
      if(n>=60){const H=clip(gh/n),A=clip(ga/n),s=shrink;
        const hv=((h.hf+s*H)/(h.hn+s))*((a.aa+s*H)/(a.an+s))/H;
        const av=((a.af+s*A)/(a.an+s))*((h.ha+s*A)/(h.hn+s))/A;
        const gap=Math.max(-400,Math.min(400,h.elo-a.elo))/800;
        const p=[prob(H,A),prob(hv,av),prob(H*Math.exp(gap),A*Math.exp(-gap))];
        const preds=[...p,mix(p,[1/3,1/3,1/3]),mix(p,weights)];pending.push(p.map(v=>-Math.log(Math.max(1e-12,v[o]))));
        keys.forEach((k,z)=>{const v=preds[z],m=scores[k];m.ll-=Math.log(Math.max(1e-12,v[o]));m.br+=v.reduce((s,t,k)=>s+(t-(k===o?1:0))**2,0);m.hit+=v.indexOf(Math.max(...v))===o?1:0;});assessed++;
      }
      const e=1/(1+10**(-(h.elo-a.elo+65)/400)),d=20*((x>y?1:x===y?.5:0)-e);changes.set(r.team1,(changes.get(r.team1)||0)+d);changes.set(r.team2,(changes.get(r.team2)||0)-d);
    }
    for(const r of rows.slice(i,j)){const [x,y]=r.score.ft,h=get(r.team1),a=get(r.team2);h.hn++;h.hf+=x;h.ha+=y;a.an++;a.af+=y;a.aa+=x;n++;gh+=x;ga+=y;}
    for(const [t,d] of changes)get(t).elo+=d;
    i=j;
  }
  return {raw:n,assessed,warmup:n-assessed,weeks,models:Object.fromEntries(keys.map(k=>[k,Object.fromEntries(Object.entries(scores[k]).map(([m,v])=>[m,v/assessed]))])),state:"HOLD",certified_cases:0};
}

function run(sources){const configs=[];for(const anchor of [0,.25,.5])for(const temperature of [.05,.1,.25])for(const shrink of [4,8,16])configs.push({anchor,temperature,shrink});return configs.map(c=>{const cohorts=sources.map((d,i)=>{const r=replay(d,i%2===0?380:306,c.anchor,c.temperature,c.shrink);return {n:r.assessed,adaptive:r.models.adaptive,venue:r.models.venue,fixed:r.models.fixed,elo:r.models.elo,baseline:r.models.baseline}});const n=cohorts.reduce((a,b)=>a+b.n,0);return {...c,cohorts,pooled_ll:cohorts.reduce((s,x)=>s+x.n*x.adaptive.ll,0)/n,pooled_venue_ll:cohorts.reduce((s,x)=>s+x.n*x.venue.ll,0)/n,wins_vs_venue:cohorts.filter(x=>x.adaptive.ll<x.venue.ll).length};});}
if(require.main===module){if(!process.argv[2])throw Error('archive directory required');const docs=files.map((file,i)=>{const b=fs.readFileSync(path.join(process.argv[2],file));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==pins[i])throw Error('pin mismatch');return JSON.parse(b)});console.log(JSON.stringify({state:'HOLD',certified_cases:0,results:run(docs)},null,2));}
module.exports={run,replay};
