// Research-only contract self-test. Synthetic fixtures; never evidence of predictive performance.
// Run: node selftest.mjs
function cases(){
 const ok={id:"test-1",forecast:100,kickoff:200,market:90,resultAt:300,sourceGroups:["official","independent"],resultVerified:true,p:[.6,.25,.15],m:[.5,.3,.2],y:0,synthetic:false};
 return [
 ["eligible",ok,true],["one source",{...ok,sourceGroups:["official"]},false],["syndicated",{...ok,sourceGroups:["feed-a","feed-a"]},false],["missing identity",{...ok,id:""},false],["future market",{...ok,market:101},false],["late forecast",{...ok,forecast:200},false],["early result",{...ok,resultAt:199},false],["unverified result",{...ok,resultVerified:false},false],["synthetic",{...ok,synthetic:true},false],["missing provenance flag",{...ok,synthetic:undefined},false],["bad probability",{...ok,p:[.6,.4,.4]},false],["negative probability",{...ok,p:[-.1,.5,.6]},false],["boolean result",{...ok,y:true},false],["invalid time",{...ok,market:NaN},false],["missing source group",{...ok,sourceGroups:["official",""]},false]];
}

function assess(r){
 const prob=p=>Array.isArray(p)&&p.length===3&&p.every(x=>typeof x==="number"&&Number.isFinite(x)&&x>=0&&x<=1)&&Math.abs(p.reduce((a,b)=>a+b,0)-1)<1e-6;
 return typeof r.id==="string"&&r.id.trim().length>0&&[r.forecast,r.kickoff,r.market,r.resultAt].every(Number.isFinite)&&r.market<=r.forecast&&r.forecast<r.kickoff&&r.resultAt>r.kickoff&&Array.isArray(r.sourceGroups)&&r.sourceGroups.every(x=>typeof x==="string"&&x.trim().length>0)&&new Set(r.sourceGroups.map(x=>x.trim().toLowerCase())).size>=2&&r.resultVerified===true&&r.synthetic===false&&prob(r.p)&&prob(r.m)&&[0,1,2].includes(r.y);
}

function score(rows){
 const ids=new Set();let n=0, brier=0, marketBrier=0,log=0,marketLog=0;
 for(const r of rows){if(!assess(r)||ids.has(r.id))continue;ids.add(r.id);n++;brier+=r.p.reduce((s,v,i)=>s+(v-Number(i===r.y))**2,0);marketBrier+=r.m.reduce((s,v,i)=>s+(v-Number(i===r.y))**2,0);log-=Math.log(Math.max(r.p[r.y],1e-15));marketLog-=Math.log(Math.max(r.m[r.y],1e-15));}
 return {n,brier:n?brier/n:null,marketBrier:n?marketBrier/n:null,logLoss:n?log/n:null,marketLogLoss:n?marketLog/n:null,production_recommendations:"DISABLED",release:"HOLD"};
}

function run(){
 let results=cases().map(([name,row,expected])=>({name,pass:assess(row)===expected}));
 const row=cases()[0][1],s=score([row,row,{...row,id:"bad",synthetic:true}]),empty=score([]);
 results.push({name:"dedupe",pass:s.n===1},{name:"Brier",pass:Math.abs(s.brier-.245)<1e-12},{name:"market Brier",pass:Math.abs(s.marketBrier-.38)<1e-12},{name:"log loss",pass:Math.abs(s.logLoss+Math.log(.6))<1e-12},{name:"empty not zero",pass:empty.n===0&&empty.brier===null},{name:"always HOLD",pass:s.release==="HOLD"&&s.production_recommendations==="DISABLED"},{name:"reject all invalid",pass:score(cases().slice(1).map(x=>x[1])).n===0});
 return results;
}
const results=run();
console.log(JSON.stringify({passed:results.filter(x=>x.pass).length,total:results.length,results},null,2));
if(results.some(x=>!x.pass)) throw new Error('contract failed');
