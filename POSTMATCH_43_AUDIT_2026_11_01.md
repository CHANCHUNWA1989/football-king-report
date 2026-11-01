# 10月31日43場封存研究｜2026-11-01獨立賽果覆盤

## 不改原始預測的來源鏈

- 原始資料：`research/slates/2026-10-31-hk-evening-unpriced.json`，**只在PR #355研究分支存在**，主分支未合併；本PR**不修改**原件。
- 本次核對的原始檔案 Git blob SHA：`a100c234c326e26fefa9b0fd96a65427c1b9ce63`；PR #355 當時 head commit：`309887b91dc6835ed6af521635fa526cfa1158dc`。
- **已獨立查出首個封存 commit**：`870f9d8cf5515cd004602b57d339fb7b48f1eda5`，GitHub author/committer 時間 **`2026-10-31T13:53:13Z`**，當時檔案 blob SHA `49c4fb6bfd735f292a767376eae309eb0afaa019`。JSON 自述 `13:53:11.016Z`，比 commit 時刻早約2秒；以 GitHub commit 時刻作可追溯公開提交證據。PR #355 建立 `13:55:23Z`，43場最早 `14:30Z` 開波，故**原始43場及四方向確在開波前封存**。比較首封與最新 head JSON：**只有**頂層 `fixtures_without_provider_ids_are_unverified` 由 `false` 改成 `true`，43場身份、開波時間及四方向全部無變。
- 43場、13聯賽、4條 ChatGPT **無成交價定性研究方向**、39場 `ABSTAIN`；20場原件欠 OddStorm 固定賽事 ID；`official_model_predictions=0`。開波前已開始的車路士對曼聯等3場仍不在43場內。
- 本PR新建獨立只讀審計 sidecar `research/audits/2026-10-31-hk-evening-43-postmatch-research-only.json`，每場保留封存賽事、開賽時刻、方向、兩個結果來源網址、比分、特殊狀態。**不可將新 sidecar 覆寫原件**。

## 兩來源逐場核實（來源分工）

- 第一個結果刊登者：Score+90 `https://scoreplus90.com/en/matches/2026-10-31`（42場）；德乙卡爾斯魯厄對海登咸以 Sport1/SID `https://www.sport1.de/news/fussball/2-bundesliga/2026/10/karlsruhe-schlaegt-heidenheim-wagner-mit-hannover-nun-letzter` 補充。
- 第二個結果刊登者：LiveScore 2026-11-01 所讀的各國賽果頁（英格蘭、德國、西班牙、意大利、荷蘭、比利時、葡萄牙、蘇格蘭、土耳其、沙特、法國），每場網址逐條保留於 JSON。
- **兩個不同網站不是兩條已證實互不共享的上游資料鏈**。因此本審計只稱「兩個刊登者吻合」，`upstream_data_independence_certified=false`；不得升格成主系統獨立已結算模型樣本。
- 四條研究方向另外核對 Manchester City 官方結果、Crystal Palace 官方及 Sky Sports、Borussia Dortmund 官方戰報、LaLiga 官方賽事頁；賽事ID、男女組別、主客及日期不可只用名稱模糊配對。

## 4條封存方向，五段規則（主隊比分在前）

| 封存case | 原方向（不是成交盤） | 2026-10-31實際比分 | 純盤線數學結果 | 解釋 |
|---|---|---|---|---|
| 005 | 白禮頓客隊 +1（只在未來價>=1.85才考慮） | 曼城 0–1 白禮頓 | `FULL_WIN` | 客隊本身贏一球 |
| 006 | 水晶宮客隊 +1（門檻>=2.00） | 熱刺 2–0 水晶宮 | `FULL_LOSS` | 客隊輸兩球 |
| 013 | 拜仁–多蒙特 全場細4（門檻>=1.90） | 2–2，合共4球 | `PUSH` | 整數4球線走盤，**不是贏** |
| 015 | 馬拉加客隊 +1.5（門檻>=1.95） | 貝迪斯 2–1 馬拉加 | `FULL_WIN` | 客隊輸一球但受讓1.5仍全贏 |

五段合計：`FULL_WIN=2, HALF_WIN=0, PUSH=1, HALF_LOSS=0, FULL_LOSS=1`。39場仍是棄選，絕不賽後挑贏家補方向。沒有真實可成交當時價格及獨立模型賽前概率，故 `EV/ROI/Brier/LogLoss=null`，不計正式命中率。

## 一項已發現的真實結果狀態錯誤：Cambuur 4–0 Go Ahead

- Score+90 將 `20261031-032` 顯示成一般比分 `4-0`，部分資料商標示 `FT`；LiveScore 顯示 `Aband.`，Sky Sports 明確寫 `Abandoned: Crowd`。
- **KNVB 官方 2026-11-01 公告** `https://www.knvb.nl/nieuws/organisatie/berichten/72372/cambuur-go-ahead-eagles-definitief-gestaakt`：81分鐘因煙火腰斬，賽會其後決定不補踢，**正式將當時4–0定為賽果**；荷甲官方 `https://eredivisie.nl/nieuws/sc-cambuur-go-ahead-eagles-definitief-gestaakt/` 亦確認。
- 所以 `4-0` 作為**官方裁定賽果**可以記錄，但**不是完成90分鐘的普通FT**。在未核對各博彩公司腰斬／裁定條款前，不可將之自動當正常投注結算，也不可混入正常90分鐘預測校準樣本。
- 此PR增加 `ops/postmatch_result_status_guard.py`：兩刊登者都普通FT且同場同分才可輸出 `RESEARCH_ONLY`；只要任何一方 `ABANDONED/SUSPENDED`，即使比分相同都 `HOLD`，等待官方裁定與獨立規則審核；任何結果仍然 `bookmaker_settlement_eligible=false`。
- 這是**狀態分類風險**，不是聲稱原PR #355已有自動結算而實際錯派彩；原PR只提供合成盤線分類，尚未讀入真實賽果。

## 後續驗收及明確未完成

1. 完整43場雙刊登者比分一致，其中42場一般完場、1場官方裁定4–0；上游資料鏈獨立性未經證實，不能宣稱43場已達模型認證門檻。
2. 原始4條定性研究不可以冒充 A/B/C 模型；賽前盤價門檻是條件，不是當時已成交價格。
3. PR #355 5項CI已通過，但查無獨立review；此PR亦需通過全部CI及獨立覆核才可合併。
4. 下一獨立工單：將官方裁定來源作可機器驗證的簽章／固定來源ID與時間戳證據，並明確分開賽事官方結果、正常90分鐘完成與博彩公司市場結算；未證實就 HOLD。
5. `production_recommendations=DISABLED` 永久保留，不在本次覆盤解除。
