# KPL 第十二階段｜外部錨點介面及樣本外回測資格（2026-11-03）

狀態：**研究模式、HOLD、無官方KPL或授權回測數據**。此 PR 以 V11 PR #393 為基礎，前置依賴 PR #392、#391、#390。

## 具體風險（V11基礎審計）

V11 JSONL 以 SHA256 previous_hash → entry_hash 鏈式連結，可偵測本地局部修改。但有人能重寫整份 JSONL 後重算整條鏈，V11 依然可通過自洽校驗；而 forecast_at 只係寫進檔案的一個欄位，唔係外部可信時間。V11 的 outcome verified=True 亦係外部聲稱，唔代表來源身份、授權或真正賽果已獨立證明。

## 本次新增程式

- `research/kpl_v12_anchor_qualification.py`
- `ops/tests/test_kpl_v12_anchor_qualification.py`

### 1. 準備獨立錨點請求

`build_anchor_request(path, record_index, requested_at, anchor_target)`：

- 先用 V11 `verify_archive` 驗證整條本地雜湊鏈，再選取指定記錄索引嘅 prefix entry_hash 作 head_hash。
- 檢查 request_at 不早於預測時間，並嚴格早於該局 game_start_at。
- 輸出 index、head_hash、prediction_id、預定錨點服務種類和 requested_at；**不做任何網絡請求、不存入外部伺服器、不產生簽章**。
- `submitted_to_external_provider=False`、`external_witness_authenticated=False`，狀態 `PENDING_EXTERNAL_WITNESS`。

可用目標種類只係介面名稱 `INDEPENDENT_TIMESTAMP_SERVICE` 或 `EXTERNAL_IMMUTABLE_STORE`。未有現實世界供應者、權限或保證。

### 2. 檢查外部收據資料格式

`inspect_anchor_receipt(path, receipt)`：

- 只接受預期欄位，拒絕 self-claimed `verified=True` 等額外字段。
- 必須匹配 archive record_index、prediction_id、head_hash；假錨點/跨局replay會被拒絕。
- 收據中聲稱的 witnessed/received_at 必須處於預測後、比賽開始前。
- **不驗證Issuer的密鑰或數碼簽章，亦無信任根**。收據時間與 issuer_id 即使結構正確，都唔代表真實獨立時間見證。輸出始終 `status=HOLD`、`external_witness_authenticated=False`。

只有配合真正獨立的 RFC3161 TSA/具公開金鑰簽章之WORM證據核對，並將信任根及核實結果與輸入解耦，將來才可能建立真實外部可信錨點。本輪 **未實作、未申請、未配置任何此類服務**，唔可以稱「已完成外部時間認證」。

### 3. 回測資格閘門

`screen_holdout_qualification(path, results, receipts, min_test=30, train_fraction=0.7)`：

- 封存鏈完整、時間順序及每局唯一性遵循 V11；
- 每局都須有完整、不重複、時間在開局前的錨點*收據結構*；
- 經V11 `chronological_holdout` 驗證整個BO系列賽不可跨 train/test、訓練賽果須於測試預測前已知、賽果身份/時鐘及最少測試樣本要求；
- 只回傳 `technical_preflight_passed` 和 train/test 樣本數，**唔將合成資料的 Brier/Log Loss 推算成真實成果**；
- 不論是否通過形式審查，`status=HOLD`、`production_recommendations=DISABLED`、`live_execution_allowed=False`，另以理由標示外部錨點、賽果來源、資料授權及模型校準未獲核實。

### 4. 測試與限制

23項合成測試，覆蓋成功生成請求與結構匹配（仍HOLD）、缺失檔案與索引、錨點超時、偽造的issuer及驗證字段、錯誤head_hash/重播、不可雜湊的惡意錨點類型、整條鏈重算後與原收據不一致、缺少或重複收據、結果未驗證、過期才取得訓練結果、樣本不足等。

```sh
python -m compileall -q ops research
python -m unittest discover -s ops/tests -p 'test_kpl_v12_anchor_qualification.py' -v
python -m unittest discover -s ops/tests -q
```

### 未完成／外部依賴

1. 無法憑自填 `received_at`／SHA256證明真正的實際先後時間。需要**獨立授權可信時間服務**及可驗證的簽章鏈。
2. 無 KPL 官方／授權完整逐局BP與賽果資料；本輪只合成測試。自填結果 verified=True 唔係獨立認證。
3. 無真實回測、無樣本外預測表現、無已驗證盈利能力。
4. PR #394 保留 Draft，全部必要 CI 與獨立覆核完成前不合併；正式模型、API、排程、網站及投注限制完全不變。
