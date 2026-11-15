# VNext PR-06 OOS 結果 SHA-256 交叉綁定修復 — 2026-11-15

**研究用途、不可部署／不可用於投注；疊加 Draft #435 的最小補丁，見 Draft #475。**

## 事前缺陷與重現（紅燈）

`ops/vnext_prospective_block_bootstrap.evaluate_sealed_holdout` 會：
1. 核對封存預測檔案 SHA、事前樣本清單、觀測來源政策、兩來源終場比分一致。
2. 只對照其中一份觀測來源的比分與評分所用的 `case["result"]`，然後呼叫原 `_row` 對成對模型評分。

**缺失：** `case["result"]["raw_sha256"]` 可以係任意格式正確但完全不對應任何觀測 `raw_sha256` 的字串。來源同分不會自動綁定結果雜湊。新增紅燈測試 `test_result_digest_must_crosslink_to_at_least_one_observation` 先在 PR HEAD `9012fa6fd828ee42e24474ae33b1e63252afe4cd` 的核心 CI **失敗**：2,477 tests、1 error，`KeyError: 'reason'`，證明舊評估產生了不應該通過的探索結果，而非拒收。其他 2,476 項未報錯。此時**不應將紅燈視為可合併**。

## 最小修復（綠燈）

仍用原本 `audit_source_independence` 的固定政策、來源格式及分數一致性檢查。於調用 `_row` 計分前，新增 fail-closed 綁定：

```python
if case["result"]["raw_sha256"] not in {
        row["raw_sha256"] for row in case["result_observations"]}:
    raise ValueError("RESULT_DIGEST_NOT_BOUND_TO_SOURCE_OBSERVATION")
```

並將唯一原有 300 場 **synthetic 測試資料**的結果雜湊改成同觀測記錄一致（這不是修改任何真實或賽前封存的歷史賽果）；新增測試覆蓋兩觀測均不匹配、只對應第二份觀測仍限探索，及舊有來源分數衝突拒收。**冇**改模型、權重、報價、數據採集、付費 API 或正式輸出。

## 勿混淆「Digest 交叉綁定」與「真正原始檔案驗證」

- 本補丁只檢查兩個 caller-supplied SHA-256 字串有相符之處，**沒有**取得或重新 SHA-256 計算任何來源原始位元組，也不驗證檔案實際存在、授權、來源身份或兩個 provider 是否有獨立上游。
- 假如用戶想證明「賽果 SHA-256 真正對應到觀測原件」，需要在**受控／有授權的非公開工作空間**把真實 raw bytes、獨立固定的預期 SHA 與收到時間、provider-native fixture ID、來源權利及證據鏈逐一配對；現階段倉庫並無足夠原件，絕不能補造原件或聲稱已完成。
- 若來源整體一致但未受獨立認證，OOS 評分仍只能是 `EXPLORATORY_ONLY`，`independently_verified_result_n=0`、`model_accuracy_improvement_verified=False`、`positive_ev_verified=False`、`production_recommendations=DISABLED`；digest 錯誤則整批 `HOLD`。
- #436 的 `link_fixture` 已經在另一層做同類 SHA membership 檢查；本次處理的是 #435 **單獨執行的 cohort evaluator**，避免漏閘。PR 疊加順序與安全審批不得繞過。

## CI 與治理要求

最終綠燈以 **最新 HEAD** 的 GitHub Actions 原始日誌為準，至少 `python -m unittest discover -s ops/tests -v`、原 V4.1 hash 相容及各安全 workflows；詳細測試數與 skipped 要在 PR comment 註明。獨立人手審核、授權原始賽果、外部可信時間與 #439 分支保護未完成，必須 Draft / HOLD / DISABLED，唔可 merge／deploy／下注。
