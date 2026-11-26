/* Synthetic structural preflight regression tests; no network. */
const assert=require("node:assert/strict");
const {structuralCheck}=require("../live_core_statsbomb_structural_preflight.cjs");
function events(){
 const es=[];
 const add=(period,timestamp,name,team,extra={})=>es.push({index:es.length+1,id:String(es.length+1),period,timestamp,type:{name},team:{id:team},...extra});
 for(const team of [1,2])add(1,"00:00:00.000","Starting XI",team,{tactics:{lineup:Array.from({length:11},(_,i)=>({player:{id:team*100+i}}))}});
 add(1,"00:10:00.000","Shot",1,{shot:{statsbomb_xg:.3}});
 add(1,"00:30:00.000","Foul Committed",1,{player:{id:101},foul_committed:{card:{name:"Red Card"}}});
 add(1,"00:45:00.000","Half End",1);
 add(2,"00:45:00.000","Half End",2);
 return es;
}
assert.equal(structuralCheck(events(),1,2),true);
for(const [mutate,expected] of [
 [x=>x[3].timestamp="00:09:00.000","EVENT_TIME_REGRESSION"],
 [x=>x[3].id=x[2].id,"EVENT_ORDER"],
 [x=>x[3].player.id=999,"NON_ROSTER_RED_REVIEW"],
 [x=>x[2].shot.statsbomb_xg=2,"MISSING_OR_INVALID_XG"],
 [x=>x[4].timestamp="00:44:00.000","SHORT_PERIOD"]
]){
 const e=events();mutate(e);assert.throws(()=>structuralCheck(e,1,2),{message:expected});
}
console.log("6 synthetic structural preflight checks passed");
