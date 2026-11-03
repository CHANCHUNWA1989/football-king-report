# 2026-11-03 歐冠9場：The Odds API 零賠率積分賽事目錄接入

> 研究側通道，嚴禁誤認為已取得可成交報價或正式下注建議；全部輸出固定 HOLD / DISABLED。

## 實際供應商文件

[The Odds API V4 官方文件：GET events](https://the-odds-api.com/liveapi/guides/v4/#get-events) 表明：
- 端點 `GET /v4/sports/{sport}/events?apiKey=...` 返回供應商原生 `id`、`sport_key`、`commence_time`、`home_team`、`away_team`，**不包含賠率**。
- 文件指明該端點 **does not count against the usage quota**；不代表無需 API key 或涵蓋所有賽事。
- `soccer_uefa_champs_league` 是供應商 sport key，實際今季是否列入用戶帳戶權限須靠真實回應判斷，不能憑宣傳判定。
- **唔會**觸發 `/odds`、`/scores`、`/markets`、歷史、任何付費端點；唔會改動現有六聯賽 API 額度策略。

## 如何運作

1. `ops/ucl_zero_credit_event_catalogue.py` 首先離線核對 [PR #387](https://github.com/CHANCHUNWA1989/football-king-report/pull/387) 的9場官方賽程，與 [PR #388](https://github.com/CHANCHUNWA1989/football-king-report/pull/388) 的9個 UEFA 官方比賽頁 ID，**未通過就不會連外**。
2. 僅手動啟動受保護 GitHub Actions、而且工作流程在 `main` 時，使用既有 `THE_ODDS_API_KEY` Secret 做最多**一次**請求，UTC 限定11月3日17:45至20:00的歐冠賽事目錄，12秒逾時，600KB上限，不做重試、不追隨轉址。
3. 驗證 HTTPS 完整來源 URL、HTTP200、三個用量標頭與 `x-requests-last=0`。如果 missing key、官方證據失效、來源轉址、非零或缺少用量證據、無資料、超時及來源權限問題，全數安全 HOLD；**不會**猜測原生 ID。即使供應商宣稱零成本，仍以實際標頭確認。
4. 每場只有同 `sport_key`、完整來源 ID、精確 UTC、完全一致英文主客名稱、未開波、無重複 ID 時，才算「**未經第三方獨立認證的供應商原生ID候選**」。無模糊姓名配對、無跨比賽/跨賽事亂合併；供應商名稱與 UEFA 名稱不一致會標示需再核對，唔會自動轉譯。
   - **開波跨時競態修正（2026-11-03）：** 即使發出 API 查詢時未開波，12秒內回應返嚟時可能已開波。程式會喺 HTTP 完成後**再讀一次真實 UTC 時鐘**，以回應完成後時刻重新判定每場 pre-match 候選資格，避免將已開始賽事當成賽前身份證據。兩個回歸測試模擬 API 呼叫跨越 17:45 UTC 及 20:00 UTC 開賽界線，先在舊程式重現候選數錯誤，再驗證改正後候選數為0；即使測試通過仍不代表供應商身份獨立認證。
   - 官方 V4 文件寫明 `commenceTimeFrom` 包含該時間或之後，`commenceTimeTo` 包含該時間或之前；17:45–20:00 UTC 日期條件本身**包含**20:00 UTC 的7場賽事，不需要任意擴大窗口。
5. 原生供應商 ID 只保留喺一次程序記憶 `private_crosswalk`，**公開或 GitHub Actions artifact 永不寫出**源 ID、key、莊家名稱或報價。對照後工作流程只上傳9場去識別化計數、HOLD阻塞原因、來源與成本狀態。

## 離線與真實資料分別

- PR 回歸測試：用 **synthetic** provider event row 同假的 Secret 驗證程式行為，完全不訪問賠率 API。合成正向測試的候選數 **不是**真實供應商數據。
- **審核補強（2026-11-03）：** 測試以注入 `opener` 模擬 HTTP 回應時，就算提供 `x-requests-last=0`，只會顯示 `provider_zero_cost_header_shape_passed=true`，絕不標記 `quota_cost_verified_zero=true` 或 `source_live_http_origin_checked=true`，並標示 `source_provenance=TEST_DOUBLE_INJECTED`。只有未注入測試載入器、真正對供應商發起單次請求並通過來源及用量標頭檢查時，先可聲稱 vendor header 完成驗證；仍不代表可成交盤口。
- 缺少或包含控制字元、空格、非 ASCII 的 Secret，會在任何連網嘗試之前被拒絕，`provider_request_attempted=false`；錯誤報告不顯示憑證。
- CI 離線 smoke：`--offline`，毋須 Secret，輸出 `MISSING_GITHUB_SECRET` 或封盤時段標籤；屬行為測試。
- **真實 The Odds API 請求：只有工作流程合併至 main 後，由授權用戶手動 `workflow_dispatch` 啟動**；本 PR 的一般 `pull_request` GitHub Actions 不會請求任何 API。
- **安全硬化（2026-11-03）：** 直接程式呼叫若同時提供 API Key、`now_utc` 自訂時間而沒有注入離線 HTTP `opener`，會在任何供應商連線之前拒絕並輸出 `LIVE_TIME_OVERRIDE_REJECTED`。理由係真實受憑證保護嘅查詢唔可以靠呼叫者回撥 UTC 時鐘，否則會繞過開波後不得新增賽前賽事ID候選嘅閘門。此防線的負向測試先於修正版本 CI 重現錯誤（舊版確實呼叫了 `_fetch_events`），再修復；正常 CLI 並無提供 `now_utc`，實際 production call 仍只讀系統 UTC。
- 工作流程供應商權限不足、沒有當輪目錄、身份名稱差異，均屬真實待查缺口，不能擅自聲稱已接通9場。

## 如何驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ucl_zero_credit_event_catalogue.py' -v
python -m unittest discover -s ops/tests -q
python ops/ucl_zero_credit_event_catalogue.py --offline \
  --output artifacts/ucl-zero-credit-offline.json
```

新 workflow `.github/workflows/ucl-zero-credit-event-catalogue.yml`：
- PR path-filter：只跑離線測試（冇 Secrets、冇 provider API request）；
- 正式手動運行：`main` 才允許一次憑證受控的 `GET events`，輸出 sanitized 7日 artifact；
- `status=HOLD`、`production_recommendations=DISABLED`、`bets_authorized=0` 是不可解除界線。

## 現時仍未完成

1. 取得真實帳戶的 `soccer_uefa_champs_league` event rows；本 PR **未進行 live authenticated call**。
2. 真實供應商命名可能與 UEFA 官方不同，只有**經獨立核實**的團隊 ID/name alias 才能擴展精確 crosswalk。
3. 真實盤口（同莊家完整兩邊、更新及擷取UTC）、賽前正式正選、角球／半場分布與足夠獨立完場前瞻樣本依然欠缺。呢個 catalogue 不會亦不能證明 EV、命中率或盈利性。
