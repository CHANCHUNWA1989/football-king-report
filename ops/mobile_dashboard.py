"""Add iPhone-first six-league accuracy hub without exposing API credentials.

Client reads static public JSON, never calls the paid/free external API and
never contains raw bookmaker price quotes. All untrusted content is inserted as
textContent (no dynamic innerHTML).
"""
import argparse
import html
import json
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
#fk-hub .fk-recommendations{margin:16px 0;padding:12px;border:1px solid #64748b88;border-radius:14px;background:#081a2b}
#fk-hub .fk-recommendations h3{color:#f8fafc;font-size:1.09rem;margin:6px 0}
#fk-hub .fk-recommendations .fk-card{border-left:3px solid #38bdf8}
#fk-hub .fk-recommendations .fk-observation .fk-card{border-left:3px solid #64748b}
#fk-hub .fk-rec-count{font-weight:600;color:#dbeafe}
#fk-hub .fk-recommendations .fk-caveat{font-size:.82rem;color:#f8c97a;line-height:1.5}
#fk-hub .fk-model-only{border:1px dashed #f59e0b99;border-radius:12px;padding:10px;margin:15px 0;background:#25220e}
#fk-hub .fk-model-only h3{margin:3px 0 7px;font-size:1rem;color:#f8c97a}
#fk-hub .fk-model-only .fk-card{border-left:3px solid #f59e0b;background:#242a35}


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
let center=null,shadow=null,paired=null,gate=null,recommendations=null;
function freshTenHours(iso){
  const stamp=Date.parse(iso||'');
  const age=Date.now()-stamp;
  return Number.isFinite(stamp)&&age>=-5*60*1000&&age<=10*60*60*1000;
}
function isCurrentResearch(){
  return center&&center.status==='RESEARCH_ONLY'&&
    recommendations&&recommendations.status==='RESEARCH_ONLY'&&
    freshTenHours(center.generated_utc)&&
    freshTenHours(recommendations.as_of_utc);
}
function renderRecommendationCards(selected,phrase){
  const host=byId('fk-picks');
  const reviewHost=byId('fk-review');
  const modelHost=byId('fk-model-only-list');
  host.replaceChildren();
  reviewHost.replaceChildren();
  modelHost.replaceChildren();
  byId('fk-model-only-section').hidden=true;
  if(!isCurrentResearch()){
    byId('fk-pick-count').textContent='HOLD：網站或研究候選已過期，暫停顯示選向';
    host.append(el('p','fk-empty','研究資料超過10小時、時間異常或報告狀態HOLD。請重新整理核對最新賽事。'));
    return;
  }
  if(!recommendations||recommendations.selection_mode!=='SHADOW_RESEARCH_ONLY'){
    host.append(el('p','fk-empty','候選推薦資料未能安全核實；暫不提供研究選向。'));
    return;
  }
  const fits=p=>(selected==='all'||p.league===selected)&&
    (!phrase||(String(p.home)+' '+String(p.away)).toLocaleLowerCase().includes(phrase));
  const qualified=(recommendations.selections||[]).filter(fits);
  const review=(recommendations.reviews||[]).filter(fits);
  byId('fk-pick-count').textContent=
    '研究首選 '+qualified.length+' 場；需要觀察 '+review.length+
    ' 場（符合資訊安全條件先展示，其他賽事會略過）';
  if(!qualified.length)host.append(el('p','fk-empty','目前冇合資格研究首選：唔會為咗湊數而硬推賽事。'));
  qualified.forEach((p,i)=>{
    const lines=[
      '方向：'+String(p.direction_zh)+'｜模型未校準機率：'+percent(p.research_probability),
      '開賽時間（UTC）：'+String(p.kickoff_utc),
      ...((Array.isArray(p.reasons)?p.reasons:[]).slice(0,4)),
      '只供研究排序；非正EV、非下注提示、冇投注金額。'
    ];
    card(host,(i+1)+'. '+(names[p.league]||'未知聯賽')+'｜'+
      String(p.home)+' — '+String(p.away),lines);
  });
  review.slice(0,8).forEach(p=>{
    const reason=(Array.isArray(p.reasons)?p.reasons:[]).slice(0,4);
    card(reviewHost,(names[p.league]||'未知聯賽')+'｜'+
      String(p.home)+' — '+String(p.away),
      ['模型暫選 '+String(p.direction_zh)+'，但未符合研究首選條件',...reason]);
  });
  if(!review.length)reviewHost.append(el('p','fk-note','目前冇額外觀察名單。'));
  const fallback=byId('fk-model-only-section');
  const active=recommendations.fallback_mode==='MODEL_ONLY_LOW_EVIDENCE';
  fallback.hidden=!active;
  if(active){
    const raw=Array.isArray(recommendations.model_only_watchlist)?
      recommendations.model_only_watchlist:[];
    const selectedModels=raw.filter(fits);
    const reasons={
      FREE_ODDS_QUOTA_NEAR_LIMIT:'免費賠率額度已到達保留線',
      NO_CURRENT_FREE_MARKET_DATA:'目前無可比較嘅新鮮賠率',
      NO_STRICT_MARKET_MATCHES:'暫時未有符合時序嘅市場配對',
      MARKET_TIME_VALIDITY_REJECTED:'市場報價時間條件未通過'
    };
    byId('fk-model-only-reason').textContent=
      (reasons[recommendations.fallback_reason]||'免費市場條件不足')+
      '；只顯示較明顯嘅未校準模型方向，證據等級比市場配對首選低。';
    if(!selectedModels.length)
      modelHost.append(el('p','fk-empty','暫時冇達到最低模型選向門檻嘅觀察賽事。'));
    selectedModels.forEach((p,i)=>{
      card(modelHost,(i+1)+'. '+(names[p.league]||'未知聯賽')+'｜'+
        String(p.home)+' — '+String(p.away),[
        '純模型觀察：'+String(p.direction_zh)+'，未校準概率 '+percent(p.research_probability),
        '開賽（UTC）：'+String(p.kickoff_utc),
        ...((Array.isArray(p.reasons)?p.reasons:[]).slice(0,4)),
        '無市場賠率核實，非正式投注建議，唔提供下注金額。'
      ]);
    });
  }
}

function draw(){
  if(!center||!shadow||!paired||!gate||!recommendations)return;
  const summary=byId('fk-summary');
  const groups=byId('fk-leagues');
  const fixtures=byId('fk-games');
  summary.replaceChildren();
  groups.replaceChildren();
  fixtures.replaceChildren();
  const selected=leagueSelect.value;
  const phrase=search.value.trim().toLocaleLowerCase();
  renderRecommendationCards(selected,phrase);
  stat(summary,'公開市場賽事',human(center.total_market_fixtures));
  stat(summary,'賽前候選概率',human(center.total_shadow_candidates));
  stat(summary,'合資格市場配對',human(center.total_strict_market_pairs));
  stat(summary,'已結算對照樣本',human(center.total_completed_comparable_samples));
  const q=center.free_quota||{};
  byId('fk-quota').textContent=
    '上次已保存賠率時嘅免費餘額：'+human(q.remaining)+'／500；最後賠率擷取：'+
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
             'production_gate.json','research_selections.json'].map(getJSON))
.then(([a,b,c,d,e])=>{
  if(a.production_recommendations!=='DISABLED'||
     b.production_recommendations!=='DISABLED'||
     c.production_recommendations!=='DISABLED'||
     d.production_recommendations!=='DISABLED'||
     e.production_recommendations!=='DISABLED'||
     e.selection_mode!=='SHADOW_RESEARCH_ONLY'||
     e.automatic_bets!==false||
     e.validated_positive_expected_value!==false){
    throw Error('安全檢查未通過');
  }
  center=a;shadow=b;paired=c;gate=d;recommendations=e;
  draw();
})
.catch(()=>{
  byId('fk-production').textContent=
   'HOLD：無法核實最新研究資料，請稍後重新整理或查看 GitHub 運行紀錄。';
  byId('fk-games').append(el('p','fk-empty','資料讀取失敗，唔會展示未驗證概率。'));
});
leagueSelect.addEventListener('change',draw);
search.addEventListener('input',draw);
// A Safari tab that remains open overnight must NOT keep displaying old picks.
setInterval(draw, 60*1000);
document.addEventListener('visibilitychange',draw);
window.addEventListener('pageshow',draw);
})();""".strip()


def inject(site):
    site=Path(site)
    page=site/"index.html"
    content=page.read_text(encoding="utf-8")
    if "<" not in content or "</body>" not in content:
        raise ValueError("HTML_BODY_REQUIRED_FOR_RESEARCH_HUB")
    if 'id="fk-hub"' in content:
        raise ValueError("DUPLICATE_RESEARCH_HUB")
    provider_names = {
        "thesportsdb": "TheSportsDB",
        "api_football": "API-Football",
        "football_data_org": "football-data.org",
        "sportmonks": "Sportmonks",
    }
    status_path = site/"extra_sources.json"
    details = {}
    if status_path.is_file():
        try:
            details = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            details = {}
    provider_notes = []
    translated = {
        "PARTIAL_COVERAGE": "已接通（免費覆蓋有限）",
        "NOT_CONFIGURED": "等你加入免費 API Key",
        "HOLD": "來源暫停／不可用",
        "PARTIAL": "部分資料取得成功",
        "NO_FIXTURES_RETURNED": "已嘗試，但暫時冇賽事",
        "NOT_YET_COLLECTED": "未有有效採集紀錄",
    }
    for provider in details.get("providers", []):
        if not isinstance(provider, dict) or provider.get("provider") not in provider_names:
            continue
        name = provider_names[provider["provider"]]
        state = translated.get(provider.get("status"), "尚未核實")
        if (provider.get("provider") == "api_football"
                and provider.get("configured") is True
                and provider.get("status") == "HOLD"):
            state = "Key 已設定，免費當季賽程／1X2 賠率未能取得；並非 Key 失效"
        count = provider.get("sampled_fixture_count", 0)
        count = count if type(count) is int and 0 <= count <= 300 else 0
        provider_notes.append(
            "<li><strong>" + html.escape(name) + "</strong>：" +
            html.escape(state) + "；賽程樣本 " + str(count) + " 場</li>")
    source_section = (
        '<section id="fk-extra-sources" class="fk-card" aria-label="其他免費足球數據渠道">'
        '<h3>四個額外免費資料渠道</h3>'
        '<p class="fk-note">呢啲資料只用作賽程／賽果來源覆蓋檢查，'
        '唔會假扮博彩公司1X2即時報價或者正式投注推薦。</p>'
        '<ul>' + ("".join(provider_notes) if provider_notes
                    else "<li>等待第一輪免費來源採集。</li>") + '</ul>'
        '<p class="fk-note">另有兩來源開賽時間一致：' +
        html.escape(str(details.get("matched_kickoff_agreements", 0))) + ' 場；'
        '資料差異需要核對：' +
        html.escape(str(details.get("kickoff_disagreements_needing_review", 0))) + ' 場。</p>'
        '<p><a href="extra_sources.json">查看四個來源更新狀態與限制</a></p>'
        '<p class="fk-note">Football data provided by the Football-Data.org API。'
        '免費版本實際啟用範圍、延遲及使用權請以供應商條款為準。</p>'
        '</section>')
    control=(
        '<link rel="stylesheet" href="research_hub.css">'
        '<section id="fk-hub" aria-labelledby="fk-hub-title">'
        '<h2 id="fk-hub-title">足球王者｜六聯賽研究與實證中心</h2>'
        '<p class="fk-note">此處只顯示公開研究概率與獨立基準，'
        '並非博彩公司可買價，亦未證明投注回報。</p>'
        '<p class="fk-alert" id="fk-production" role="status">正式投注建議：HOLD</p>'
        '<div class="fk-recommendations" id="fk-recommendations">'
        '<h3>今日研究首選｜主勝・和局・客勝</h3>'
        '<p class="fk-caveat">呢度會主動揀方向、解釋原因，但屬未校準的研究篩選；'
        '唔係實際下注建議，亦唔代表有正期望值或勝率保證。</p>'
        '<p class="fk-rec-count" id="fk-pick-count">研究候選讀取中</p>'
        '<div id="fk-picks" aria-live="polite"></div>'
        '<h3>其他值得觀察（未達研究首選條件）</h3>'
        '<div id="fk-review"></div>'
        '<p><a href="research_selections.json">研究候選及篩選原因（JSON）</a></p>'
        '</div>'
        '<div id="fk-model-only-section" class="fk-model-only" hidden>'
        '<h3>免費賠率不足｜純模型低證據觀察</h3>'
        '<p class="fk-caveat" id="fk-model-only-reason">'
        '低證據研究方向，未獲博彩公司市場確認；不能用作下注訊號。</p>'
        '<div id="fk-model-only-list" aria-live="polite"></div>'
        '</div>'
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
        '</section>' + source_section + '<script src="research_hub.js" defer></script>'
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
