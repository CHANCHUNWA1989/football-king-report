# 足球王者 VNext PR-12｜自動封存移離未受保護主分支（HKJC 試點）

2026-11-04｜**Research / Draft / No merge / No bets**

## 63條 GitHub Actions 工作流程初步盤點

已讀取 `main` 分支 `.github/workflows` 目錄內 **63份YAML**，尋找 `contents: write`、`gh api -X PUT`、直接 Git commit/push 等寫入操作。當中至少以下 **15條** 具有倉庫內容寫入路徑（行為未逐個完成獨立安全審核，唔代表每個步驟都已運行或完成實際寫入）：

1. `football-king-hkjc-free-research.yml` → `sources/hkjc_tipsme_free_latest.json`。
2. `football-king-iphone.yml` → `evidence/settled.json` 及其他內容寫入權限步驟。
3. `four-model-shadow-daily.yml` → 研究封存寫入步驟。
4. `football-king-asia-apis.yml` → 免費亞太來源摘要。
5. `football-king-bsd-free.yml` → BSD 免費來源摘要。
6. `football-king-german-live.yml` → 德國聯賽免費來源摘要。
7. `football-king-japan-free-market.yml` → `market/japan_free_status.json`。
8. `football-king-odds.yml` → `market/` 歷史及最新摘要。
9. `football-king-research-extensions.yml` → 研究摘要。
10. `football-king-secondary-sources.yml` → 後備來源摘要。
11. `football-king-six-free-upgrade.yml` → 六免費來源歷史及最新摘要。
12. `football-king-weather.yml` → 天氣資料狀態。
13. `football-king-weekly.yml` → 每週研究狀態。
14. `football-king-wide-free.yml` → 廣域來源摘要。
15. `private-all-market-research.yml` → 私有市場研究狀態。

`purge-unsafe-market-artifacts.yml` 另外有 Actions artifact `DELETE`，但未見 Git Contents PUT，屬另一種風險，唔計入上述15條。呢個係**靜態現況盤點**，不是授權資料合規保證；其餘14條寫入流程均未更改，應另立遷移工單逐條審查。

## 問題及前置阻塞

- 現有 `main.protected=false`，rulesets清單為 `[]`；API讀取詳細 branch protection 仍然 **403**。GitHub帳戶或工具有管理員身分，不等於現有連接可修改或讀取所有 security settings。追蹤：[Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)，已指派 `CHANCHUNWA1989`。
- HKJC流程 `archive` 工作原本 `contents: write`，使用 `gh api -X PUT repos/.../contents/sources/hkjc_tipsme_free_latest.json`、**冇指定branch**，GitHub Contents API依預設主分支寫入。已核實舊主分支提交 `1b1e21415327f46e081c48f8c59c6863b5947e98` 僅更新相關研究狀態。
- 真正強制主分支經 PR+獨立審核後，這種直寫可能失敗。**不能以開放安全繞過權限去恢復資料封存**。

## HKJC試點架構（今次 PR）

本次獨立研究 PR **base=main**，不疊加未合併的模型PR，亦不改其他排程。

- `ops/hkjc_isolated_archive.py`：不做任何供應商抓取，不改模型；嚴格使用既有 `hkjc_free_research.validate()` 加上**完整 metadata 欄位白名單**、固定官方開發者文件來源、固定理由碼／捕獲時間限制／資料大小上限；拒絕任何額外原始水位、API token、授權自述或交易旗標。
- 先確認固定 `research/hkjc-free-metadata-archive` **獨立分支**真實存在（今次用工具從 `main` 建立；暫未有新檔案）；唔會自動建立、替換主分支或偷換對象。所有 GitHub Contents `PUT` 都指定 `branch: research/hkjc-free-metadata-archive`；GitHub API 404/403、錯誤ref、重複來源、寫入衝突全部 fail closed。
- 用捕獲UTC及 `run_id`、`attempt` 建獨立 `sources/hkjc_free_metadata_archive/history/YYYY/MM/DD/...json` **按執行新增**，嚴格拒絕改寫同一run身份嘅不同內容；`latest.json` 只用 Contents CAS blob SHA 比對後更新；時間倒流唔覆蓋新報告。任何CAS重試失敗或API 403，job失敗而唔會暗中寫main。
- `.github/workflows/football-king-hkjc-free-research.yml`：保留原本 `collect`、免費來源上限、`TIPSME_API_KEY` 僅讀取同7天 Actions Artifact；只將原本 `archive` 工作改為**倉庫main+main ref手動/排程以外禁止**嘅定向研究分支封存，使用 `persist-credentials:false`，無直接main寫入。
- `ops/tests/test_hkjc_isolated_archive.py`：完全使用 synthetic `collect(key="")`、fake GitHub store 和 mocked HTTP，測試密鑰洩漏、額外賠率、版本衝突、重跑、舊時間、不合法ref、API拒絕、用新資料覆蓋及 static workflow 合同。

**遷移限制與運作後果：** 由於唔再寫 `sources/hkjc_tipsme_free_latest.json` 到 `main`，**繼續只讀main舊路徑嘅dashboard/腳本會睇到舊數據**。如有依賴，需另行審查以安全讀取隔離分支或自動artifact，而唔可以聲稱已完成全系統零停機遷移。現有main歷史快照不修改或刪除；研究分支檔案亦唔係第三方時間見證。

## 安全、授權及未完成

- 只儲存已作基本遮蔽嘅**研究metadata**，不複製 bookmaker原始水位、帳戶資訊、任何私有 API Key；不增加資料來源請求、配額或新的額外爬蟲。
- 研究摘要 `RESEARCH_ONLY` 只係資料收集狀態，**不代表模型可交易或可正EV**；仍保留 `positive_ev_verified=false`, `can_execute_bet=false`, `production_recommendations=DISABLED`。
- GitHub研究分支可保存每次的 metadata git變更但**不是 WORM／Sigstore／Rekor 認證**；實際授權及上游獨立性未知。
- 其餘14條直接寫入流程尚未改造；主分支保護、GitHub Admin-read、review批准、整個VNext主鏈合併仍然未完成。
- PR-12 需做 exact-head `python -m compileall -q ops` + `python -m unittest discover -s ops/tests -q`，五條CI及新增測試原始日志核實；**獨立安全審查前保持 Draft、不合併、不觸發額外供應商抓取。**

## 之後的必要工作

先核實所有消費 `sources/hkjc_tipsme_free_latest.json` 嘅控制台/腳本，加入獨立分支讀取兼權限檢查與時間到期 `HOLD`；再批量處理其餘14條各自嘅歷史留存及資料授權。由管理員建立 main 保護與正常PR審核，亦須確認archive branch及GitHub Token寫入權限符合倉庫規則；欠權限時停封存並報警，絕不回退main直寫。
