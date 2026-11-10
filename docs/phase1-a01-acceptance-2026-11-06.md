# A01 驗收：拒絕歧義讓球報價身份

日期：2026-11-06 UTC。研究用途，**HOLD／DISABLED**。

## 問題與修復

原版 `extract_historical_quotes` 以 outcome name 是否在 `(event.get('home_team'), event.get('away_team'))` 決定讓球方向。若三項皆缺失，`None` 比對成功，錯誤產生 `side='home'`；同名主客隊亦可被錯誤分類。錯誤方向會污染後續結算，即使時間欄位完全合格也不能接納。

本次在處理 spreads outcomes 前，要求主客隊都是非空字串，而且去掉首尾空白後互異。實際選項仍須**精確匹配供應商原文**，沒有新增模糊隊名配對或自動轉換；大小球與不支援市場的處理保留。任何無效 spreads 身份令整個 envelope 拋出 ValueError，不回傳部分正常報價。

修改檔案：

- `ops/the_odds_api_adapter.py`：讓球主客隊身份閘門。
- `ops/tests/test_the_odds_api_adapter.py`：缺失、None、空白、重名、非字串、錯選項及反轉主客隊的測試。
- `ops/tests/test_bookmaker_timestamp_gate.py`：時間入口也拒絕無身份讓球；正常客隊四分盤保留線值與研究旗標。

身份合格僅代表 schema 可分類，不是來源獨立認證、真實可成交報價或正 EV。

## 先失敗，再修復

在未改 adapter 前加入四個新測試方法，執行：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest ops.tests.test_the_odds_api_adapter -v
```

結果：12 個 test methods，13 個 failure（subTest 逐案記錄）；均因本應拒絕的身份未拋出 ValueError。這是合成輸入缺陷重現，並非真實博彩公司資料。

修復後同一批負例及既有正例成功，另加入兩個 timestamp gate 整合測試，確保錯誤身份不能藉由合法時間欄位繞過。

## 本地驗收與獨立程式覆核

Python 3.12.14：

| 指令／檢查 | 實際結果 |
|---|---|
| `python -m unittest ops.tests.test_the_odds_api_adapter ops.tests.test_bookmaker_timestamp_gate ops.tests.test_frozen_forecast_join -v` | 47 tests OK |
| `python -m unittest discover -s ops/tests -q` | 2,493 tests OK，16 skipped，無失敗 |
| `python -m ops.install_age --destination /tmp/football-audit-age` | 安裝既有 hash-pinned age v1.3.2，通過 archive／binary SHA256；不是 sigsum 簽章驗證 |
| `FOOTBALL_AGE_BINARY=/tmp/football-audit-age/age python -m unittest ops.tests.test_private_response_relay ops.tests.test_private_drive_handoff -q` | 補跑上述 16 個原先 skipped 測試，全數 OK，無 skipped |
| `python -m compileall -q ops` | exit 0 |
| `python -m unittest discover -s tests -q` | 157 tests OK |
| shared ledger／evaluation／report／execution guard／screen／freshness／evidence gate／pipeline contract，加 `test_settlement_input_limits` | 72 tests OK（對應現有 unified-ledger-tests workflow 指令） |
| `git diff --check` | exit 0 |

獨立助理 `audit_settlement` 讀取三個程式／測試檔的 diff，獨立重跑 47 項相關測試，結論 **APPROVE（限本次窄範圍）**。這不等於 #439 要求的獨立人手 release approval，也不會解除 HOLD。

## CI 記錄方式

本報告提交時遠端 CI 尚未執行，不預先聲稱通過。新 Draft PR 的 description／Checks 會記錄實際 head SHA、workflow run URL、job conclusion，以及受 path filter 影響未自動執行的 workflow。只認對應該 head 的實際完成結果；pending／未觸發不算通過。CI 可檢驗的均是技術及合成回歸，不能當作真實盈利證據。

沿用現有 `research-settlement-tests.yml` 已覆蓋這兩個測試檔的 discover 指令，無需新增另一套 CI 或更改正式 workflow 設定。

## 範圍與風險

- 正常大小球、主／客讓球、線值及十進制賠率輸出保留，所有 `positive_ev_verified`、`production_recommendation_allowed` 仍 false。
- 缺失／同名／空白的 upstream 身份會開始 fail closed；這是預期資料品質限制，不能用放寬比對補資料。
- A02 等價快照去重、A03 真實擷取時刻、A04 負 total、A05 Decimal 精度，以及賽前外部見證／獨立結果認證均**尚未修復**，見 [完整審計及後續工單](phase1-system-audit-2026-11-06.md)。
- 未改既有 A/B/C 封存、模型權重、真實資料或正式投注設定；未合併、部署、呼叫真實賠率 API 或提供投注推薦。
- **未證實能提高預測**；只驗證身份入口拒絕行為與既有功能相容性。
