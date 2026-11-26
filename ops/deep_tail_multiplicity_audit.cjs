// Retrospective statistics only; no prospective or release evidence.
const fs=require('node:fs'),crypto=require('node:crypto'),path=require('node:path');
const refs=[["5c9ce5577b23e4a6c78552cda129f8f2946ec01e","research/deep_tail_mixture_bootstrap_20261127.json","4da0a6c0542de17f59d705545929672affb06ccc"],["0c2912cb6a702fad03e3168d61b02361854a43fe","research/deep_tail_cross_league_transfer_20261127.json","3ad1a4922f4d075522852cde01365309e187ad7d"]];
function audit(cohorts){
 const metrics=["ll","tail","over25","ah_m2","score_ll"],models=["independent_mix","shared_mix"],keys=Object.keys(cohorts).sort(),groups=keys.map(k=>cohorts[k]),leagues=[...new Set(keys.map(k=>k.split("/")[1].split(".")[0]))].sort();
 if(keys.length!==10||leagues.length!==5)throw Error("scope");
 for(const c of groups){if(!Array.isArray(c.blocks)||!c.blocks.length||c.blocks.some(b=>!Number.isInteger(b.n)||b.n<1||models.some(m=>!Array.isArray(b[m])||b[m].length!==5||b[m].some(x=>!Number.isFinite(x))))||c.blocks.reduce((s,b)=>s+b.n,0)!==c.assessed)throw Error("blocks");for(const m of models)for(let j=0;j<5;j++){const expected=c.models.poisson[metrics[j]]-c.models[m][metrics[j]];if(!Number.isFinite(expected)||Math.abs(c.blocks.reduce((s,b)=>s+b[m][j],0)/c.assessed-expected)>1e-10)throw Error("reconciliation");}}
 function point(ks){const n=ks.reduce((s,k)=>s+cohorts[k].assessed,0);return Object.fromEntries(models.map(m=>[m,Object.fromEntries(metrics.map((v,j)=>[v,ks.reduce((s,k)=>s+cohorts[k].blocks.reduce((t,b)=>t+b[m][j],0),0)/n]))]));}
 const draws=20000, family=10, alpha=.05, samples=models.map(()=>metrics.map(()=>[]));let seed=725;
 function rnd(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
 for(let d=0;d<draws;d++){let n=0;const sums=models.map(()=>metrics.map(()=>0));for(const g of groups)for(let i=0;i<g.blocks.length;i++){const b=g.blocks[Math.floor(rnd()*g.blocks.length)];n+=b.n;for(let m=0;m<2;m++)for(let j=0;j<5;j++)sums[m][j]+=b[models[m]][j];}for(let m=0;m<2;m++)for(let j=0;j<5;j++)samples[m][j].push(sums[m][j]/n);}
 function interval(v,a){return [v[Math.floor((a/2)*(v.length-1))],v[Math.ceil((1-a/2)*(v.length-1))]];}
 const estimates=point(keys),intervals=Object.fromEntries(models.map((m,i)=>[m,Object.fromEntries(metrics.map((k,j)=>{const v=samples[i][j].sort((a,b)=>a-b);return [k,{delta:estimates[m][k],nominal95:interval(v,alpha),bonferroni995:interval(v,alpha/family)}]}))]));
 const leaveOne=Object.fromEntries(leagues.map(l=>[l,point(keys.filter(k=>k.split("/")[1].split(".")[0]!==l))]));
 const perLeague=Object.fromEntries(leagues.map(l=>[l,point(keys.filter(k=>k.split("/")[1].split(".")[0]===l))]));
 return {n:groups.reduce((s,c)=>s+c.assessed,0),blocks:groups.reduce((s,c)=>s+c.blocks.length,0),draws,family,intervals,leaveOne,perLeague,state:"HOLD",certified_cases:0};
}
if(require.main===module){const root=process.argv[2]||'.';const data=refs.map(([,file,pin])=>{const b=fs.readFileSync(path.join(root,file));if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==pin)throw Error('pin');return JSON.parse(b).results;});if(Object.keys(data[0]).some(k=>k in data[1]))throw Error('overlap');console.log(JSON.stringify(audit({...data[0],...data[1]}),null,2));}
module.exports={audit};
