# 第十一階段｜GitHub Run 身份及實際時序交叉核對（Issue #401）

## 起點／實際驗收阻礙

2026-11-03 審計發現：
- #403（即場角球事件）、#406（來源ID）、#408（Sigstore witness）、#411（證據串連）仍為 Draft、未合併 main；
- `.github/workflows/football-king-live-fixture-seal.yml` 及 `research/live_fixture_manifests/` 尚未存在於 main；
- #411 尚無獨立 reviewer approval；沒有任何可信真人／自動獨立審核可假裝已完成；
- 因此**未能合法取得及驗證任何 #408 專用正式 workflow 簽署嘅賽前 fixture manifest**，更無獲授權、同分鐘可成交角球盤快照；
- 新增合成/Mock 測試都不可計入前瞻預測樣本，命中率及 ROI 沒有改善證據。

## 今次解決一個可核實缺口

#411 過往只從使用者提供嘅 `--run-id / --attempt / --source-sha / --workflow-sha` 作為 Sigstore 驗證釘選值。Sigstore certificate & transparency log 仍是必要，但缺少另一次**當場從 GitHub REST 抓取真正 Actions Run metadata**作對照。

新增 `ops/live_fixture_github_run_guard.py`，透過固定
`gh api --hostname github.com --method GET /repos/CHANCHUNWA1989/football-king-report/actions/runs/<run-id>`
進行新查詢，並核對以下條件：

- repository 及 head_repository 均是固定 full_name 與 repository numeric ID；
- run ID、run attempt、head SHA、`main` 分支、固定 `football-king-live-fixture-seal.yml` 路徑及 **`workflow_dispatch`** 事件完全相符；
- GitHub Run 必須 **completed / success**；
- GitHub 伺服器提供之 `created_at`、`run_started_at` 時序有效，且最少早於**資料中記錄**的 kickoff 10分鐘；
- CLI 失敗、網絡／GitHub 驗證權限不足、時間異常、分支／SHA／工作流不符，統一 HOLD，不保存或向外顯示 API 回應、GH token、私人 bookmaker 名稱/賠率。

#411 `ops/attested_live_corner_bridge.py` 改為：先驗證真正 Sigstore witness + manifest bytes，再用當次 GitHub Actions Run metadata 核對，最後才做 #403/#406 live-score/corner/quote 時序檢查。只有三步全通過可以顯示 `RESEARCH_ONLY`，但 `source_authenticity_verified`、`actual_kickoff_authenticated`、`market_executable_verified`、`certified_positive_ev` **均不可因而設為真**。任何新輸入缺資料時必須 HOLD。

## 測試與限制

- 新增 `ops/tests/test_live_fixture_github_run_guard.py` 嘅合成 GH REST 測試，涵蓋錯庫、錯提交、錯工作流、錯分支、失敗 Run、時間倒灌、假回應、重複 JSON key、CLI 不可用、惡意 run-id。
- 擴充原有 `test_attested_live_corner_bridge.py`，保證 Run metadata 不一致時 **不准進入 live 資料驗證**。
- 呢啲測試 mock 掉 `gh api` 或 Sigstore CLI，**唔係真實 GitHub/Sigstore 成功見證**。
- GitHub REST metadata 來自官方受信 API，但仍然只係平台 Run 開始時刻、身份與執行結果，**唔係第三方認證真實賽事開球時間或供應商內容**。而且不代表任一賠率真係當時可下注。
- 新增外部 GH API 只會於研究端有人調用該 CLI 時執行，唔設排程，唔調用任何賠率供應商 API，唔增加免費賠率配額使用。
- 未經獨立第三方覆核前四個 Draft PR，唔會合併主分支；正式 `production_recommendations = DISABLED`、HOLD 不變。

## 真正端到端驗收必要條件

1. 先完成 #403 → #406 → #408 → #411 → 本PR 嘅獨立程式審查與 CI，按依賴順序合併（不得帶失敗通過）。
2. 只可使用有合法來源、沒有秘密或商業原始報價的**真實賽前 fixture source map**，由 main 的手動 seal workflow 產生簽章；先進行 GH metadata + Sigstore Tlog 的真實驗證。
3. 確保來源合法性、真實 source-native fixture ID／實際 kickoff 和 quote 時間及實際 feed 內容獨立核對；再用合格 snapshot 進入研究，不可硬填缺失時間。
4. 事前封存預測、賽後獨立核實結果，累積足夠新樣本後才檢查樣本外預測優勢；仍不能自動解鎖正式投注。

### 離線測試

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_live_fixture_github_run_guard.py' -v
python -m unittest discover -s ops/tests -p 'test_attested_live_corner_bridge.py' -v
python -m unittest discover -s ops/tests -q
```
