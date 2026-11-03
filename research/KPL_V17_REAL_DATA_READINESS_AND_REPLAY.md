# KPL V17｜預測準確率實證：資料資格及逐局時間順序Elo回測

日期：2026-11-03（中國標準時間 UTC+08）

## 1. 前置審計與真正問題

PR #398 (V16) 已經處理「以EDG.M領先2:1直接推斷G4勝率較高」嘅方法問題，但冇一個真正使用歷史資料、按時間逐局更新的簡單預測基線。先前嘅GitHub CI全部成功只證明合成輸入行為正確，**唔代表KPL方向預測改善**。

V17增加**實際計算概率嘅Elo研究基線**、時間順序重播、整個BO7系列賽分組測試及與50:50基線比較。重點係逐局預測先於賽果公開、係咪確實改善Brier與Log Loss、並防止挑選成功預測先結算。

## 2. 2026-11-03 WB–EDG.M嘅可信來源盤點

| 欄位 | 來源 | 可否納入實測 |
|---|---|---|
| 第1至3局賽果及重大轉折 | KPL官方認證微博，新浪新聞轉載，日期2026-11-03 18:44、19:17、19:51 | 有逐局官方戰報佐證，但尚欠全系列各局獨立ID、原始更新捕獲時刻；不構成完整BO7回測樣本 |
| WB 4:2 EDG.M及G4–G6賽果 | 維基百科當日賽事表 | 第三方條目；官方最終逐局資料未獨立核實，不把它作已驗證模型結算 |
| G4–G6完整Ban/Pick | 未取得當日可證明事前存在嘅快照 | HOLD |
| G4各分鐘金錢、塔、龍區、陣容 | 未取得當時時戳／授權來源 | HOLD |
| 第四局可成交盤口 | 未取得可核實平台及報價時間 | HOLD；唔宣稱市場正EV |
| 不同網站比分 | ARENA與虎牙部分頁面仍顯示0:0，明顯延遲 | 不作即時ground truth |

具體來源：
- 官方G1戰報：https://3g.sina.com.cn/news/detail/5361239930179321.html
- 官方G2戰報：https://3g.sina.com.cn/news/detail/5361248166481423.html
- 官方G3戰報：https://3g.sina.com.cn/news/detail/5361256752220737.html
- 尚待第二官方來源交叉核實嘅賽事紀錄：https://zh.wikipedia.org/wiki/王者荣耀职业联赛2026年年度总决赛
- 可能過期嘅賽事站：https://arena.zswclub.com/hok/2026-kpl-grand-finals/schedule 及 https://www.huya.com/kpl

## 3. 公開歷史資料及使用權限

非官方 https://github.com/Fire-Phoenixs/kpl-bp-dataset 自述包含2019–2026年33個賽事、約11,141小局、其中9,817局完整BP；來源係騰訊公開網頁接口。但資料整理者明確採用 **CC BY-NC 非商業整理**，並聲明賽事原始數據權利歸原權利人。這些係資料集維護者之自述，未獨立核對其每筆來源；**整理項目開源並唔等於授權投注模型使用或轉售原始賽事數據**。本PR唔下載、拷貝或鏡像該資料集任何受限原始數據。

准入前應核對：
1. 逐局battle_id與match_id、英雄BP及賽果身份一致，且覆蓋完整BO系列賽；只要缺一局就HOLD。
2. 每次模型預測時間及其可見資料集時刻；歷史資料係事後發布嘅話，不能扮成賽前已封存預測。
3. 來源真實、資料取得／商業用途／再發布授權、賽事版本與選手、局內數據取自相同patch及觀測時間。
4. 賽前盤口原始報價，包含書商、時間、可成交性及去水基線；未有則只可比較50:50基線，不能宣稱超越莊家。

## 4. 新增研究模組（非正式推薦）

`research/kpl_v17_elo_replay.py` 函數 `replay_elo_shadow(rows, model_frozen_at, elo_k, elo_scale, train_fraction, ...)`：

- 只接受明確嘅series_id、局數、patch_id、兩隊固定team_id、當局賽前forecast_at、開局game_start_at、結果公開result_observed_at、資料來源類別等欄位。
- 一場BO7必須由Game1開始完整、局數連續，恰好有其中一隊第四勝作結；若不完整、賽後加局、同局重複、換隊名／patch或時間次序倒流全部拒絕。
- **預測前**只更新result_observed_at嚴格早於該局forecast_at嘅前局結果；就算同一系列賽前局已經打完，但資料仲未公開，模型都唔准使用。
- Elo k、scale、資料切分及政策凍結時間作為預先宣告參數；額外必須傳入整個系列賽評估母體 `registered_series_ids` 及事前登記時間 `universe_registered_at`，任何缺少、重新排序或賽後移除整場系列賽均拒絕；同時拒絕跨局重複來源摘要（但摘要未經外部認證）；patch_id不同則不跨patch挪用舊ratings。只係基礎Elo研究模型，無BP、經濟、龍區權重。
- 樣本外期間採用**prequential online update**：先預測、其後賽果公開先更新，下一局可用已公開賽果；超參數唔可以事後按測試組表現挑選。報告需明示其係線上順序更新，而唔係完全凍結模型參數的靜態holdout。
- 時間分割必須按整個BO系列賽，訓練組結果全部早於第一個測試組預測；不足最少系列賽數、局數則HOLD。
- 同固定50:50（唔係市場盤口）比較Brier、Log Loss、方向準確率與覆蓋率、ECE；以完整BO系列賽為cluster做配對bootstrap。即使合成數據靚，都只標記synthetic，絕不當作真實KPL模型改善。事前母體登記時刻亦係自填聲明，無可信外部封存時仍然唔能證明未被事後改寫。
- `source_record_sha256` 只保證輸入哈希字串格式；無獨立簽章和來源payload核對時唔證明內容真實。

**所有輸出固定 status=HOLD、real_kpl_accuracy_verified=False、live_execution_allowed=False、production_recommendations=DISABLED、positive_ev_verified=False（合成或自述licensed都一樣）。** 無抓取、無發盤或下注。

## 5. 測試與後續驗收

`ops/tests/test_kpl_v17_elo_replay.py`：26項合成測試，包含前局未公布時唔可以偷用、調換未來賽果唔可以改寫其之前預測、跨patch重置、完整BO7驗證、時間倒填、訓練結果晚於測試預測、資料來源級別混用、惡意資料類型、重複來源摘要、事後刪除一場系列賽／母體登記過遲、是否優於50:50等。

```bash
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v17_elo_replay.py' -v
python -m unittest discover -s ops/tests -q
```

### 未達成／不能冒稱
- 未接入具有清晰權利、足夠時戳嘅KPL真實歷史BP、賽果及賽前報價。
- 未計算可發表嘅真實KPL樣本外Brier、Log Loss、命中率、正EV。
- 未訓練BP或即場經濟模型、未證明G4可賽前選WB；避免事後答案倒灌。
- PR #399繼續 Draft 堆疊於 #398；前面所有未合併研究PR必須先經獨立審計。正式推薦/投注全部HOLD。
