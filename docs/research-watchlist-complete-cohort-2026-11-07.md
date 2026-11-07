# 足球王者｜完整賽前研究名單賽後覆盤（2026-11-07）

## 為何修復

2026-11-06 晚上至 2026-11-07 凌晨的研究名單：艾夫斯堡 +1.25 與愛華頓細2.5球兩個最後優先觀察方向落敗；其他早期研究、最後排除的盤口則有部分成功。如果只報有中結果，會形成嚴重選擇偏差。早前公開模型和各網站所見報價未達可成交／獨立 OOS 驗證；這次覆盤不得倒推或事後封存成「真實賽前證據」。

## 這個修補真正做到

新增 `ops/research_watchlist_review.py`，**離線、零 API credit、研究用途**。以事先準備的完整 watchlist 和獨立 results 檔案為輸入：
- 所有 `PRIORITY_RESEARCH`（優先方向）、`WATCH`（觀察）、`EXCLUDED`（排除）、`HOLD`（數據不足）決定都要逐項出現在報告；即使結果對照成功亦不能將 EXCLUDED 計作主要建議命中。
- 賽事採固定 `fixture_id`；每個 `fixture_id + market + selection + quarter_line` 只能出現一次。每項有獨立 `selection_id`，不能利用不同 bookmaker price 事後複製同一候選。
- 要求事先提供 `registered_at_utc < kickoff_at_utc`；有價格時，`quote_updated_at_utc <= captured_at_utc <= registered_at_utc` 且不超過 20 分鐘年齡；缺價格只能 HOLD。
- 支援 1X2、亞洲讓球（選擇方的有符號讓球）、全場大細球。沿用現有 `asian_ev_research.asian_net` 的全贏、贏半、走盤、輸半、全輸結算。
- 賽果必須對應同一 `fixture_id` 和 kickoff；過早宣稱完場、未來結算、無效比分或重複／矛盾賽果會標示未能結算，不會「揀一個有利比分」。
- 報告依原先決定分桶展示全部候選數、已觀察賽果數、待核實數、分級結算及假設每個盤口1單位的單位淨回報；**呢個只係描述性假設回報，唔係實際收益或賽前可成交 EV**。
- 完整 watchlist 算本地 SHA256；隨後結果更新不改名單指紋。指紋可對照版本，**不可獨立證明**名單係賽前建立；要在開賽前利用外部不可改寫時間證據封存。
- 即使輸入自稱來源已核實，結果都明確標示 `results_independently_verified=false`、`prematch_manifest_independently_attested=false`、`production_recommendations=DISABLED`。

## 2026-11-07 單項維護：隔離賽前清單與賽果

- 重現缺陷：watchlist 行夾帶已填入的比分／結果，仍可通過 `seal_manifest` 及 `review`，污染「賽前」清單的內容邊界。
- 在既有 `_watchlist` 共用入口拒收頂層 `home_goals`、`away_goals`、`score_ft`、`outcome`、`result`、`historical_outcome`、`finished_at_utc` 欄位；存在即拒收，包括 `0` 或 `null`。一般 `research_note` 仍可保留，賽果只由獨立 results 輸入提供。
- 先重現16個負例失敗，再以4行驗證修復。22項 watchlist 測試及見證／簽署主體共38項相關測試成功；完整 ops 2,395項與根目錄157項測試成功，無跳過；compileall／diff check成功。精確提交的 CI 以 PR #457 Checks 為準，不預先宣稱通過。
- 這是已知結構化欄位的輸入隔離；本地 pin 及呼叫者時間仍不是外部賽前認證，亦不驗證文字備註的事實。未改原始名單、歷史賽果、模型或正式旗標，沒有接駁資料供應商、合併或部署。

## 離線使用方式

先在賽前準備完整 `watchlist.json`，賽後另外準備 `results.json`（兩者不要上傳到公開儲存庫，尤其是具授權限制的原始博彩公司資料）。語法示例：

```bash
python -m ops.research_watchlist_review \
  --watchlist /private/watchlist.json \
  --results /private/results.json \
  --checked-at-utc 2026-11-07T10:00:00Z \
  --output /private/watchlist-review.json
```

輸入 contract 由 `ops/tests/test_research_watchlist_review.py` 提供明確 synthetic fixtures。以上命令係用法示例，不代表已執行真實賽事回填。

## 驗收與安全

```bash
python -m compileall -q ops
python -m unittest ops.tests.test_research_watchlist_review -v
python -m unittest discover -s ops/tests -q
```

已補 11 類正反測試：主要方向落敗、排除方向勝出、缺賠率 HOLD、AH 和大小球四分一盤、未完賽不消失、重複賽果全數隔離、事後改決策與註冊時間、價差／重複選擇、時序和價格不合法、來源自稱認證無效、固定名單 SHA。

## 未完成／不可誇大

1. 本模組尚未接駁真實授權的亞洲讓球、大細球原始賠率收集和獨立結果；對 11 月 6 日個案**不得事後製造**已封存的真實賽前名單。
2. 本地時鐘欄位、SHA256、第三方聲稱，不能取代外部 time anchoring 與來源權利、資料不可竄改證明。
3. 個案未獨立認證且無可靠 OOS 校準：正式推薦及自動下注繼續 HOLD／DISABLED。此修正**未證實提高命中率或盈利**。
4. Issue #439 main branch protection、獨立人手審核、已有 Draft #451/#453/#454/#455/#456 需另外處理；本 PR 不繞過審核部署。

這項改進的可驗收成果是：**未來不能喺事後覆盤工具內只計中獎候選或將排除項目改稱正式推薦**，並保留完整分母與時間缺口。

## 2026-11-07 P0 增量修正：本地賽前指紋核對

以往報告只有即時計算的 `manifest_local_sha256`；如果賽後更改首選／撤回／賠率後重算指紋，沒有已保存的對照值，覆盤無法發現。現增加 `seal_manifest`／`manifest_pin` 核對。

### 賽前（只能在全部比賽開波前；正式 CLI 使用執行當下 UTC）

```bash
python -m ops.research_watchlist_review \
  --seal-only \
  --watchlist /private/watchlist.json \
  --output /private/previously-pinned-watchlist.json
```

此收據只記錄完整名單 SHA256、項目數目及建立時刻，**不會公開原始報價、模型或 API Key**。賽前必須把獨立保存的收據送到可信的不可改寫來源（例如經審核的外部時間認證服務）；單一 JSON 檔案同其本地時間都可以事後更改，**本修正未提供外部認證服務或證明已完成外部封存**。CLI 不接受 `--issued-at-utc` 人手回填舊時刻，程式函數可用於合成測試。

### 賽後（只接受先前保存的同一份收據）

```bash
python -m ops.research_watchlist_review \
  --watchlist /private/watchlist.json \
  --results /private/results.json \
  --manifest-pin /private/previously-pinned-watchlist.json \
  --checked-at-utc 2026-11-07T10:00:00Z \
  --output /private/watchlist-review.json
```

- `manifest_pin_matches_content` 只表示本次輸入與另存的本地 pin 對得上；**不代表來源可靠、賽前獨立證明、正 EV、已可落注或預測率提升**。
- 更改任何賽前決定、場次、模型、盤口線、賠率，或刪除輸咗／被排除項目，會令 SHA 不符，直接 fail closed；不會輸出「新的」覆盤成績。
- 收據只准固定 schema、`LOCAL_UNATTESTED`、`external_attestation_verified=false` 及 `production_recommendations=DISABLED`；禁止輸入冒稱已認證標記。收據時刻須在全部名單註冊之後且早於第一場開賽。
- 不提供 pin 時可繼續產生舊有 `RESEARCH_ONLY` 研究報告，但 `manifest_pin_matches_content=false`；不可誤稱已有封存。
- 新增 9 項正反驗證，連同原有 11 項，總共 20 組研究審計測試。系統授權盤口與獨立來源賽果缺口不變，`main` 分支安全審核 #439 未解除，不得合併／部署作正式推薦。


## 2026-11-07 增量研究修正：GitHub Sigstore 簽署摘要與透明日誌時間

### 本次已開發、但未部署或執行真實簽署的部分

- ops/watchlist_attestation_subject.py：只產生一行 64 位 SHA256 摘要。輸入非摘要、垃圾字元、紀錄的最早開球時間距目前少於或等於 10 分鐘一律拒絕。
- .github/workflows/research-watchlist-attestation.yml：只允許 main 分支手動 workflow_dispatch；未合併至 main，因此目前無法執行。使用 GitHub OIDC / actions/attest@固定 commit SHA 生成 SLSA build provenance；只上傳摘要 TXT 及 Sigstore bundle（保存7日），絕不上傳原始完整賽前名單或博彩公司受限價格。
- ops/watchlist_witness.py：逐次重新驗證私有 watchlist、LOCAL_UNATTESTED pin、單行 SHA256 主體，以及 gh attestation verify 的真實 CLI 驗證結果。簽署身分必須匹配指定 repo、main、signer workflow、來源 commit SHA、工作流 SHA、run ID、GitHub 托管 runner；可信時間必須來自已驗證的 Rekor Tlog，唔可使用使用者自己寫入或儲存的 verified JSON 標記。
- 若未有真 bundle、模型名單改動、簽署者錯、SHA 不一致、Tlog 時間早於本地 pin 或晚於紀錄開波前10分鐘，都會 HOLD。即使簽署成功也只是「摘要承諾早於所記錄開球時刻」，不能把實際 kickoff、來源權利、盤口成交、獨立賽果、模型 OOS、盈利當作已驗證。
- ops/tests/test_watchlist_witness.py 新增11項模擬反例，ops/tests/test_watchlist_attestation_subject.py 新增5項。所有簽署成功輸出都只是 MOCK 測試，不是真實已執行的 GitHub 簽署。

### 未來正式開通步驟

1. 真正開賽前，保存完整私人 watchlist 與本地 pin（不可事後偽造過去收據）。
2. 必須先完成 GitHub main 分支保護及獨立人手審核 Issue #439，才考慮合併這個新簽署 workflow。未部署時不能使用 GitHub Actions 手動選單啟動。
3. 開通後由擁有人以 workflow_dispatch 提交 digest-only manifest_sha256 與記錄中的最早 kickoff UTC，工作流程須在開賽超過10分鐘前實際完成 GitHub 簽署。
4. 從同一 Actions run 下載 watchlist-manifest-sha256.txt 及 watchlist.sigstore.json，賽後用下列驗證器及可信 GitHub run 元數據重新獨立確認。不得公開私人完整名單及原始報價。

命令用法示例（尚無可用真實簽署檔）：

    python -m ops.watchlist_witness --watchlist /private/watchlist.json --pin /private/previously-pinned-watchlist.json --proof-dir /private/signed-proof --source-sha FULL_40_HEX_SOURCE_SHA --workflow-sha FULL_40_HEX_SIGNER_SHA --run-id GITHUB_RUN_ID --attempt 1 --output /private/rechecked-witness-report.json

測試指令：

    python -m unittest ops.tests.test_watchlist_witness -v
    python -m unittest ops.tests.test_watchlist_attestation_subject -v
    python -m unittest discover -s ops/tests -q
    python -m compileall -q ops

GitHub CLI 官方說明：https://cli.github.com/manual/gh_attestation_verify

### 不可突破的界線

今次提交**沒有完成任何真實 Sigstore 見證，沒有來源授權的新數據，也沒有獨立核實真實開賽時間**。新工具維持 RESEARCH_ONLY / HOLD，production_recommendations=DISABLED；不可將 CI 成功宣稱為模型命中率、盈利、正式推薦的認證。


## 2026-11-07 安全阻擋修正：未保護 main 不准執行 GitHub 簽署

最新 GitHub API 核對：main 的 protected=false；rulesets=[]；Issue #439 仍未完成，並且既有 Draft #438 有相同類型的保護檢查但尚未合併。這意味着只限制 main 手動執行不足夠：現有未保護 main 仍可觸發工作流程。

本輪將 Draft #438 中已寫好的 fail-closed preflight 邏輯移植到 watchlist 簽署 PR #457（獨立模組 ops/watchlist_governance_preflight.py，待上游合併後再整合以減少重複），並新增 ops/tests/test_watchlist_governance_preflight.py 13項合成測試。新 workflow 的順序如下：

1. 必須是固定 repository、repository ID、main branch、手動 workflow_dispatch、有效原始 commit SHA 及 run ID。
2. 從 GitHub API **實時**核實 main 當下 HEAD 與執行 commit 一致、main protected=true，以及保護規則確實有獨立 PR 審核、最少1人批准、撤回過時批准、最後修改後需要再批、禁止管理員繞過、strict 且指定 GitHub Actions App 的必要安全 CI、禁止 force push 和分支刪除。
3. GitHub API 無權限、503、未能核實或任何一項條件缺失，就在產生指紋和 actions/attest **之前**返回非零 exit code，完全停止簽署。
4. 只有管治 preflight 過關，先執行 digest-only 及 Tlog 步驟；即使證據成功仍保持 HOLD / production_recommendations=DISABLED。

目前本 ChatGPT 連接**不能**代碼庫管理員更改 main 分支保護或提供獨立人手審核。GitHub Actions token 可能沒有保護規則 API 的讀取權；403 必須繼續 HOLD，不能用管理員 PAT、跳過檢查或自稱成功。這是有意設計的安全阻擋。

整體工程只在 Draft PR 內測試，沒有合併、沒有操作真正簽署流程，亦沒有任何真實足球市場正 EV 認證。


## 2026-11-07 P0 檔案不可覆寫修正

覆盤再發現一個具體安全漏洞：原本的 `ops.research_watchlist_review.main` 使用 `Path(...).write_text` 輸出本地封存 pin 或賽後 report，可以無提示地直接覆寫既有原始 watchlist、results、舊 pin 或此前報告；簽署驗證 CLI 的報告輸出也可直接覆寫同名檔。這會令證據鏈和原研究決定更容易意外消失，或被事後更改。

修正：
- `ops/research_safe_output.py` 採 `os.O_CREAT | os.O_EXCL | os.O_WRONLY`（支援的系統另加 `O_NOFOLLOW`）以 **僅建立新檔案**，存在相同路徑一律拒絕；不是先檢查存在與否再覆寫，減少 race condition。
- 輸出設為擁有人讀寫 `0600`，JSON 有 `allow_nan=False`，寫入成功後 `fsync`。不更改傳入完整賽前名單、比分及既存簽署證據。
- `ops/research_watchlist_review.py` 的 `--seal-only` 和正常 `--results` 報告統一用上述安全輸出；封存命令只可寫新 pin，想另外封存必須指定另一新檔名。
- `ops/watchlist_witness.py` 真正簽署驗證後的研究報告同樣只准輸出新路徑，絕不覆寫既有報告、manifest 或 source；本來禁止寫到簽署證據資料夾的規則亦保留。
- `ops/tests/test_watchlist_output_integrity.py` 新增7類正反測試：正常新 pin、現存 pin/原始 watchlist、符號連結／硬連結、正常新覆盤、結果檔覆寫、簽署報告輸入檔覆寫及現存驗證報告。

驗證指令：

    python -m unittest ops.tests.test_watchlist_output_integrity -v
    python -m unittest discover -s ops/tests -q
    python -m compileall -q ops

此功能只保證當次寫入時不會不小心覆寫原有檔案。儲存位置管理員可另行刪除／修改檔案；它**不等同**外部不可篡改時間戳、不可改寫儲存、已授權盤口或獨立賽果認證。正式推薦仍維持 HOLD／DISABLED，PR #457 仍未合併。
