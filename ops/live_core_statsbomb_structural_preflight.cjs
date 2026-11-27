/* Independent structural preflight, not the Python replay or calibration.
 * No provider payloads or match statistics are printed or stored.
 */
function structuralCheck(events,h,a){
 const need=(x,s)=>{if(!x)throw Error(s)},id=x=>Number.isInteger(x)&&x>0;
 need(id(h)&&id(a)&&h!==a,"FIXTURE");
 const teams=[h,a],roster=new Map(teams.map(x=>[x,new Set()])),sent=new Map(teams.map(x=>[x,new Set()])),xi=new Set(),ids=new Set();
 let lastIndex=0,p=0,t=0,ends=new Set(),non=false,closed=[];
 function close(){need(ends.size===1&&ends.has(t),"PERIOD_END");need(t>=2700000,"SHORT_PERIOD");closed.push(p)}
 need(Array.isArray(events)&&events.length&&events.length<=20000,"EVENT_LIST");
 for(const e of events){
  need(id(e.index)&&e.index>lastIndex&&typeof e.id==="string"&&e.id&&!ids.has(e.id),"EVENT_ORDER");
  lastIndex=e.index;ids.add(e.id);
  const k=e.period;need([1,2,3,4,5].includes(k),"PERIOD");
  const typ=e.type.name,card=(typ==="Foul Committed"?e.foul_committed:typ==="Bad Behaviour"?e.bad_behaviour:null)?.card?.name;
  if(k>2){if(!non){need(p===2&&ends.size===1&&ends.has(t),"NONREGULATION_BEFORE_REGULATION_END");non=true}continue}
  need(!non,"REGULATION_AFTER_NONREGULATION");
  if(k!==p){need(k===p+1,"PERIOD_ORDER");if(p)close();p=k;t=0;ends=new Set()}
  const m=typeof e.timestamp==="string"&&/^(\d{2}):([0-5]\d):([0-5]\d)\.(\d{3})$/.exec(e.timestamp);
  need(m,"EVENT_CLOCK");const ts=+m[1]*3600000+ +m[2]*60000+ +m[3]*1000+ +m[4];
  need(ts>=t&&ts<=6000000,"EVENT_TIME_REGRESSION");t=ts;
  const team=e.team.id;need(roster.has(team),"TEAM");const r=roster.get(team),s=sent.get(team);
  if(typ==="Half End")ends.add(t);
  if(typ==="Starting XI"){
   const players=e.tactics.lineup.map(v=>v.player.id);
   need(p===1&&t===0&&!xi.has(team)&&players.length===11&&new Set(players).size===11&&players.every(id),"STARTING_XI");
   players.forEach(x=>r.add(x));xi.add(team)
  }else if(typ==="Substitution"){
   const x=e.player.id,y=e.substitution.replacement.id;
   need(id(x)&&id(y)&&r.has(x)&&!r.has(y)&&!s.has(y),"SUBSTITUTION");r.delete(x);r.add(y)
  }
  if(card==="Red Card"||card==="Second Yellow"){
   const x=e.player?.id;need(id(x),"NATIVE_ID");need(!s.has(x),"DUPLICATE_DISMISSAL");
   need(r.has(x),"NON_ROSTER_RED_REVIEW");s.add(x);r.delete(x);need(s.size<=3,"RED_COUNT")
  }else need(card==null||card==="Yellow Card","UNKNOWN_CARD");
  if(typ==="Shot"){const v=e.shot.statsbomb_xg;need(typeof v==="number"&&Number.isFinite(v)&&v>=0&&v<=1,"MISSING_OR_INVALID_XG");need(xi.size===2,"MISSING_LINEUP")}
 }
 close();need(closed.join(",")==="1,2"&&xi.size===2,"INCOMPLETE_REGULATION");return true
}
if(typeof module!=="undefined")module.exports={structuralCheck};
