# KPL V20 — 前瞻性影子觀測：賽前登記、逐局FORECAST/HOLD、全面覆蓋率

日期：2026-11-03。繼承Draft PR #402。**只係離線、用戶執行時才運行嘅研究介面；無自動工作流程、無背景賽程監察、無下注及無真實KPL模型準確度宣稱。**

## 點解要做？
V17–V19係嚴格使用虛構或之後提供嘅歷史結果重播Elo。即使時間排序一致，只要資料係賽後補填，就不能獨立證明實際賽前作出過該局預測。V20新增「本地寫入時間約束＋create-only不可覆寫紀錄」幫未來研究開始儲存真正候選紀錄，但必須清楚說明：**本地時鐘、create-only檔案、自己計SHA256都唔係獨立可信時間戳。** 使用者可控制本地環境、整份資料與授權聲稱；任何真實時間證明仍需第三方簽章證據、GitHub不可任意修改的受保護儲存或獨立時間戳服務。

## 新增功能

程式：`research/kpl_v20_shadow_trial.py`

### 1. register_shadow_trial(root, manifest)
- 一次事前登記完整預定BO7系列賽母體、兩隊穩定ID、模型凍結版本、來源標記、首次開賽日與當地登記時間。
- 僅接受登記時刻與本機當前UTC相差60秒以內，且所有已登記系列賽首局未開始；模型必須於登記之前凍結。
- 每個系列賽最多有7個**可能開打**嘅小局，並唔要求一開始知道最後實際會打幾局；賽後按第四勝結束系列賽。
- 僅寫入新trial目錄及manifest；相同trial ID不得覆蓋。包含本地SHA256摘要，惟無外部時間見證。

### 2. submit_shadow_decision(trial_dir, decision)
- 每局開始前，只能建立**一次** `FORECAST` 或 `HOLD`；操作時鐘與輸入forecast_at差不得超過60秒。因資料欠缺而HOLD時，概率必須null，並明列原因（BP缺、資料過期、未校準等）；不得將HOLD以0.5概率取代。
- 目前只支持PRE_GAME階段；BP鎖定後與開局前嘅細分階段、LIVE數據必須另設研究模型及獨立時鐘。絕不將V20當成即場投注引擎。
- G2以上必須已存在前一局研究決策紀錄，唔可以事後補交單一「命中局」。重複寫入原路徑會被操作系統的排他創建拒絕。
- 逐局紀錄包含manifest SHA256、actual local recorded_at及研究決策內容；所有輸出一直HOLD。

### 3. audit_shadow_trial(trial_dir, outcome_claims)
- 所有原本登記嘅系列賽都要留喺分母；如果其中一場未完賽／欠賽果，`unresolved_registered_series_count`會顯示而唔係刪走。
- 逐局核對系列賽身份、勝方、賽事開始/結束/觀測時間、每場最多7局且第四勝即停止；結果來源 `SOURCE_ASSERTED` 始終係「輸入來源聲稱」，唔係官方真實性認證。
- 已完整結束嘅BO7，每個實際打咗嘅小局包括 **FORECAST、HOLD、缺賽前紀錄** 都計入覆蓋率分母；HOLD不得藏起失準。
- 只對完整系列賽且結果來源有聲稱嘅FORECAST計算「diagnostic_only_not_real_kpl」Brier/Log Loss/方向命中率，並同期顯示所有局數、缺失數、HOLD數、預測覆蓋率。此分數無獨立資料認證，唔可以稱為真實KPL預測準確率。
- 即使分數漂亮，始終 `status=HOLD`, `live_execution_allowed=False`, `production_recommendations=DISABLED`, `real_kpl_accuracy_verified=False`。

## 實際賽程核對和限制

KPL官方微博2026年9月20日賽程公告指年度總決賽淘汰賽於**10月27日至11月8日**進行，**11月14日年度總決賽**；2026年10月11日官方長沙站票務公告指淘汰賽期間每日**18:00（中國時間）**開賽。
- 官方賽程公告：https://sina.cn/news/detail/5345222013223292.html
- 官方長沙賽場公告：https://3g.sina.com.cn/news/detail/5352803217709884.html
- 11月3日官方最終賽事門票資訊：https://3g.sina.com.cn/news/detail/5361138138089409.html

呢啲官方**日曆級**資料不能保證明天具體比賽隊伍、某場BO7嘅逐局開局時間、BP完整性或賽前實際可見概率。直播平台有時會保留舊賽程/時間，需逐場於官方來源再次核實。

**本PR冇登記任何一場真實未來KPL預測，亦未啟動自動追蹤。** 原因：未有經獨立核實嘅實際逐局開始時間、外部時間戳服務及合法使用來源，不能自稱已有完整前瞻性證據。下一輪需安排官方日曆核對、獨立賽事ID、來源使用權、model frozen policy及可獨立持久化簽章／時間憑據，然後方能開始實際比賽觀測。不可將測試fixture資料當作真實比賽。

## 測試與現階段界線

`ops/tests/test_kpl_v20_shadow_trial.py` 完全合成，時間使用被控制嘅模擬本機UTC（證明程式邏輯，並非真實時間）；涵蓋同一trial重複登記、晚於首局開賽、未有上一局就提交G2、HOLD不准帶概率、檔案被篡改、冒認來源、場次遺漏仍計入覆蓋率，以及完整BO7賽果結算等。

```sh
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v20_shadow_trial.py' -v
python -m unittest discover -s ops/tests -q
```

所有前置PR #390–#402及本輪新Draft仍待獨立審核；不要合併正式主分支、部署API、打開賠率發佈或投注功能。KPL實戰命中率／模型校準是否提升：**尚無可獨立驗證證據**。
