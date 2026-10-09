"""Attach a no-secret, automatically refreshed German football source widget.

GitHub Pages is static; this widget fetches our own public, server-validated
snapshot (NOT an unbounded third-party API) on demand in Safari. It never
touches the bookmaker odds budget or modifies research selections.
"""
import argparse
from pathlib import Path

CSS = """
#fk-german-live{margin:14px 0;padding:15px;border:1px solid #64748b66;border-radius:14px;background:#0b2034;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif}
#fk-german-live h2{color:#f1f5f9;font-size:1.1rem;margin:0 0 8px}
#fk-german-live p,#fk-german-live li{font-size:.85rem;line-height:1.5;color:#cbd5e1}
#fk-german-live .gl-note{padding:9px;background:#24324b;border-radius:8px}
#fk-german-live .gl-controls{display:flex;align-items:center;flex-wrap:wrap;gap:9px;margin:10px 0}
#fk-german-live select,#fk-german-live button{min-height:42px;border:1px solid #94a3b8;border-radius:9px;padding:8px 10px;font:inherit}
#fk-german-live button{background:#dbeafe;color:#0f172a;cursor:pointer}
#fk-german-live select{background:#fff;color:#0f172a;min-width:145px}
#fk-german-live .gl-event{margin:8px 0;padding:10px;border-radius:9px;background:#172e42;border:1px solid #62748955}
#fk-german-live .gl-event h3{font-size:.91rem;color:#f1f5f9;margin:0 0 4px}
#fk-german-live .gl-event p{margin:3px 0}
#fk-german-live .gl-dispute{border-left:4px solid #f59e0b}
#fk-german-live .gl-verified{border-left:4px solid #38bdf8}
#fk-german-live .gl-muted{font-size:.77rem;color:#cbd5e1}
#fk-german-live a{color:#b9d8ff}
""".strip()

JS = r"""(() => {
'use strict';
const ROOT=document.getElementById('fk-german-live');
if(!ROOT)return;
const URI='https://raw.githubusercontent.com/CHANCHUNWA1989/football-king-report/main/sources/live_germany_latest.json';
const names={bundesliga:'德甲',bundesliga2:'德乙',germany_liga3:'德丙'};
const messages={
  SINGLE_COMMUNITY_SOURCE:'單一社群來源，未獨立核實',
  TWO_PUBLISHER_KICKOFF_AGREEMENT:'OpenLigaDB＋TheSportsDB開賽時間一致',
  KICKOFF_CONFLICT_REVIEW:'兩來源開賽時間不一致，待覆核',
  FINISHED_SCORE_CONFLICT_REVIEW:'兩來源完場比分有分歧，待覆核'
};
const state=document.getElementById('gl-status');
const holder=document.getElementById('gl-games');
const filter=document.getElementById('gl-league');
const btn=document.getElementById('gl-refresh');
let snapshot=null;
function element(tag,className,text){
  const x=document.createElement(tag);
  if(className)x.className=className;
  if(text!==undefined)x.textContent=String(text);
  return x;
}
function hold(reason){
  holder.replaceChildren();
  state.textContent='HOLD｜'+reason;
  holder.append(element('p','gl-note','目前唔會展示未驗證或過期賽事。原有模型同賠率資料不受影響。'));
}
function localTime(s){
  const d=new Date(s);
  return Number.isFinite(d.getTime())?
    new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',
      month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',
      hour12:false}).format(d)+'（香港）':'時間未確認';
}
function isFresh(s){
  const d=Date.parse(s||'');
  const age=Date.now()-d;
  return Number.isFinite(d)&&age>=-5*60*1000&&age<=150*60*1000;
}
function draw(){
  if(!snapshot||snapshot.schema!=='football-king-openligadb-hourly-v1'||
     snapshot.production_recommendations!=='DISABLED'||
     snapshot.live_second_by_second_guaranteed!==false||
     !isFresh(snapshot.collected_utc)||
     snapshot.status!=='RESEARCH_ONLY'){
    hold('德國賽事快照超過150分鐘、時間異常，或者來源故障');
    return;
  }
  state.textContent='社群資料（非官方即時）｜最後查詢：'+
    localTime(snapshot.collected_utc)+'｜開波時間如有改動，等下一輪確認';
  holder.replaceChildren();
  const choice=filter.value;
  const now=Date.now();
  const seen=new Set();
  const games=(Array.isArray(snapshot.matches)?snapshot.matches:[]).filter(g=>{
    const ko=Date.parse(g.kickoff_utc||'');
    if(!Number.isFinite(ko)||
       ko<now-5*60*60*1000||ko>now+4*24*60*60*1000||
       (choice!=='all'&&g.league!==choice))return false;
    const id=String(g.league)+'|'+String(g.provider_match_id);
    if(seen.has(id))return false;
    seen.add(id);
    return true;
  }).slice(0,30);
  if(!games.length){
    holder.append(element('p','gl-note','呢個日期窗口／聯賽暫時冇可展示嘅賽事；唔代表所有賽事已取消。'));
    return;
  }
  for(const g of games){
    const disputed=['KICKOFF_CONFLICT_REVIEW','FINISHED_SCORE_CONFLICT_REVIEW']
       .includes(g.crosscheck_state);
    const verified=g.crosscheck_state==='TWO_PUBLISHER_KICKOFF_AGREEMENT';
    const card=element('article','gl-event '+(disputed?'gl-dispute':verified?'gl-verified':''));
    card.append(element('h3','',(names[g.league]||'德國聯賽')+'｜'+
                  String(g.home||'未知')+' — '+String(g.away||'未知')));
    card.append(element('p','','開賽：'+localTime(g.kickoff_utc)));
    let phase=g.status==='SCHEDULED'?'未開賽':
        g.status==='FINISHED_CONFIRMED_BY_SOURCE'?'社群標示完場':
        g.status==='FINISHED_SCORE_PENDING'?'完場比分待確認':'已到開賽時間，實際賽況未核實';
    if(g.status==='FINISHED_CONFIRMED_BY_SOURCE'&&Array.isArray(g.score_ft))
      phase+=' '+g.score_ft.join('–');
    card.append(element('p','',phase));
    card.append(element('p','gl-muted',
      messages[g.crosscheck_state]||'單一社群來源；尚未完成雙來源核對'));
    holder.append(card);
  }
}
async function refresh(){
  btn.disabled=true;
  try{
    const r=await fetch(URI,{cache:'no-store'});
    if(!r.ok)throw Error('公共快照暫時不可用');
    const raw=await r.text();
    if(raw.length>400000)throw Error('超出可讀範圍');
    const parsed=JSON.parse(raw);
    if(!Array.isArray(parsed.matches)||!Array.isArray(parsed.league_coverage))
      throw Error('資料格式異常');
    snapshot=parsed; draw();
  }catch(e){snapshot=null;hold('無法連接經 GitHub 驗證嘅公開快照');}
  finally{btn.disabled=false;}
}
filter.addEventListener('change',draw);
btn.addEventListener('click',refresh);
window.addEventListener('pageshow',()=>snapshot?draw():refresh());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();else draw();},15*60*1000);
refresh();
})();""".strip()


def inject(site):
    site=Path(site)
    target=site/"index.html"
    html=target.read_text(encoding="utf-8")
    if "</body>" not in html or 'id="fk-german-live"' in html:
        raise ValueError("INVALID_OR_DUPLICATE_GERMAN_WIDGET")
    block=(
        '<link rel="stylesheet" href="german_live.css">'
        '<section id="fk-german-live" aria-label="德國聯賽免費社群比分和賽程">'
        '<h2>德甲・德乙・德丙｜免費賽程快速更新</h2>'
        '<p class="gl-note">OpenLigaDB 社群資料，每小時嘗試更新，'
        '唔保證即秒比分，亦唔屬投注預測。'
        '球賽時間及分數必須自行核對官方賽事來源。</p>'
        '<div class="gl-controls">'
        '<label for="gl-league">聯賽</label>'
        '<select id="gl-league"><option value="all">全部三聯賽</option>'
        '<option value="bundesliga">德甲</option>'
        '<option value="bundesliga2">德乙</option>'
        '<option value="germany_liga3">德丙</option></select>'
        '<button id="gl-refresh" type="button">重新讀取已驗證快照</button></div>'
        '<p id="gl-status" class="gl-muted" role="status">HOLD｜查詢時間及來源狀態中</p>'
        '<div id="gl-games" aria-live="polite"></div>'
        '<p class="gl-muted">來源：<a href="https://www.openligadb.de/">OpenLigaDB</a>'
        '，資料授權 <a href="https://www.openligadb.de/lizenz">ODbL</a>。'
        '另一來源：<a href="https://www.thesportsdb.com/">TheSportsDB</a>。'
        '兩來源時間一致只表示交叉觀測，唔證明賽果官方認證。</p>'
        '</section><script src="german_live.js" defer></script>'
    )
    html=html.replace("</body>",block+"</body>",1)
    target.write_text(html,encoding="utf-8")
    (site/"german_live.css").write_text(CSS+"\n",encoding="utf-8")
    (site/"german_live.js").write_text(JS+"\n",encoding="utf-8")
    return {"widget":"german_community_hourly",
            "odds_calls":0, "private_api_keys_embedded":False,
            "has_licence_attribution":True}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    opts=p.parse_args()
    print(inject(opts.site))
