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
