# J3 客勝／和局風險：主客場分拆資料準入（2026-11-15 HKT）

**狀態：HOLD / DISABLED。** 本研究 PR 只加入正確切分及時序安全驗證器，沒有獲得任何 J3 原始授權資料、真正認證比分、校準機率、最新盤口或投注執行權限。

## 滋賀 vs FC大阪分析缺口

- **2026-11-15 晚間更新**：J.League 官方完整賽事頁 https://www.jleague.jp/en/match/j3/2026/111516/ 已明示 **Full Time，滋賀 1–1 FC大阪**，實際列示18:03 JST開賽（**17:03 香港時間**）。原先讀取到嘅 LIVE 快照已過時。原聊天研究方向「FC大阪客勝」按90分鐘1X2屬 **FULL_LOSS**，不可再列為待完場；但仍非獨立驗證兩個上游結果、亦非實際注單結算。
- 前述「FC大阪客勝 @1.91」為對話中的研究方向，並非證明由現在六大聯賽模型生成的封存預測，更沒有可核實實際成交賠率。
- **首次真實官方結果觀察**：`research/audits/2026-11-15-j3-shiga-osaka-official-ft-research.json` 保存**精簡事實記錄及官方原頁連結**（非來源HTML、非授權原文重製、非獨立加密原件）；`ops/j3_postmatch_reference.py` 加 `ops/tests/test_j3_shiga_osaka_official_ft_research.py` 嚴格驗證此賽事固定身份、比分、來源及防止自稱「已認證」標記。來源網頁曾於現時查閱時顯示FT，但資料檔並未封存來源原始bytes、精準擷取時戳或不可篡改認證。**禁止把賽後1–1放回賽前作客歷史樣本，或者當作2026/27 J3已認證樣本外模型勝率。**
- `ops/research_recommender.py` 只覆蓋英超／英冠／德甲／西甲／意甲／法甲；`ops/jleague_research_audit.py` 研究的是 **2025 J1回顧性資料**，不能把J1樣本當成J3當季已認證模型。
- 因此之前發現的「總戰績與作客勝率混淆、和局風險未認證」不能用一場比分事後調權，亦不能宣稱 J3 命中率已提高。

## 本次 `ops/j3_venue_split_shadow.py` 安全輸入

輸入是**明確由來源持有人提供**的資料，不會自行下載來源；拒絕缺值、重複、錯聯賽／賽季、同隊主客、未完場、非法比分及晚於賽前截點的記錄。

- 目標賽事：`league=j3`、`season=2026-27`、來源原生賽事 `event_id`、主客來源原生球隊ID及可辨認時區的 `kickoff_utc`。
- 研究截點 `as_of_utc` 必須比目標開球早至少10分鐘。
- 過往每場完整紀錄：來源賽事ID、同聯賽／同賽季主客球隊ID、確切開球、聲稱90分鐘 `match_status=FT`、`home_goals`、`away_goals`、`final_observed_utc` 和當次 `archived_utc`。
- 所有過往紀錄必須開球先於聲稱FT，聲稱FT先於封存，封存先於本次截點。僅依照**主隊主場**及**客隊作客**來計數勝／和／負；唔會混入客隊主場或其他聯賽／季別。
- **2026-11-15 防重複補丁**：不再只比較來源 `event_id` 或完全相同嘅 UTC 開球時間。對同一日本當地日期（JST，UTC+9），只要任何一隊被記錄為進行兩場 J3 比賽，即整批資料 `AMBIGUOUS_LOCAL_MATCHDAY_TEAM` 拒絕；避免不同來源ID、改期／開球時刻偏差導致同場重複計數。**不同球隊同日各有賽事仍然合法**。這是保守研究隔離規則，未經官方原件核實不可自行「去重後繼續計勝率」。回歸：先在 `c403b76ef309` 證實兩項失敗，再由 `35a812022afd` 修正。
- `draw_fraction_unverified` 是輸入歷史比分的描述性比例，**不是當場和局概率，更不是校準後勝率**。

即使所有metadata合理，亦**不代表原件未被更改、來源真實獨立、賽事實際完場或賽前封存獲驗證**。本模組永遠 `independently_certified_history_cases=0`、`calibrated_draw_probability_available=false`、`positive_ev_verified=false`、`bookmaker_odds=null`、`bet_eligible=false`、`production_recommendations=DISABLED`。CI測試只用完全標明合成的對手、勝和負記錄，不能當真實FC大阪／滋賀戰績。

## 下一個證據閘門

1. **J3來源**：確認合法／可用嘅2026-27全季 J3 賽事 ID、主客球隊身份、正式開球與完場（原始資料 SHA-256、來源內容、擷取時間及授權）。
2. **獨立來源**：於受控環境核對第二真正獨立上游；相同網站比分不等於已驗證獨立性，並核對官方90分鐘FT及賽事改期。
3. **同場賽前封存**：比賽開波前已有不可事後改寫的模型版本、訓練資料截點、概率輸出、正選資訊狀態及賠率觀察時間。
4. **樣本外校準**：固定分層評估方法，比較J3客勝、和局模型與同場市場基準，分別記錄真實命中、Brier、Log Loss、信賴區間；不能用FC大阪一場調門檻。
5. **外部審核**：保持 Draft，待非作者review及全CI通過後再決定是否合併。禁止自動投注或聲稱已驗證EV。

指令（研究CI）：

```bash
python -m unittest discover -s ops/tests -p 'test_j3_venue_split_shadow.py' -v
python -m unittest discover -s ops/tests -q
```
