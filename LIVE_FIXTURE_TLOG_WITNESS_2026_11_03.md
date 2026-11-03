# 第九階段：即場賽事來源對照表可信封存（Issue #401）

此工作延續 Draft PR #403（角球盤內容及時序）與 #406（各供應商 native fixture ID 一致性）；第九階段修正 #406 中 `registered_at_utc` 只是提交者自行填寫、可以事後回填嘅信任缺口。

## 已增加（研究模式）

1. `.github/workflows/football-king-live-fixture-seal.yml` 只可由 **main** 進行 `workflow_dispatch`，需要指定已**提交公開儲存庫**的 `research/live_fixture_manifests/<ID>.json`；沒有授權商業賠率或者 private API 使用權，不能把原始盤口或秘密放入公開檔案。
2. 工作流核查固定四欄 manifest schema、每個來源唯一原生賽事 ID、確切 HTTPS 來源地址及聲稱賽前登記時刻；離記錄開球時間必須至少有15分鐘才能嘗試封存。
3. 以既有 GitHub/Sigstore `actions/attest`（固定 commit）對**相同 bytes**簽署，產生 bundle；`ops/live_fixture_attestation_audit.py` 當次重新執行 `gh attestation verify`，核對固定 GitHub source SHA、workflow SHA、run ID、attempt、`refs/heads/main`、hosted runner、簽章主體 SHA-256，以及 Sigstore 已驗證的 Rekor Tlog 時間。
4. 唯有可信 Tlog 時間較**文件記錄**的開賽時間最少提前10分鐘，才可回傳 `RESEARCH_ONLY`；缺 Sigstore、簽章失敗、回填時間、檔案被修改、他場來源ID、錯 issuer、錯 run／workflow 或簽後才來得及上傳，必須 `HOLD`。
5. `ops/tests/test_live_fixture_attestation_audit.py` 提供合成／mock-gh 的正負測試。**模擬 subprocess 並非真正簽章驗證**；只能證明政策邏輯。

## 使用

本 PR 目前是獨立 Draft，尚未合併；workflow 唔可以當成已在 main 運作。整合通過審核後，先將不含私人資料嘅 manifest 提交到 main，例如 `research/live_fixture_manifests/example-case.json`，並在真正開賽之前從 Actions 手動執行 `Football King Live Fixture Manifest Sigstore Witness (research only)`，輸入其固定相對路徑。

工作流出產 `fixture-manifest.json` + `fixture-manifest.sigstore.json` 兩份文件；下載後可執行：

```bash
python ops/live_fixture_attestation_audit.py \
  --proof path/to/unpacked-fixture-proof \
  --source-sha <reviewed-40-hex-run-commit> \
  --workflow-sha <reviewed-40-hex-workflow-commit> \
  --run-id <github-actions-run-id> \
  --attempt <run-attempt>
```

所有 GitHub run/workflow SHA/ID 需由**可信 GitHub REST/Actions 頁面獨立核對**，不可直接信任證據包 JSON 自報值。與實際即場判斷結合時，仍須同 #406 角球盤 manifest 配對檢查一起使用；簽章 witness 不直接通過即場數據或任何投注閘門。

## 不能聲稱

- 「簽署過」只證明**某份 manifest 原始內容**在可信透明日誌時間之前受指定工作流簽署，唔代表供應商是真官方、原生賽事 ID 係真實、真實開波時間已被獨立認證。
- 任何可信時間戳都唔會自動證明角球／比分更新時間真確、博彩盤口可成交或模型命中率提高。
- 現時無真實已封存即場 AH／角球 quote 可供驗證；唔可以將測試數字當成實際勝率或正EV。
- 工作流唔收集商業原始盤口、唔花任何第三方付費配額、唔改歷史 A／B／C、唔落注。
- 產物存放於 GitHub Actions artifact，初步保留90日；需另外有合規持久保存方案先可作長期回測原件。
- 正式 `production_recommendations=DISABLED` 及 `HOLD` 完全保持。

## 驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

CI全綠只係程式碼回歸；待真實合法來源首次成功封存並**重新驗證透明日誌**，先可稱已完成外部實證。即使成功，仍需獨立核實來源時間、賽事狀態及未來模型樣本外能力。
