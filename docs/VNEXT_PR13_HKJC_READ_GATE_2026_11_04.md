# 足球王者 VNext PR-13｜HKJC 隔離封存唯讀消費者與時間保護

2026-11-04 · **研究用途／Draft／HOLD／未上線**

## 前置核對

- [PR #442](https://github.com/CHANCHUNWA1989/football-king-report/pull/442) 已完成工程CI但仍係未合併Draft；新封存路徑只會由**將來受審核合併後**嘅排程更新。
- 經GitHub repository tree核對，`main` 有8,612個Git tree entries；已實際讀取舊使用說明 `HKJC_FREE_FOOTBALL_API_2026_10_10.md`，該文件明確指導用戶讀 `sources/hkjc_tipsme_free_latest.json`，係一個**已確認嘅舊路徑人手消費者**。
- 亦檢查 `ops/mobile_dashboard.py`、`ops/build_zh_hant_dashboard.py`、`ops/research_mobile_status.py`、`ops/report_zh_hant.py`、`ops/shadow_mobile_report.py`、`ops/integrated_research_report.py`、`ops/hkjc_snapshot_audit.py` 等候選報告檔，**喺檢查範圍內未找到直接讀舊HKJC JSON路徑嘅程式消費者**。呢個唔等於全倉儲所有間接依賴已形式化證明不存在。
- 最後核對到 `main` 嘅舊檔顯示 `status=NOT_CONFIGURED`；呢個係特定封存檔嘅狀態，**唔代表所有時間與環境都冇設定供應商 key**。
- 部署前還要以實際讀取路徑審核網站／iPhone／其他外部介面；任何未檢視消費者唔可以假設冇風險。

## 新增 `ops/hkjc_isolated_reader.py`

- **唯一允許的遠端請求**：`GET https://api.github.com/repos/CHANCHUNWA1989/football-king-report/contents/sources/hkjc_free_metadata_archive/latest.json?ref=research%2Fhkjc-free-metadata-archive`。無任何備援讀 `main` 或私人盤口API，也不需要新增供應商API Key。
- 無資料／GitHub 404、403、網絡錯誤、HTTP過大、格式異常一律 `status=HOLD`；保留 `DISABLED`。
- GitHub Contents JSON 必須逐欄比對 `type=file`、精確 path/name、base64 encoding、大小、40位Git Blob SHA1；從回傳 bytes 重算 **Git Blob SHA1**，拒絕名稱／雜湊／內容錯配。**Git Blob SHA1只係GitHub回應一致性檢查，唔係Sigstore/Rekor或可信第三方時間見證。**
- 使用 PR-12 原本 `hkjc_free_research.validate` 及嚴格metadata白名單；拒絕任何原始賠率、私鑰、投資投注旗標、非規範JSON和重複欄位。
- 每日香港13:18定時採集，元數據以**30小時**為到期上界（不是市場有效報價TTL）：檢查時距封存捕獲超過30小時、未來超過5分鐘便即 `HOLD` 且 `metadata_recent=false`。
- 即使檔案近期成功、紀錄自述 `RESEARCH_ONLY`，輸出整體仍**永遠 `status=HOLD`**、`source_independent=false`、`licensed_quote_redistribution=false`、`real_market_quote_verified=false`、`positive_ev_verified=false`、`production_recommendations=DISABLED`。曝光嘅入球、角球等只係「**封存當刻**各市場符合基本檢查的賽事**數量**」，唔係現時可成交盤口。
- CLI `python ops/hkjc_isolated_reader.py --no-auth` 只讀公開研究metadata並輸出JSON；**必定非零退出碼**，唔可當做解除建議或落注嘅workflow gate。
- `ops/tests/test_hkjc_isolated_reader.py` 只用mock GitHub、無新網絡來源或免費額度消耗，模擬404、403、過期、未來、來源欺騙、內容竄改、NaN、raw quote、權限及雜湊不符。

## 人手消費者交接

已更新 `HKJC_FREE_FOOTBALL_API_2026_10_10.md`：標示舊 `main/sources/hkjc_tipsme_free_latest.json` 為**遷移後會停更嘅歷史路徑**；先由 GitHub Actions 7日Artifact睇真實執行結果，將來 PR #442+本PR經安全審核合併後，才使用隔離分支讀取器。預設讀取器 `HOLD` 唔等於寫入失敗，係防錯誤放行設計。

### 未完成（真實運作）

1. 新隔離分支 `research/hkjc-free-metadata-archive` 已預備，但喺 PR #442 合併前無**新排程第一次成功寫入**。本PR只驗證模擬讀取能力，**未核實真正遠端 `latest.json` 成功存在或更新**。
2. PR #442 與本PR都要實際獨立review、檢查讀取憑證最低權限同分支設定；唔可自行跳過或自動合併。
3. 其餘 **14** 條repo內容寫入 workflow 尚未遷移；GitHub `main.protected=false`、保護API 403與Issue #439仍係獨立阻塞。
4. 即使真正資料經隔離GitHub branch存檔，仍**未證明來源授權、供應商獨立、實際可信時間、樣本外提升、可成交報價或正EV**。不可恢復投注。

## 驗收

`python -m compileall -q ops`；`python -m unittest discover -s ops/tests -q`；只可將 exact-head GitHub CI 與原始日誌驗證結果作為工程驗收。未合併前不觸發原本正式排程以測試資料，不變更 `main`。

**HOLD／DISABLED維持原狀。**
