// Research only. Regulation final scores; same fixture and as-of required upstream.
// Feasibility of next-goal marginals, not calibration, authentication or EV.
export function audit(current, rows, next) {
  const eps=1e-9;
  const goal=x=>Number.isSafeInteger(x)&&x>=0;
  const prob=x=>typeof x==="number"&&Number.isFinite(x)&&x>=0&&x<=1;
  const fail=reason=>({decision:"HOLD",activation:"DISABLED",coherent:false,reason});
  if(!current||!goal(current.home)||!goal(current.away)||!Array.isArray(rows)||rows.length===0||rows.length>10000) return fail("invalid_grid");
  if(!next||![next.home,next.away,next.none].every(prob)||Math.abs(next.home+next.away+next.none-1)>eps) return fail("invalid_next_mass");
  let none=0,homeOnly=0,awayOnly=0,both=0;
  const seen=new Set();
  for(const r of rows){
    if(!r||!goal(r.home)||!goal(r.away)||r.home<current.home||r.away<current.away||!prob(r.p))return fail("invalid_terminal_cell");
    const key=r.home+":"+r.away;
    if(seen.has(key))return fail("duplicate_terminal_cell");
    seen.add(key);
    if(r.home===current.home&&r.away===current.away)none+=r.p;
    else if(r.away===current.away)homeOnly+=r.p;
    else if(r.home===current.home)awayOnly+=r.p;
    else both+=r.p;
  }
  if(Math.abs(none+homeOnly+awayOnly+both-1)>eps)return fail("invalid_terminal_mass");
  const bounds={none:[none,none],home:[homeOnly,homeOnly+both],away:[awayOnly,awayOnly+both]};
  const violations=Object.keys(bounds).filter(k=>next[k]<bounds[k][0]-eps||next[k]>bounds[k][1]+eps);
  return {decision:"HOLD",activation:"DISABLED",coherent:violations.length===0,reason:violations.length?"incompatible_marginals":"algebraically_feasible_only",bounds,violations,groups:{none,homeOnly,awayOnly,both}};
}
export function runSelfTests(){
  let count=0; const check=(v,label)=>{if(!v)throw Error(label);count++;};
  const cur={home:0,away:2},grid=[{home:0,away:2,p:.25},{home:1,away:2,p:.25},{home:0,away:3,p:.3},{home:1,away:3,p:.2}];
  const good={home:.35,away:.4,none:.25};
  check(audit(cur,grid,good).coherent,"feasible");
  check(audit(cur,grid,{home:.25,away:.5,none:.25}).coherent,"lower bound");
  check(audit(cur,grid,{home:.45,away:.3,none:.25}).coherent,"upper bound");
  check(!audit(cur,grid,{home:.1,away:.65,none:.25}).coherent,"home below");
  check(!audit(cur,grid,{home:.5,away:.25,none:.25}).coherent,"away below");
  check(!audit(cur,grid,{home:.35,away:.35,none:.3}).coherent,"none mismatch");
  check(!audit(cur,grid,{home:.35,away:.4,none:.2}).coherent,"next sum");
  check(!audit(cur,grid,{home:NaN,away:.4,none:.25}).coherent,"NaN");
  check(!audit(cur,grid,{home:true,away:.4,none:.25}).coherent,"boolean");
  check(!audit(cur,grid.concat(grid[0]),good).coherent,"duplicate");
  check(!audit(cur,grid.slice(1),good).coherent,"missing mass");
  check(!audit(cur,[{home:0,away:1,p:1}],{home:0,away:0,none:1}).coherent,"score rewind");
  check(audit(cur,[{home:0,away:2,p:1}],{home:0,away:0,none:1}).coherent,"all no goal");
  check(audit(cur,[{home:2,away:4,p:1}],{home:.99,away:.01,none:0}).coherent,"both score");
  check(audit(cur,grid,good).decision==="HOLD"&&audit(cur,grid,good).activation==="DISABLED","never activate");
  check(audit(cur,[...grid].reverse(),good).coherent,"order");
  for(let i=1;i<=512;i++){
    const a=(i%19+1),b=(i%23+1),c=(i%29+1),d=(i%31+1),t=a+b+c+d,x=(i%101)/100;
    const g=[{home:0,away:2,p:a/t},{home:1,away:2,p:b/t},{home:0,away:3,p:c/t},{home:1,away:3,p:d/t}];
    check(audit(cur,g,{none:a/t,home:(b+x*d)/t,away:(c+(1-x)*d)/t}).coherent,"stress feasible "+i);
    check(!audit(cur,g,{none:a/t,home:0,away:1-a/t}).coherent,"stress impossible "+i);
  }
  return count;
}
