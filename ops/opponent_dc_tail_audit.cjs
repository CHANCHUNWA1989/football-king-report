// Offline research only; input must be pinned OpenFootball files.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const files=["2023-24/en.1.json","2023-24/de.1.json","2024-25/en.1.json","2024-25/de.1.json"],pins=["f62b11dfaf06cffd1236c2777caebb880a0cfea1","2c41078e751d914f24bfe7e55c5567cea70a4aee","504f2e732fbc3c9caeb98e4382b13b094453b840","9921b1d8485429913ff6d161500beb519d8b0e51"];
function replay(doc,expected){
 const clip=x=>Math.max(.2,Math.min(5,x)), factor=x=>Math.max(.5,Math.min(2,x));
 const rows=doc.matches.slice().sort((a,b)=>a.date.localeCompare(b.date)||a.team1.localeCompare(b.team1)||a.team2.localeCompare(b.team2));
 if(rows.length!==expected)throw Error("count");
 const seen=new Set(),teams=new Map();
 for(const r of rows){const f=r.score?.ft,k=r.team1+"\0"+r.team2;if(!/^\d{4}-\d{2}-\d{2}$/.test(r.date)||!Array.isArray(f)||f.length!==2||f.some(x=>!Number.isInteger(x)||x<0)||!r.team1||!r.team2||r.team1===r.team2||seen.has(k))throw Error("fixture");seen.add(k);}
 const get=t=>{if(!teams.has(t))teams.set(t,{hn:0,an:0,hf:0,ha:0,af:0,aa:0,hfe:0,hae:0,afe:0,aae:0,hrf:0,hra:0,arf:0,ara:0});return teams.get(t)};
 const names=["venue","venue_dc","opponent_blend","opponent_blend_dc"],stats=Object.fromEntries(names.map(k=>[k,{ll:0,draw_brier:0,tail_brier:0,score_ll:0,hit:0,ah_m2_brier:0}]));
 function forecast(h,a,rho,x,y){
  h=clip(h);a=clip(a);
  function pois(l){const p=[Math.exp(-l)];for(let k=1;k<=30;k++)p.push(p[k-1]*l/k);return p}
  const H=pois(h),A=pois(a),p=[0,0,0],ah=[0,0,0];let mass=0,tail=0,exact=0;
  for(let i=0;i<=30;i++)for(let j=0;j<=30;j++){
   const tau=i===0&&j===0?1-h*a*rho:i===0&&j===1?1+h*rho:i===1&&j===0?1+a*rho:i===1&&j===1?1-rho:1;
   const v=H[i]*A[j]*tau;if(v<0||!Number.isFinite(v))throw Error("grid");
   mass+=v;p[i>j?0:i===j?1:2]+=v;ah[i-j>2?0:i-j===2?1:2]+=v;if(Math.abs(i-j)>=3)tail+=v;if(i===x&&j===y)exact=v;
  }
  if(Math.abs(mass-1)>1e-8)throw Error("mass");
  return {p:p.map(v=>v/mass),ah:ah.map(v=>v/mass),tail:tail/mass,exact:exact/mass};
 }
 let n=0,gh=0,ga=0,assessed=0,draws=0,tails=0;
 for(let i=0;i<rows.length;){
  let j=i+1;while(j<rows.length&&rows[j].date===rows[i].date)j++;
  const batch=rows.slice(i,j),updates=[];
  const H=clip(n?gh/n:1.5),A=clip(n?ga/n:1.2),s=8;
  for(const r of batch){
   const [x,y]=r.score.ft,h=get(r.team1),a=get(r.team2);
   const ho=(h.hf+s*H)/(h.hn+s)/H,ad=(a.aa+s*H)/(a.an+s)/H,ao=(a.af+s*A)/(a.an+s)/A,hd=(h.ha+s*A)/(h.hn+s)/A;
   const hv=H*ho*ad,av=A*ao*hd;
   const rh=H*factor((h.hrf+s*H)/(h.hfe+s*H))*factor((a.ara+s*H)/(a.aae+s*H));
   const ra=A*factor((a.arf+s*A)/(a.afe+s*A))*factor((h.hra+s*A)/(h.hae+s*A));
   if(n>=60){
    const o=x>y?0:x===y?1:2,grade=x-y>2?0:x-y===2?1:2,tail=Math.abs(x-y)>=3?1:0;
    const configs=[[hv,av,0],[hv,av,-.04],[(hv+rh)/2,(av+ra)/2,0],[(hv+rh)/2,(av+ra)/2,-.04]];
    for(let k=0;k<names.length;k++){const z=forecast(...configs[k],x,y),m=stats[names[k]];
     m.ll-=Math.log(Math.max(z.p[o],1e-12));m.draw_brier+=(z.p[1]-(o===1?1:0))**2;m.tail_brier+=(z.tail-tail)**2;m.score_ll-=Math.log(Math.max(z.exact,1e-12));m.hit+=z.p.indexOf(Math.max(...z.p))===o?1:0;m.ah_m2_brier+=z.ah.reduce((t,v,l)=>t+(v-(l===grade?1:0))**2,0);
    }
    assessed++;draws+=o===1?1:0;tails+=tail;
   }
   updates.push({h,a,x,y,hfe:H*ad,aae:H*ho,afe:A*hd,hae:A*ao});
  }
  for(const u of updates){const {h,a,x,y}=u;h.hn++;h.hf+=x;h.ha+=y;a.an++;a.af+=y;a.aa+=x;h.hfe+=u.hfe;h.hae+=u.hae;a.afe+=u.afe;a.aae+=u.aae;h.hrf+=x;h.hra+=y;a.arf+=y;a.ara+=x;n++;gh+=x;ga+=y;}
  i=j;
 }
 return {raw:n,assessed,draws,tails,models:Object.fromEntries(names.map(k=>[k,Object.fromEntries(Object.entries(stats[k]).map(([m,v])=>[m,v/assessed]))])),state:"HOLD",certified_cases:0};
}
if(require.main===module){if(!process.argv[2])throw Error('archive directory required');const out={};for(let i=0;i<files.length;i++){const b=fs.readFileSync(path.join(process.argv[2],files[i]));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==pins[i])throw Error('pin');out[files[i]]=replay(JSON.parse(b),i%2?306:380)}console.log(JSON.stringify(out,null,2))}
module.exports={replay};
