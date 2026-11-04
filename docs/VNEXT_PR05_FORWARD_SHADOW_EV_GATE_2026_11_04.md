# 足球王者 VNext PR-05 | 同場同時點前瞻 Shadow 對照及報價證據閘門

2026-11-04 · **離線研究模組** · 依賴未合併 Draft PR #433 → #431 → #430 → #429。

## 已檢查基礎

`ops/forward_validation.py` 既有前瞻賽果結算，`ops/research_center.py` 既有 Brier/Log Loss/校準算法，`ops/forecast_decision_journal.py` 既有邏輯修訂鏈，`ops/asian_ev_quote_gate.py` 和 `ops/live_quote_snapshot_guard.py` 既有來源／時間安全檢查。新模組是**獨立 Shadow 配對評估器**，不取代、修改或解除舊安全規則。

## 新增模組

`ops/vnext_shadow_forward_audit.py`

### 嚴格配對

每一個案例須具備：
- `pair.fixture_id`, `kickoff_utc`, `as_of_utc`；
- 精確兩個不同且全 cohort 固定的模型版本 `baseline`、`challenger`；
- 兩者 `forecast_utc == pair.as_of_utc`，原始 `inputs_available_utc <= forecast_utc <= kickoff -10 minutes`，不接受偽稱已校準的預測；
- 精確三類 `probabilities_1x2`，需全正、有限、總和為 1；
- 賽果單獨放 `result`，含相同賽事 ID、90分鐘常規賽得失球、賽後 `result_received_utc`、來源與原始 SHA 標記；
- 必須由整批至少30個不同賽事 ID 構成，單場不同分鐘不能重複計樣本。任一項違例 -> **整批 HOLD**，不靜默 dropna。

輸出：基準／挑戰者三分類 Log Loss、未重標準化 Brier、正規化 RPS、5檔校準表、逐場配對後的均值差與自述 cohort hash。

**成功也只輸出 `EXPLORATORY_ONLY`**：30場是輸出診斷的工程門檻，不是統計效力、外部來源真偽、可信樣本外檢驗或模型放行標準。未提供真正可獨立認證的事前封存、賽果來源、未開封測試集、paired bootstrap、置信區間；因此 `true_prospective_holdout_verified=False` 及 `model_accuracy_gain_verified=False` 永遠固定。

### 盤口／EV閘門

`audit_quote_metadata` 檢查賽事ID、莊家、獨立報價識別、90分鐘結算範圍、3種市場之一、嚴格四分之一盤線、有限十進制水位、提供商更新／擷取／收到／可用時間與決策時間順序（最多5分鐘舊）。

即使欄位完全合法，提供商身份／授權／實際可成交狀態／機率校準未經外部驗證，也會固定 `status=HOLD`、`market_executable_verified=False`、`ev_or_roi_verified=False`、`positive_ev_verified=False`。**本PR完全不輸出EV數字**，亦不接受用截圖、水位或模擬線聲稱真實正EV。

報價來源自述的 `licensed_and_executable_independently_verified` 必須為 false；如果用戶或來源自行改成 true，並不能構成驗證，直接拒絕。未來如要認證，應建立另一個經審計的信任鏈，不應單純改此欄位為 true。

## 測試與驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

`ops/tests/test_vnext_shadow_forward_audit.py` 涵蓋同時點比較、30個不同 fixture ID、Brier/RPS/Log Loss、校準、未來賽果/輸入洩漏、模型版本混合、模型超時、重複 fixture、偽稱校準、非法概率、假認證、過期/未到達盤口及高價格仍無正EV認證。所有數字均為**合成資料**。

GitHub exact-head CI、原始測試日誌及獨立覆核完成前，不可合併。研究用輸出不代表真實當晚七場預測、有效樣本外成績或投注利潤；所有模組均保持 `production_recommendations=DISABLED`。

## 下一步前置條件

需有**外部固定並可驗證**的 pre-match forecast 和結果儲存、未重複的真正 holdout、同期市場基準、至少數百／上千場有效獨立樣本、基於比賽週的成組 bootstrap 與事前驗收標準，以及受許可的實際時間戳報價；原始來源不可在事後修改。只有滿足獨立證據門檻後才可設計 EV 數值輸出及風險閘門。
