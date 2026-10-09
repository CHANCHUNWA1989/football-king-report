# 足球王者 V4.1｜克羅地亞 Prva NL 即場亞洲盤研究擴充（2026-10-09）

## 研究案例：NK Sesvete vs NK Jadran Luka Ploče

- 截圖：2026-10-09 上半場 30:09，0–0，角球 0–1，無紅黃牌。
- 根據 Sofascore [比賽頁](https://www.sofascore.com/football/match/nk-jadran-luka-ploce-nk-sesvete/XKwsRCRb) 比賽原定 **13:00 UTC** 開始；截圖上的手機鐘/球賽分鐘不等於有博彩公司數據時點簽署。
- 雙方賽前各 7 場：塞瓦特 9 入 8 失（聯賽第7），賈德蘭 12 入 7 失（聯賽第1）。資料：[Forebet 賽前積分榜](https://www.forebet.com/en/football/matches/nk-sesvete-jadran-luka-plo%C4%8De-2517607)。
- 用戶提供的**歷史截圖**市場（不是現在可執行的價格）：全場大1.5 @1.81、小1.5 @1.99、大1.75 @2.06、小1.75 @1.74、大1.25 @1.52、小1.25 @2.38；主隊 +0.25 @1.76 / 客 -0.25 @2.06；主0 @2.19 / 客0 @1.66；主 +0.5 @1.53 / 客 -0.5 @2.40。**不儲存用戶帳戶或完整手機截圖。**
- **即場 shot-on-target、xG、危險攻勢、球隊官方傷停和可執行的 quote timestamp 尚未核實**。根據現有六大聯賽模型，不能假稱已校準克羅地亞 1.NL。
- 目前「小1.75 @1.74」僅是市場觀察，不是正式入場建議：假設餘下 Poisson 入球平均 1.7，理論 EV 約 -1%；不同強度會變，所以不能單純由 30' 0–0 推導獲利。

## 新增功能

1. **`ops/live_market_research.py`**：可從 JSON 案例輸入任何已結構化的克羅地亞 1.NL 即場亞洲全場大小球及讓球市場。對 0.25 / 0.75 行使各 50% 下注腿的半贏／半輸／走盤數學；記錄 screenshot/source 預測時點和 bookmaker `updated_utc`。
2. 現時輸入案例沒有 bookmaker 報價更新時間，所以自動 `HOLD`；即使未來手動提供時間，仍需**外部獨立 stats + 校準 model + 當刻可買 bookmaker** 才有足夠條件做真正價值判斷。
3. **`ops/croatia_fixture_probe.py`**：免費每次最多兩個端點，TheSportsDB V1 [搜尋賽事](https://www.thesportsdb.com/docs_api_guide)（不超過免費版限制）+ SportScore [按日期賽事查詢](https://sportscore.com/developers/api/)（免費免 Key，商用或對外展示需遵守其署名條件）；**只探測同一比賽姓名與 UTC 開賽時間**。即使兩個站都成功，不證明上游獨立性、盤口、xG 或正 EV。
4. 自動 **`.github/workflows/football-king-croatia-live-research.yml`**：新程式推送主分支執行一次，亦可以手動工作流程。內含 12 項截圖盤口、亞洲盤收益的單元測試、2 次免費比賽來源探測、匿名安全統計與 GitHub Artifact。此案例**不設無意義每日重複監察**。
5. 新功能**不改動**原有六大聯賽、The Odds API 1X2 免費配額保留線、完場封存、模型校準及投資/下注權限。

## 免費 API 能做與不能做

- [The Odds API V4](https://the-odds-api.com/liveapi/guides/v4/index.html) 的官方清單支持 `totals`、`spreads`，但文檔明確指出主要適用美國體育及部分博彩公司，額外市場可能按事件／方案收費並消耗較多積分；**不能承諾克羅地亞 Prva NL 有即場亞洲 1.75 或 -0.25 盤**，不得增加六大聯賽現有定時消耗。
- [TheSportsDB 免費 API](https://www.thesportsdb.com/docs_api_guide)：是賽事發現/日期候選資料，而非已證實的亞洲博彩公司賠率。免費 search events 每次可能只有一個結果。
- [SportScore](https://sportscore.com/developers/)：免 Key，免費資料公開展示需**可見的「Powered by SportScore」超連結**；現時 workflow 只保存安全計數而不會顯示原始來源足球分數或搬運原始視頻。
- **唔可以**透過爬取 Sofascore 或 Flashscore 的非公開端點去繞過授權限制，亦不可用未經核實 2026 現季來源當作另一個獨立博彩公司報價。

## 安全規則

- 報價失效／來源更新時間缺失／來源不可信／市場類型不一致／球隊同名但 ID 不一致：`HOLD`。
- Poisson 係**假設強度敏感度**，不是球隊真實勝率；未有足夠按「賽事時間點」訓練的前瞻樣本，不能以估值當 1X2 模型預測。
- 正式下注與自動推送 = `DISABLED`，所有結果屬研究。
- 現有 18 場封存、0 完場可評估樣本，仍要獨立真實完場樣本（至少 300 等有證據的驗證門檻），唔會因新增克羅地亞支援即時解鎖。
- 只有在使用者把新的**賽況／射正／xG／投注畫面**提供過來時，才考慮重新評估；舊賠率不會被當成現價。
