// Offline research only. No market or release evidence.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const files=["2023-24/en.1.json","2023-24/de.1.json","2024-25/en.1.json","2024-25/de.1.json"],pins=["f62b11dfaf06cffd1236c2777caebb880a0cfea1","2c41078e751d914f24bfe7e55c5567cea70a4aee","504f2e732fbc3c9caeb98e4382b13b094453b840","9921b1d8485429913ff6d161500beb519d8b0e51"];
function replay(doc,expected){
 const clip=x=>Math.max(.2,Math.min(5,x));
 const rows=doc.matches.slice().sort((a,b)=>a.date.localeCompare(b.date)||a.team1.localeCompare(b.team1)||a.team2.localeCompare(b.team2));
 if(rows.length!==expected)throw Error("count");
 const seen=new Set(),teams=new Map();
 for(const r of rows){const f=r.score?.ft,k=r.team1+"\0"+r.team2;if(!/^\d{4}-\d{2}-\d{2}$/.test(r.date)||!Number.isFinite(Date.parse(r.date))||!Array.isArray(f)||f.length!==2||f.some(x=>!Number.isInteger(x)||x<0||x>30)||!r.team1||!r.team2||r.team1===r.team2||seen.has(k))throw Error("fixture");seen.add(k);}
 const get=t=>{if(!teams.has(t))teams.set(t,{hn:0,an:0,hf:0,ha:0,af:0,aa:0});return teams.get(t)};
 const names=["poisson","independent_mix","shared_mix"],metrics=["ll","tail","over25","ah_m2","score_ll"],stats=Object.fromEntries(names.map(k=>[k,Object.fromEntries(metrics.map(m=>[m,0]))])),blocks={};
 function dist(l){const p=[Math.exp(-l)];for(let k=1;k<=30;k++)p.push(p[k-1]*l/k);return p}
 function forecast(h,a,mode,x,y){
  h=clip(h);a=clip(a);const H=[dist(h*.75),dist(h),dist(h*1.25)],A=[dist(a*.75),dist(a),dist(a*1.25)];
  let mass=0,tail=0,over=0,exact=0;const p=[0,0,0],ah=[0,0,0];
  for(let i=0;i<=30;i++)for(let j=0;j<=30;j++){
   const v=mode===0?H[1][i]*A[1][j]:mode===1?(H[0][i]+H[2][i])*(A[0][j]+A[2][j])/4:(H[0][i]*A[0][j]+H[2][i]*A[2][j])/2;
   mass+=v;p[i>j?0:i===j?1:2]+=v;ah[i-j>2?0:i-j===2?1:2]+=v;if(Math.abs(i-j)>=3)tail+=v;if(i+j>=3)over+=v;if(i===x&&j===y)exact=v;
  }
  if(Math.abs(mass-1)>1e-8)throw Error("mass");
  const y1=x>y?0:x===y?1:2,grade=x-y>2?0:x-y===2?1:2;
  return [-Math.log(Math.max(p[y1]/mass,1e-12)),(tail/mass-(Math.abs(x-y)>=3?1:0))**2,(over/mass-(x+y>=3?1:0))**2,ah.reduce((t,v,l)=>t+(v/mass-(l===grade?1:0))**2,0),-Math.log(Math.max(exact/mass,1e-12))];
 }
 let n=0,gh=0,ga=0,assessed=0;
 for(let i=0;i<rows.length;){
  let j=i+1;while(j<rows.length&&rows[j].date===rows[i].date)j++;
  const batch=rows.slice(i,j),H=clip(n?gh/n:1.5),A=clip(n?ga/n:1.2),s=8;
  if(n>=60)for(const r of batch){
   const [x,y]=r.score.ft,h=get(r.team1),a=get(r.team2);
   const hv=((h.hf+s*H)/(h.hn+s))*((a.aa+s*H)/(a.an+s))/H,av=((a.af+s*A)/(a.an+s))*((h.ha+s*A)/(h.hn+s))/A;
   const vals=names.map((_,k)=>forecast(hv,av,k,x,y));for(let k=0;k<names.length;k++)for(let m=0;m<metrics.length;m++)stats[names[k]][metrics[m]]+=vals[k][m];
   const w=Math.floor((Date.parse(r.date+"T00:00:00Z")/86400000+3)/7);
   if(!blocks[w])blocks[w]={n:0,independent_mix:Array(metrics.length).fill(0),shared_mix:Array(metrics.length).fill(0)};
   blocks[w].n++;for(let k=1;k<names.length;k++)for(let m=0;m<metrics.length;m++)blocks[w][names[k]][m]+=vals[0][m]-vals[k][m];
   assessed++;
  }
  for(const r of batch){const [x,y]=r.score.ft,h=get(r.team1),a=get(r.team2);h.hn++;h.hf+=x;h.ha+=y;a.an++;a.af+=y;a.aa+=x;n++;gh+=x;ga+=y}
  i=j;
 }
 return {raw:n,assessed,models:Object.fromEntries(names.map(k=>[k,Object.fromEntries(metrics.map(m=>[m,stats[k][m]/assessed]))])),blocks:Object.values(blocks)};
}
function summarize(results){
 const metrics=["ll","tail","over25","ah_m2","score_ll"],names=["poisson","independent_mix","shared_mix"];
 const groups=Object.values(results),n=groups.reduce((s,v)=>s+v.assessed,0);
 const pooled=Object.fromEntries(names.map(k=>[k,Object.fromEntries(metrics.map(m=>[m,groups.reduce((s,v)=>s+v.assessed*v.models[k][m],0)/n]))]));
 let seed=722;const rnd=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
 const samples=Object.fromEntries(names.slice(1).map(k=>[k,metrics.map(()=>[])]));
 for(let draw=0;draw<2000;draw++){
  let den=0;const totals=names.slice(1).map(()=>metrics.map(()=>0));
  for(const group of groups){for(let j=0;j<group.blocks.length;j++){const b=group.blocks[Math.floor(rnd()*group.blocks.length)];den+=b.n;names.slice(1).forEach((k,i)=>metrics.forEach((_,m)=>totals[i][m]+=b[k][m]));}}
  names.slice(1).forEach((k,i)=>metrics.forEach((_,m)=>samples[k][m].push(totals[i][m]/den)));
 }
 const ci=Object.fromEntries(names.slice(1).map(k=>[k,Object.fromEntries(metrics.map((m,i)=>{const v=samples[k][i].sort((a,b)=>a-b);return [m,[v[49],v[1949]]]}))]));
 return {n,pooled,ci,week_blocks:groups.map(g=>g.blocks.length),state:"HOLD",certified_cases:0};
}
if(require.main===module){if(!process.argv[2])throw Error('archive directory required');const results={};for(let i=0;i<files.length;i++){const b=fs.readFileSync(path.join(process.argv[2],files[i]));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==pins[i])throw Error('pin');results[files[i]]=replay(JSON.parse(b),i%2?306:380)}console.log(JSON.stringify({results,summary:summarize(results)},null,2));}
module.exports={replay,summarize};
