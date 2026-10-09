"""Add iPhone-first six-league accuracy hub without exposing API credentials.

Client reads static public JSON, never calls the paid/free external API and
never contains raw bookmaker price quotes. All untrusted content is inserted as
textContent (no dynamic innerHTML).
"""
import argparse
from pathlib import Path

CSS = """
#fk-hub{border:1px solid #64748b44;border-radius:18px;padding:16px;margin:18px 0;background:linear-gradient(140deg,#0f172a,#183249);color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif}
#fk-hub *{box-sizing:border-box}
#fk-hub h2{font-size:1.25rem;color:#f8fafc;margin:0 0 7px}
#fk-hub .fk-note{font-size:.88rem;color:#cbd5e1;line-height:1.5}
#fk-hub .fk-alert{border-left:4px solid #f59e0b;padding:8px 10px;background:#48330a;border-radius:6px;font-weight:650;margin:12px 0}
#fk-hub .fk-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}
#fk-hub .fk-stat{border:1px solid #64748b55;background:#0b1728;border-radius:12px;padding:12px}
#fk-hub .fk-stat strong{font-size:1.3rem;display:block;color:#f8fafc}
#fk-hub .fk-stat small{font-size:.76rem;color:#cbd5e1;display:block;margin-bottom:4px}
#fk-hub .fk-controls{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
#fk-hub select,#fk-hub input{flex:1 1 175px;font:inherit;min-width:0;min-height:44px;padding:9px 10px;border:1px solid #64748b;border-radius:9px;color:#0f172a;background:#fff}
#fk-hub .fk-card{border:1px solid #64748b55;border-radius:11px;padding:11px;margin:9px 0;background:#10263b}
#fk-hub .fk-card h3{color:#f1f5f9;font-size:1rem;margin:0 0 5px}
#fk-hub .fk-card p{color:#cbd5e1;font-size:.85rem;margin:4px 0;line-height:1.45}
#fk-hub .fk-chip{display:inline-block;font-size:.76rem;border-radius:9px;border:1px solid #94a3b866;padding:3px 6px;margin-right:6px;color:#e2e8f0}
#fk-hub a{color:#a5d8ff}
#fk-hub .fk-empty{padding:10px;border:1px dashed #94a3b866;border-radius:9px;color:#cbd5e1}
#fk-hub .fk-legend{font-size:.76rem;color:#cbd5e1}
@media(min-width:680px){#fk-hub .fk-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){#fk-hub *{transition:none!important;animation:none!important}}
""".strip()

JS = r"""(() => {
'use strict';
const root=document.getElementById('fk-hub');
if(!root)return;
const byId=id=>document.getElementById(id);
const all=['epl','championship','bundesliga','laliga','seriea','ligue1'];
const names={epl:'英超',championship:'英冠',bundesliga:'德甲',
             laliga:'西甲',seriea:'意甲',ligue1:'法甲'};
const human=v=>typeof v==='number'&&Number.isFinite(v)?String(v):'—';
const percent=p=>typeof p==='number'&&Number.isFinite(p)?(p*100).toFixed(1)+'%':'—';
function el(tag,cls,text){
  const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(text!==undefined)n.textContent=String(text);
  return n;
}
function stat(host,label,value){
  const item=el('div','fk-stat');
  item.append(el('small','',label),el('strong','',value));
  host.append(item);
}
function note(host,value){host.append(el('p','',value));}
function card(host,title,lines){
  const box=el('article','fk-card');
  box.append(el('h3','',title));
  lines.forEach(line=>note(box,line));
  host.append(box);
}
async function getJSON(path){
  const response=await fetch(path,{cache:'no-store'});
  if(!response.ok)throw Error('公開資料暫不可讀');
  const text=await response.text();
  if(text.length>2500000)throw Error('資料長度異常');
  return JSON.parse(text);
}
const leagueSelect=byId('fk-league');
const search=byId('fk-search');
all.forEach(code=>{
  const o=el('option','',names[code]);o.value=code;leagueSelect.append(o);
});
let center=null,shadow=null,paired=null,gate=null;
function draw(){
  if(!center||!shadow||!paired||!gate)return;
  const summary=byId('fk-summary');
  const groups=byId('fk-leagues');
  const fixtures=byId('fk-games');
  summary.replaceChildren();
  groups.replaceChildren();
  fixtures.replaceChildren();
  const selected=leagueSelect.value;
  const phrase=search.value.trim().toLocaleLowerCase();
  stat(summary,'公開市場賽事',human(center.total_market_fixtures));
  stat(summary,'賽前候選概率',human(center.total_shadow_candidates));
  stat(summary,'合資格市場配對',human(center.total_strict_market_pairs));
  stat(summary,'已結算對照樣本',human(center.total_completed_comparable_samples));
  const q=center.free_quota||{};
  byId('fk-quota').textContent=
    '免費查詢餘額：'+human(q.remaining)+'／500；最後賠率擷取：'+
    (center.market_age_utc||'尚未取得')+'（UTC）';
  const eligible=center.league_cards||[];
  eligible.filter(c=>selected==='all'||c.id===selected).forEach(c=>{
    const desc=[
      '兩個來源開賽時間一致：'+human(c.two_source_kickoff_agreements)+
       '／有明確開賽時間 '+human(c.precise_scheduled_kickoffs),
      '今次市場嚴格配對 '+human(c.strict_pre_match_pairs_current_run)+
       ' 場；已結算 '+human(c.settled_held_out_samples)+' 場',
      '賽果完全獨立核實：否'+
       (c.unconfirmed_kickoff_alerts?'；時間差異待檢查 '+human(c.unconfirmed_kickoff_alerts)+' 場':''),
    ];
    if(c.comparison&&c.settled_held_out_samples){
      desc.push('探索性 Log Loss 模型／市場：'+
       human(c.comparison.model_log_loss)+'／'+human(c.comparison.market_log_loss)+
       '；樣本未達正式驗證門檻');
    }
    card(groups,c.name,desc);
  });
  let forecast=Array.isArray(shadow.predictions)?shadow.predictions:[];
  forecast=forecast.filter(f=>(selected==='all'||f.league===selected)
      &&(!phrase||(String(f.home)+' '+String(f.away)).toLocaleLowerCase().includes(phrase)));
  const matches=Array.isArray(paired.comparisons)?paired.comparisons:[];
  const matched=new Set(matches.map(m=>String(m.league)+'|'+String(m.home)+'|'+String(m.away)+'|'+String(m.kickoff_utc)));
  if(!forecast.length){
    fixtures.append(el('p','fk-empty','呢個篩選暫時冇符合研究條件嘅賽前預測。'));
  } else {
    forecast.slice(0,80).forEach(f=>{
      const key=String(f.league)+'|'+String(f.home)+'|'+String(f.away)+'|'+String(f.kickoff_utc);
      const isPaired=matched.has(key);
      const lines=[
        '開賽 UTC：'+String(f.kickoff_utc||'未確認'),
        '研究概率 主／和／客：'+[f.p_home,f.p_draw,f.p_away].map(percent).join('／'),
        '市場時間點配對：'+(isPaired?'合資格（仍未驗證模型優勢）':'未合資格／沒有可比較市場'),
        '固定 A/B 候選：'+[f.ab_candidate_p_home,f.ab_candidate_p_draw,f.ab_candidate_p_away].map(percent).join('／')+
        '（未經校準、不得自動取代基線）'
      ];
      card(fixtures,(names[f.league]||'未知聯賽')+'｜'+String(f.home)+' — '+String(f.away),lines);
    });
  }
  const ab=center.aggregate_metrics?.ab_research;
  const model= center.aggregate_metrics;
  byId('fk-metrics').textContent=
    !model?'已結算合資格樣本：0，暫無可用校準／Log Loss 實證。':
    '已結算樣本：'+human(model.settled_games)+
    '；Log Loss 模型／市場：'+human(model.model_log_loss)+'／'+human(model.market_log_loss)+
    '；A/B 同場比較：'+human(ab?.same_case_count)+'（探索性，未獨立驗證）';
  byId('fk-production').textContent='正式投注建議：HOLD。'+
    '原因：'+String(gate.reason||'證據不足')+
    '。絕不會因成功部署或者模型概率差距而自動開放。';
}
Promise.all(['research_center.json','shadow.json','market_comparison.json',
             'production_gate.json'].map(getJSON))
.then(([a,b,c,d])=>{
  if(a.production_recommendations!=='DISABLED'||
     b.production_recommendations!=='DISABLED'||
     c.production_recommendations!=='DISABLED'||
     d.production_recommendations!=='DISABLED'){
    throw Error('安全檢查未通過');
  }
  center=a;shadow=b;paired=c;gate=d;
  draw();
})
.catch(()=>{
  byId('fk-production').textContent=
   'HOLD：無法核實最新研究資料，請稍後重新整理或查看 GitHub 運行紀錄。';
  byId('fk-games').append(el('p','fk-empty','資料讀取失敗，唔會展示未驗證概率。'));
});
leagueSelect.addEventListener('change',draw);
search.addEventListener('input',draw);
})();""".strip()


def inject(site):
    site=Path(site)
    page=site/"index.html"
    content=page.read_text(encoding="utf-8")
    if "<" not in content or "</body>" not in content:
        raise ValueError("HTML_BODY_REQUIRED_FOR_RESEARCH_HUB")
    if 'id="fk-hub"' in content:
        raise ValueError("DUPLICATE_RESEARCH_HUB")
    control=(
        '<link rel="stylesheet" href="research_hub.css">'
        '<section id="fk-hub" aria-labelledby="fk-hub-title">'
        '<h2 id="fk-hub-title">足球王者｜六聯賽研究與實證中心</h2>'
        '<p class="fk-note">此處只顯示公開研究概率與獨立基準，'
        '並非博彩公司可買價，亦未證明投注回報。</p>'
        '<p class="fk-alert" id="fk-production" role="status">正式投注建議：HOLD</p>'
        '<div id="fk-summary" class="fk-stats" aria-live="polite"></div>'
        '<p id="fk-quota" class="fk-note">免費市場餘額讀取中</p>'
        '<div class="fk-controls">'
        '<label for="fk-league">聯賽篩選</label>'
        '<select id="fk-league"><option value="all">全部六聯賽</option></select>'
        '<label for="fk-search">搜尋球隊</label>'
        '<input id="fk-search" type="search" placeholder="輸入球隊名稱" autocomplete="off">'
        '</div><h3>各聯賽數據覆蓋與真實評分</h3><div id="fk-leagues"></div>'
        '<h3>今次賽前研究候選（不是投注建議）</h3>'
        '<div id="fk-games"></div>'
        '<p id="fk-metrics" class="fk-legend">待核對已結算樣本</p>'
        '<p class="fk-legend">雙來源賽程時間一致 ≠ 已核實賽果；'
        '模型與市場有差異 ≠ 可盈利；所有新模型都先留在 Shadow Mode。</p>'
        '<p><a href="research_center.json">完整六聯賽實證資料</a>｜'
        '<a href="production_gate.json">正式建議資格審核</a></p>'
        '</section><script src="research_hub.js" defer></script>'
    )
    if '<h2>近期賽程與賽果</h2>' in content:
        content=content.replace('<h2>近期賽程與賽果</h2>',control+'<h2>近期賽程與賽果</h2>',1)
    else:
        content=content.replace("</body>",control+"</body>",1)
    page.write_text(content,encoding="utf-8")
    (site/"research_hub.css").write_text(CSS+"\n",encoding="utf-8")
    (site/"research_hub.js").write_text(JS+"\n",encoding="utf-8")
    return {"dashboard_visible":True,"script":"research_hub.js",
            "css":"research_hub.css","secrets_embedded":False}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",default="app/site")
    args=parser.parse_args()
    print(inject(args.site))
