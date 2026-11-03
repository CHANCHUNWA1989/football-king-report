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
5. 原生供應商 ID 只保留喺一次程序記憶 `private_crosswalk`，**公開或 GitHub Actions artifact 永不寫出**源 ID、key、莊家名稱或報價。對照後工作流程只上傳9場去識別化計數、HOLD阻塞原因、來源與成本狀態。

## 離線與真實資料分別

- PR 回歸測試：用 **synthetic** provider event row 同假的 Secret 驗證程式行為，完全不訪問賠率 API。合成正向測試的候選數 **不是**真實供應商數據。
- CI 離線 smoke：`--offline`，毋須 Secret，輸出 `MISSING_GITHUB_SECRET` 或封盤時段標籤；屬行為測試。
- **真實 The Odds API 請求：只有工作流程合併至 main 後，由授權用戶手動 `workflow_dispatch` 啟動**；本 PR 的一般 `pull_request` GitHub Actions 不會請求任何 API。
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
