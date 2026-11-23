# 足球王者｜真實 OpenSSL RFC 3161 本地端到端測試（研究／HOLD）

## 目的：不再只以模擬 runner 聲稱驗證過密碼學

上游 #550 已有 `make_query` / `verify_response`，但以前 13 項單元測試以 mock subprocess 回傳「Verification: OK」，唔會證明實際 OpenSSL 參數正確、CA 鏈可驗或 nonce 真係受到保護。本 PR 只新增一個**獨立、真正在 CI 執行 OpenSSL CLI 的整合測試**，唔改生產 source feed、模型、盤口、封存格式、正式推介或 #550 核心實作。

`ops/tests/test_inplay_private_rfc3161_real_local_e2e.py` 會：
- 測試時即時在 `TemporaryDirectory` 建立 **只供測試** 的 RSA CA、專用 TSA 簽署金鑰及具 `critical,timeStamping` 延伸用途的證書；金鑰只存執行器暫存目錄、退出即清除，絕不提交到公開 repo、唔係真實可信 TSA。
- 從上游 `test_inplay_forward_private_seal.input_case` 生成純合成「雙來源＋quote＋截圖」材料，**一致平移全部時間**到測試執行時間，避免用過期固定測試資料；保留 `RESEARCH_ONLY` / `decision=HOLD`。
- 執行真正的 `make_query`，由 `openssl ts -reply -config ... -queryfile ... -out ...` 本地簽發完整 TSR，再真正執行 `verify_response` 的兩種簽章驗證（整包 tar SHA256 摘要、原始 TSQ nonce）。成功回傳只係 `cryptographic_imprint_check_passed=True`，其他所有資格仍為 `False`。
- **反證測試**：用同檔案但另一個 nonce 嘅請求核對原 TSR 必須 FAIL；用另一份有效候選 tar 嘅 SHA256 核對原 TSR 必須 FAIL；無效 CA 必須 FAIL；5分鐘前聲稱採集但現時才簽發嘅 TSR 必須因 120 秒限額被拒絕。
- 不會執行任何外部網絡呼叫、網站爬取、API 費用、授權原始資料下載；唔會上傳真實博彩報價、個人相片、TSA 私鑰或真正憑證。

## 關鍵限制

這只是**真實密碼學本地自簽測試**，唔係商業 TSA 承認嘅外部時間見證。任何持有本地測試私鑰嘅人都可以自己簽發新 token。當正式試點需要時，仲要另外取得獨立可信 TSA 回覆、TSA policy / issuer / revocation 驗證、真正 source-native ID 與兩源獨立性、合法使用與市場可成交證明。

2026-11-23 長野 vs 浦和嘅歷史 13:30 HKT 截圖仍然不得補封成當時已見證前瞻樣本。**本 PR 唔增加任何 certified forward samples。**

## 預定驗收

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

要求所有同 head GitHub Actions regression/safety/stress/validate/ledger tests 綠燈，並由獨立 reviewer 核查測試憑證信任界線。保留 stacked Draft：本 PR → #550 → #547 → #544 → main。

全程 `production_recommendations=DISABLED`、`decision=HOLD`、`positive_ev_verified=false`、`certified_forward_samples=0`。**合成測試 100% 不能當預測準確率增加或正 EV 證明。**

官方 OpenSSL RFC3161 命令說明：<https://docs.openssl.org/3.5/man1/openssl-ts/>。
