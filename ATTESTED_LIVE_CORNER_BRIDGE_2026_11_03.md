# 第十階段｜可信來源對照表 → 即場角球證據之端到端研究閘門

本階段是 Draft PR #408 的增量，stacked base #408。前置仍為 #403 → #406 → #408。目的係避免一個可信簽署過嘅 manifest、同一個**未經簽署或錯賽事**嘅即場角球快照，由兩段各自獨立程式驗證後被錯誤拼接。

## 新增研究 CLI

```bash
python ops/attested_live_corner_bridge.py \
  --snapshot /secure/local/live-corners-snapshot.json \
  --proof /secure/local/unpacked-sigstore-fixture-proof \
  --source-sha <independently-checked-40-hex-run-source-sha> \
  --workflow-sha <independently-checked-40-hex-workflow-sha> \
  --run-id <reviewed-github-run-id> \
  --attempt <reviewed-github-attempt>
```

前置 proof 係 **#408 正式 workflow 成功完成後產生**的 `fixture-manifest.json`、`fixture-manifest.sigstore.json`（需要本身符合 #408 規則）；原始 proof、受信任 GitHub run/context、quote、角球事件時間必須從合規來源取得。本PR無放置任何真實市場價格、密鑰或真實簽章示例。

程序依次進行：

1. 只接受 `corners_totals`；其他盤種由既有流程處理，不容透過新入口降級檢查。
2. 忽略 snapshot 自報 `decision_utc`，以執行當刻 UTC 計算90秒上游資料新鮮度（合成測試可注入固定 UTC）。
3. **重新執行** #408 `live_fixture_attestation_audit.audit`：依固定 repo、source SHA、workflow SHA、run/attempt 和 Sigstore Rekor Tlog 驗證簽署主體原始位元組同早於記錄開球至少10分鐘。
4. 驗證成功後，再次讀取同一 manifest，核對原始 SHA-256，防止核查前後 byte swap。只使用呢份有 digest 連結嘅 manifest 做 #406 native fixture ID、HTTPS url、開球時間一致性驗證。
5. 執行 #403 角球數、最新角球／入球事件、狀態與報價時間檢查。任何一段不合規、簽章驗證器 unavailable、發生檔案變更，一律 `HOLD`，不嘗試以自報 boolean `verified` 繞過。
6. CLI 對外**不顯示**原始比分、逐場角球、bookmaker、價格或證據網址，只顯示標準 `HOLD`／`RESEARCH_ONLY`、安全原因及永遠關閉的盈利／下注旗標。

## 信任界線與未完成部分

- `RESEARCH_ONLY` **只**代表當次 GitHub/Sigstore witness 的**聲稱記錄開賽時間**之前證據封存，與其後輸入的角球盤快照在格式、來源 ID、事件時序上自洽。**不代表**即場資料已由官方獨立驗證、莊家可成交價格有效、正EV、賽果或模型命中率已獲認證。
- 本身 `live_quote_snapshot_guard.audit_live_snapshot` 依舊可獨立運行，作為研究用途。對需要可信封存的角球端到端研究，應只使用本新 CLI；不要將獨立檢查器的 `RESEARCH_ONLY` 當成已驗證時間證據。
- 此次無真實 fixture proof、無真正 `gh attestation verify` 實際驗收、無合法授權高頻盤口資料，測試 `gh` 回應都係合成及模擬。新功能不得聲稱端到端實際資料收集已完成。
- 來源簽名只有認證 signer workflow + manifest bytes，不認證外部足球 feed 真偽。證明真實來源／當時角球／盤口可成交性必須另有第三方認證、授權、同場同刻數據及可追溯事件清單。
- API 配額、現有 A/B/C 研究資料、正式投注功能全部不變；`production_recommendations=DISABLED`、`certified_positive_ev=False`。
- 首次真正端到端研究需先完成 stacked PR 合併及 **main-only** #408 工作流簽署，然後用合法來源真實事件快照執行本 CLI；未完成前維持 `HOLD`。

## 測試

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_attested_live_corner_bridge.py' -v
python -m unittest discover -s ops/tests -q
```

12項新測試涵蓋合成 mock witness 通過、Sigstore 驗證失敗、已保存假報告、manifest 簽後被調包、不同賽事 ID、早於角球事件嘅報價、已結束／已決定角球市場、非角球盤繞過、偽造決策時刻、GH signer 不符、CLI 變造 JSON、輸出不洩露價格。**mock CLI 驗證成功並非真實加密驗證**。
