# KPL V13：單次快照、封存JSON嚴格解析及錨點驗證效能審計（2026-11-03）

## 目標
本輪係針對 PR #394 V12 封存驗證與收據核對之間可能發生嘅 TOCTOU（time-of-check to time-of-use）競態，以及逐筆反覆讀取整條封存鏈造成不必要重複 I/O。所有程式均係離線研究用途，**唔係真正外部時間見證或官方KPL資料認證**。

## 實際漏洞
V12 原本 `_archive_records` 先呼叫 `verify_archive(path)`，再重新 `open(path)` 讀取每條收據對應檔案。
- 若本地檔案於兩次打開之間被修改或替換，`verify_archive` 同後續使用嘅唔一定係同一份位元組。
- 回測資格流程逐筆呼叫 `inspect_anchor_receipt(path, receipt)`，每個收據可能重新掃描整份封存，對大批封存產生近似 N² 重複讀取/驗證。
- Python `json.loads` 默認接受同一個 JSON 物件中的重複鍵，可能令一些具歧義嘅封存記錄被當成已解析資料。

## 修正
1. 新增 `research/kpl_v13_archive_snapshot.py`：`read_verified_archive_snapshot(path)` 只打開一次本地檔案，最多讀取 32 MB + 1 byte 以拒絕超大資料。從**同一份**原始位元組進行JSON解析、V11逐筆預測時間驗證、整條SHA256鏈重算、重複局數檢查及時間順序檢查。
2. 使用 JSON `object_pairs_hook` 拒絕同一物件重複鍵，亦拒絕NaN / Infinite數值。
3. V12 `_archive_records` 改用V13一次驗證結果，而 `screen_holdout_qualification` 直接用同一份已驗證快照核對全部收據，不再逐筆重新開檔；保留既有 API／HOLD。
4. 快照額外有 `archive_sha256`，僅代表本地讀到嘅原始位元組摘要，**不等於可信外部簽章/官方授權**。

### 測試
`ops/tests/test_kpl_v13_archive_snapshot.py` 12項合成資料測試，包含單次開檔、全收據共享同一快照、重複JSON key、局部修改破壞雜湊、斷尾檔、超大檔案、缺檔及維持HOLD等。完整原有CI亦要通過。

```sh
python -m compileall -q ops research
python -m unittest discover -s ops/tests -p 'test_kpl_v13_archive_snapshot.py' -v
python -m unittest discover -s ops/tests -q
```

## 殘餘限制

- 單次讀取不保證讀取期間檔案所在 filesystem 具備原子快照語義；有權限人士仍可整體重寫、重算整條鏈及偽造自填收據。必須有真正獨立、可驗證簽章嘅外部時間見證／不可變WORM證據，先可以證明賽前存在。
- `received_at`、`issuer_id`、賽果`verified=True` 仍係未經獨立證實嘅輸入；完全唔可以升格為正式可信KPL歷史資料。
- 本輪只有合成測試，冇下載、抓取或入庫真實BP，冇實際模型訓練、預測勝率提升、可靠EV或真實下注指令。
- PR #395（本輪）以 #394 為base；#394/#393/#392/#391/#390 都仍須獨立審查與安全整合，正式投注一直 `HOLD/DISABLED`。
