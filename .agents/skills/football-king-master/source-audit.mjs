import {readFileSync} from 'node:fs';
// Historical manual observations only: not source authentication.
const fixture=JSON.parse(readFileSync(new URL('./historical-evidence.json',import.meta.url),'utf8'));
function checks(f){
 const clone=()=>JSON.parse(JSON.stringify(f));
 const c=[["score",clone(),"score","CORROBORATED_HISTORICAL"],["red",clone(),"redIdentity","CORROBORATED_HISTORICAL"],["minute",clone(),"redMinute","AGREES_UPSTREAM_UNKNOWN"],["xg",clone(),"xg","HISTORICAL_SINGLE_SOURCE"],["market",clone(),"market","MISSING"],["no forward",clone(),"forwardEligible",false],["no live",clone(),"liveEligible",false]];
 const m=(n,fn,k,w)=>{const x=clone();fn(x);c.push([n,x,k,w]);};
 m("one publisher",x=>x.sources=x.sources.slice(0,1),"score","HOLD");
 m("duplicate publisher",x=>x.sources[1].publisher="uefa","score","HOLD");
 m("wrong fixture",x=>x.sources[1].fixture="UEFA:999","score","HOLD");
 m("score conflict",x=>x.sources[1].score=[4,1],"score","HOLD");
 m("player conflict",x=>x.sources[1].red.player="Other","redIdentity","HOLD");
 m("side conflict",x=>x.sources[1].red.side="home","redIdentity","HOLD");
 m("minute conflict",x=>x.sources[2].red.minute=45,"redMinute","HOLD");
 m("state conflict",x=>x.sources[2].red.scoreBefore=[3,0],"redMinute","HOLD");
 m("missing minute",x=>x.sources[2].red.minute=null,"redMinute","HOLD");
 m("invalid minute",x=>x.sources[0].red.minute=-1,"redMinute","HOLD");
 m("unknown xg",x=>delete x.sources[2].xg,"xg","MISSING");
 m("invalid xg",x=>x.sources[2].xg.values=[-1,2],"xg","HOLD");
 m("live xg label",x=>x.sources[2].xg.scope="live","xg","HOLD");
 m("unverified quote",x=>x.market={line:.5},"market","UNVERIFIED");
 m("wrong kind",x=>x.kind="live","score","HOLD");
 m("non https",x=>x.sources[1].url="http://www.reuters.com/a","score","HOLD");
 m("spoof host",x=>x.sources[1].url="https://www.reuters.com.evil.test/a","score","HOLD");
 m("spoof flags",x=>{x.forwardEligible=true;x.production_recommendations="ENABLED"},"forwardEligible",false);
 c.push(["null record",null,"score","HOLD"]);return c;
}
function audit(f){
 const o={score:"HOLD",redIdentity:"HOLD",redMinute:"HOLD",xg:"MISSING",market:"MISSING",forwardEligible:false,liveEligible:false,release:"HOLD",production_recommendations:"DISABLED"};
 if(!f||f.kind!=="historical_manual_review"||typeof f.fixture!=="string"||!Array.isArray(f.sources))return o;
 o.market=f.market==null?"MISSING":"UNVERIFIED";
 const s=f.sources, hosts={uefa:/^https:\/\/(?:www\.)?uefa\.com\//,reuters:/^https:\/\/(?:www\.)?reuters\.com\//,fotmob:/^https:\/\/(?:www\.)?fotmob\.com\//};
 if(s.some(x=>!x||x.fixture!==f.fixture||!Object.hasOwn(hosts,x.publisher)||typeof x.url!=="string"||!hosts[x.publisher].test(x.url))||new Set(s.map(x=>x.publisher)).size!==s.length)return o;
 const a=s.filter(x=>x.publisher==="uefa"&&x.role==="official"),b=s.filter(x=>x.publisher==="reuters"&&x.role==="independent_editorial");
 if(a.length!==1||b.length!==1)return o;
 const pair=x=>Array.isArray(x)&&x.length===2&&x.every(v=>Number.isInteger(v)&&v>=0),eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 if(!pair(a[0].score)||s.some(x=>!pair(x.score)||!eq(x.score,a[0].score)))return o;
 o.score="CORROBORATED_HISTORICAL";
 const r=a[0].red;
 if(r&&typeof r.player==="string"&&r.player.trim()&&["home","away"].includes(r.side)&&s.every(x=>x.red?.player===r.player&&x.red?.side===r.side)){
 o.redIdentity="CORROBORATED_HISTORICAL";const ms=s.filter(x=>x.red.minute!=null);
 if(Number.isInteger(r.minute)&&r.minute>=1&&r.minute<=130&&pair(r.scoreBefore)&&ms.length>=2&&ms.every(x=>x.red.minute===r.minute&&pair(x.red.scoreBefore)&&eq(x.red.scoreBefore,r.scoreBefore)))o.redMinute="AGREES_UPSTREAM_UNKNOWN";
 }
 const xs=s.filter(x=>x.xg!=null);
 if(xs.length){const v=xs[0].xg;o.xg=xs.length===1&&xs[0].publisher==="fotmob"&&v.scope==="full_time"&&Array.isArray(v.values)&&v.values.length===2&&v.values.every(n=>typeof n==="number"&&Number.isFinite(n)&&n>=0)?"HISTORICAL_SINGLE_SOURCE":"HOLD";}
 return o;
}
const results=checks(fixture).map(([name,f,k,w])=>{const o=audit(f);return {name,pass:o[k]===w&&o.release==="HOLD"&&o.production_recommendations==="DISABLED"};});
console.log(JSON.stringify({passed:results.filter(x=>x.pass).length,total:results.length,results,historical:audit(fixture)},null,2));
if(results.some(x=>!x.pass))process.exitCode=1;
