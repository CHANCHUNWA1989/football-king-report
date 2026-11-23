# 未來 shadow 原生身份欄位保存（2026-11-04）

當 OpenLigaDB 回應原有 `team1.teamId`／`team2.teamId`，原封存 gateway 只會輸出賽事 ID、球隊名字及賽程。本修復讓之後正常產生的 shadow 保留原生主客 ID 及同一次回應 SHA256，避免資料在封存前丟失。舊 shadow、paired、ledger、ABC／D 試驗及 ZIP 都保持原 bytes；正式推薦繼續 `DISABLED／HOLD`。

## 已實際修改

只有 `ops/shadow_forecast.py` 的預設 getter 加入同一次回應記憶體 buffer，透過原 ZIP `get_fixtures(openligadb_fn=...)` 及 `fetch_openligadb(opener=...)` 接縫。原有一個 HTTP GET 的 URL、12秒 timeout、8,000,001 bytes read bound、原 gateway normalizer、fallback、訓練、概率及時序邏輯沿用，沒有新增 API 請求或重試。沒有新增 flat `ops` module。

從**同一 bytes**按原生 matchID＋league shortcut／season 唯一定位，核對原件主客順序與原 normalizer 輸出。主客 ID 必須是真正正整數，排除 bool、負值、相同主客或超過有界整數的值。重複 matchID、同一回應矛盾 league ID／team ID綁定、錯scope、JSON重複鍵、NaN／Infinity或解析遞迴失敗均不產生身份 claim；有界原件缺項不改變既有研究預測。名字只用來拒絕同一回應的矛盾，從不由名字猜原生 ID。

未來 `predictions[].native_fixture_input` 是獨立、固定欄位的 `football-king-native-fixture-input-observation-v1`：

| 欄位 | 意義 |
| --- | --- |
| `schema, status, provider` | 固定版本、`UNAUTHENTICATED`、`OpenLigaDB` |
| `match_id, home_team_id, away_team_id, league_id` | 同一次原件已有、具型別的原生整數 ID |
| `league_shortcut, league_season` | 原件與請求一致的聯賽／賽季 scope |
| `source_response_sha256` | 記憶體中原件 bytes 的 SHA256，亦須與原 gateway 算出的 SHA 相同 |
| `native_ids_from_same_response_as_gateway_fixture` | 固定 true，只表達原生 ID 與 gateway fixture 來自同一次回應 |
| `source_identity_authenticated, source_capture_authenticated` | 固定 false |
| `raw_input_durably_archived, native_ids_used_as_model_features, eligible_for_model_scoring` | 固定 false |

同一原件計算／核對的 hash 亦保存在相應 `sources[].source_response_sha256`。只有預設受控 getter 的閉合輸出會帶這些欄位；外來 explicit replay getter 或 `predict_league` 輸入的同名 metadata／`verified=true` 不會被原樣複製。其他來源及原生身份缺失的行維持原研究行為。

沒有新增 response-completion timestamp：ZIP getter 的 callback clock 可能固定在入口時間，不能把它宣稱回應完成時刻。`generate` 仍在真實計算完成後取 live clock、重驗10分鐘 buffer；慢回應不會回填成早前預測時間。

## 測試通過

先在未修復版本用既有真公開原件 bytes 重現 `native_fixture_input` 缺失，再以原 ZIP gateway 作同一次 GET 離線重播。新 focused tests 涵蓋：

- 正向保留 match83234 的主客 IDs100／87及 exact response hash；每次執行一個 GET、沒有額外讀取或重試。
- 除新增身份／hash欄位後，整個研究輸出與原 getter 完全相等，包含全部概率、goal rates、training digest／count、model ID及時間。
- 錯型／缺項／矛盾／重複身份、scope、JSON鍵及非有限數值、hash不符、外來信任旗號、讀取上限、上游失敗及 live completion buffer。

本項新增17個測試；連既有 shadow、completion-clock及 schedule-enrichment focused tests 共62項通過。只作有界離線檢查，沒有新供應商請求、全套測試、PR合併或新正式資格宣稱；完整回歸、獨立精確版本審核、CI及部署另由主助理跟進。

## 需外部資料／未完成驗收

此修復沒有長期保存該次 HTTP 原始 bytes，hash 不能取代原件，也不能證明 publisher 真偽、跨源身份、actual kickoff或90分鐘最終比分。新的 metadata 尚未接到正式 admission／certified ledger／未來正式 cohort policy；舊 v1 identity validator及 market pair schema 不變。新產生 shadow 的既有簽封流程會包含這些新增欄位，但部署後仍須獨立核對真正新封存，不能把離線重播當作已完成的未來 joint proof。

私人受控執行如 pin 此既有 `ops/shadow_forecast.py`，需要主助理按精確新source版更新相容 pins、保留歷史版本；本工單不改私人設定或排程。

## 未證實能提高預測

這是資料保存修復。它沒有新增已認證樣本、改變模型預測或證明優於市場；原300場／12合資格週／4聯賽各40場及其餘品質、校準、風險和最後人工審核門檻繼續生效。
