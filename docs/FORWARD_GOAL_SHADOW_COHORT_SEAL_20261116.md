# 足球王者｜全新前瞻 OU2.5／BTTS 完整賽事名單凍結閘門（2026-11-16）

## 今次工單與現有研究關係

- PR #485：修正 OU2.5 回測偷用測試結果做基準；
- PR #486：樣本外校準失敗，必須否決；
- PR #488：2,380場固定歷史源重跑，探索性75/25分聯賽大小球混合；**不能用舊回放當成未見新場次的已驗證改善**。
- PR #458：已有獨立 OpenLigaDB Bundesliga 原版A／Poisson／Dixon–Coles 1X2研究擷取；本工單不改該分支與已封存資料。
- **本PR只新增離線 prospective input gate，唔代替任何上游原件擷取、簽署、盤口來源或賽後雙源覆核**。

## 目的

喺下一場尚未開賽的真正新賽事開始前，為固定聯賽／來源擷取完整賽事Universe：
`source.fixture_id`（來源命名空間及原生ID）、球隊原生ID、真實上游開賽UTC時間；
同一擷取來源的最新已完成歷史及原版A入球預測；固定上季訓練期大2.5／BTTS比例。

**所有來源身份／時間皆只係上游自報 metadata**。本工具無任何真正獨立HTTP/來源認證能力。
真實來源如不可獲得、資料過時、身份對不上、開波前10分鐘不足，就必須 HOLD 或拒絕。

## 固定候選概率（研究用途）

`Over2.5_A = 1 - exp(-(λ_home + λ_away))*(1 + λ_total + λ_total^2/2)`；
`BTTS_A = (1-exp(-λ_home))*(1-exp(-λ_away))`。

對每個市場：
`shadow_blend = 0.75 * original_A + 0.25 * (training-only league prior)`。

**25%於探索性歷史資料下提出；已接觸舊賽果，仍然必須用真正全新前瞻獨立測試。**

- 必須列出來源原始SHA256、收到來源的時間、訓練資料SHA256／截止時間及最少30場訓練數；
- 需指定固定模型Git SHA，要求同一批資料同一版本，模型計算時間唔可以早過來源HTTP收到時間或晚過當前時間；
- 所有fixture都要比當前runner UTC時刻至少早10分鐘以上（未開賽），來源擷取不得早過30分鐘；
- 每一個上游提供fixture都保留，即使缺原版A入球率亦要輸出 `HOLD_NO_PREMATCH_MODEL`，以免只揀最容易預測比賽作回測；
- 對缺失原版A rates、損壞身份、過時時戳、NaN、附帶賽後比分或盤口之輸入拒絕／保留HOLD；
- 使用標準 `SHA256` 對封存 JSON deterministic 編碼，生成只准新建、不得覆蓋的輸出；**原件加SHA不等於外部獨立時間簽署**；
- 始終 `status=HOLD`、`eligible_for_model_promotion=false`、`certified_prospective_samples=0`、`production_recommendations=DISABLED`；
- 絕不宣稱已經有經確認正EV、ROI、盤口可成交、外部Sigstore/Rekor/TSA或獨立賽果證據。

## 程式使用

```bash
python -m ops.forward_goal_shadow_cohort_seal --input actual_live_native_source_input.json --output never_overwrite_utc_cohort.json
```

CLI固定使用GitHub runner本身 UTC 時鐘（不能由輸入檔指定偽造 `now`）；其 `now` 引數只在無網絡單元測試注入。CLI 遇到真實來源不足時 fail-closed。

輸入schema範例（**全部係虛構資料結構，唔係真賽事／真盤口**）：
```json
{
  "schema": "football-king-forward-goal-shadow-cohort-v1",
  "production_recommendations": "DISABLED",
  "source": {
    "namespace": "openligadb", "league": "bundesliga",
    "source_response_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "source_received_utc": "2026-11-16T15:20:00Z", "source_capture_id": "sample-run-37"
  },
  "training": {
    "league": "bundesliga",
    "training_source_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "training_cutoff_utc": "2026-11-15T23:00:00Z",
    "training_match_count": 120,
    "over25_frequency": 0.53, "btts_frequency": 0.56
  },
  "fixtures": [
    {"fixture_id":"openligadb:10001","home_team_id":"100","away_team_id":"101","kickoff_utc":"2026-11-21T12:30:00Z"}
  ],
  "forecasts": [
    {"fixture_id":"openligadb:10001","model_revision_sha":"e466196956a0780776bc90ef1168f6c462024c3e",
     "computed_utc":"2026-11-16T15:25:00Z","expected_home_goals":1.7,"expected_away_goals":1.2}
  ]
}
```

## Genuine future-match one-GET read-only pilot (added)

`ops/live_bundesliga_goal_shadow_freeze.py` now uses the repository's **original
pinned V4.1 fixture gateway** plus existing `ops.shadow_forecast.predict_league`.
It makes one real OpenLigaDB HTTP GET from GitHub Actions, reads the original
same-response native fixture IDs, and freezes ALL source-listed scheduled
Bundesliga games from now+10min through 7 days. Only the original A expected
home/away goal rates for those fixtures are used; missing A model outputs
remain explicitly in the future cohort with `HOLD_NO_PREMATCH_MODEL`.

A league-specific OU2.5 / BTTS training prior comes from actual earlier
FULL-TIME results seen in that same public HTTP response (at least 30 unique
matches). The prior's `training_cutoff_utc` is the *latest included
previous-match kickoff*, NOT externally verified result first-publication
time. Model calculations occur AFTER the HTTP-response receive time.
All times and publisher identity remain unauthenticated; no betting odds.

Workflow `.github/workflows/forward-bundesliga-goal-shadow-freeze.yml`
verifies the original ZIP SHA-256, runs 11+8 focused safety tests and full
regression, then performs **a genuine current one-GET research capture**.
It stores one immutable-for-artifact-retention GitHub Actions artifact for
up to 90 days; GitHub artifact retention is NOT a permanently signed or
external timestamped witness.

If OpenLigaDB is unavailable, data invalid, no scheduled game in the next
seven days, or original model missing, the job fails / records HOLD
instead of fabricating a pregame sample. A green run validates technical
collection, **not** independent publisher authentication or profitable
predictions.

## 验收、限制及下一個真正前瞻依賴

1. GitHub Actions要確認新增11個正負向測試通過、全部回歸同原版安全測試成功；CI通過僅能證明閘門運作。
2. **本輪仍未完成獨立可信第三方簽署的Live ingestion**：此程式從使用者供應JSON讀取；若未有真實來源抓取，不得聲稱有一場新賽前預測。
3. 真實前瞻必須透過現有合法 OpenLigaDB 實況取得來源原始bytes／native IDs／UTC來源時間與歷史 cutoff，先可呼叫本工具；封存需外部見證，之後只讀跨兩源賽果。
4. 每個新前瞻批次要同場保存原版、Poisson、Dixon–Coles及本Challenger的概率；本工具現只產生原版A率的OU/BTTS Challenger，不宣稱已做到三模型同盤配對。
5. 研究成果不得改已封存原版，亦不得直接提供真實下注建議。

留在 Draft/HOLD，獨立審核前禁止合併主程式或升級正式投注。
