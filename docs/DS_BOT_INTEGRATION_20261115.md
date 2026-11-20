# 足球王者 VNext × DS Bot：離線研究交接／階段 1（HOLD）

日期：2026-11-15（香港日期）。

**完成範圍**：只新增受限 JSON 交接格式、離線只讀的 Python 拒絕閘門與合成回歸測試。**沒有安裝／啟動 DS Bot、DeepSeek Harness 或常駐 Bot**，沒有把 Bot 輸出接入正式預測、模型、盤口、網站或 GitHub Actions 定時更新。

## 上游與授權核實

- 原始碼：https://github.com/Fei2411/DS-Bot
- 2026-11-15 核對的上游 `main` SHA：`a66cc737cfb6c3d8a2597e748cded6cab1206dd3`；最新 Release `v0.3.6`（2026-11-12）。
- `LICENSE`：Apache-2.0；`NOTICE` 包括依賴／第三方來源及 DeepSeek Harness MIT。現階段不複製或嵌入 DS Bot 原始碼，不新增 npm、pip、Docker、付費依賴。日後要散布上游程式必須保留適用 LICENSE、NOTICE 與變更標示。
- `README.md`：DS Bot 是基於 DeepSeek Harness 的桌面／插件多智能體平台，**不是**即用的 Python 足球分析程式庫，亦非 DeepSeek 官方項目。
- `SECURITY_MODEL.md` 明確標識網頁、工具回應、Bot 訊息為不可信任內容，並以 Prompt Injection 為主要威脅。其 Docker 設定包含 `danger-full-access`／`approval never`，在容器內無逐項審批；**本 PR 不使用其 Docker 或賦予 Bot GitHub 寫入權限、Secrets、下注帳戶權限**。

## 本倉庫安全基線

直接檢查 GitHub `main`（2026-11-15）：commit `2b5c5c2eaf0d87c4c3547b07e85acccfdf687db2`、`protected=false`、rulesets `[]`。Issue #439（保護 main／獨立人工審核／可核實 CI）仍然開啟。PR #470 是 Draft／未合併。因治理缺口，**本研究分支只能以 Draft PR 呈交，不得合併／部署，不能讓 Bot 直接推送 main**。

## 最小權限架構

1. **可選外部 DS Bot（此階段未啟動）**：`fixture_audit` 檢查賽程身份／時間，`market_audit` 評估市場授權與時效缺口，`model_challenge` 質疑研究假設，`review_notes` 產出批判意見。
2. 將 DS Bot 訊息**人工匯出**至與 GitHub 倉庫分離的本地沙盒 JSON 檔案。所有文字、網址及身分主張一律不可信；「review_notes」不等同獨立 GitHub 人工核准。
3. 執行 `python -m ops.ds_bot_handoff_gate --input /path/to/sandbox/handoff.json`；模組**只讀檔案、無網絡請求、不執行模型內容、不寫入網站／賽前快照／資料庫／模型**。
4. 輸出只有 `status=HOLD`、`production_recommendations=DISABLED`、數量、未認證指紋。絕不回傳 Bot 原始文字或網址。SHA256 僅是重複性比對，**不是**身份認證、外部見證、來源授權或資料時序證明。

## JSON 合約（合成示例）

```json
{
  "schema": "football-king-dsbot-handoff-v1",
  "origin": "ds-bot",
  "run_id": "synthetic-example-1",
  "generated_at_utc": "2026-11-15T05:59:00Z",
  "as_of_utc": "2026-11-15T05:00:00Z",
  "status": "RESEARCH_ONLY",
  "production_recommendations": "DISABLED",
  "observations": [
    {
      "role": "fixture_audit",
      "note": "Synthetic fixture identity question, not authenticated.",
      "references": ["https://example.org/fixture"]
    },
    {
      "role": "review_notes",
      "note": "Synthetic challenge, not independent approval.",
      "references": []
    }
  ]
}
```

時間只接受 RFC3339 UTC 秒（`Z`）；範例 24 小時後會被判過期。JSON 最多 64 KiB，只接受列明欄位、1–4 個互不重複的研究角色、每角色最多 4 個乾淨 HTTPS（不允許帳密／query／fragment）參考網址。禁止重複 JSON keys、symlink、過時、未來／倒流時間、`production_recommendations=ENABLED`、額外認證欄位、執行命令欄位。失敗返回 `HOLD`、退出碼 2。

任何參考 URL 均是**自稱**線索，非獨立驗證原件；模組沒有產生前瞻合格樣本、真正可成交賠率、正 EV 或預測準確率改善的機制。

## 本次與下一階段驗收

本地（合成）：
```sh
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ds_bot_handoff_gate.py' -v
```

PR CI 必須檢查 `python -m unittest discover -s ops/tests -v`，以及原封存 V4.1 SHA256／相容測試、stress job、Repository Safety Python 3.11／3.12。所有跳過項、錯誤及最新 HEAD 的原始 logs 分開報告；單元測試成功不等同真 DS Bot 已裝或真來源認證。

**下一階段 NO-GO 前置條件**：安全審查及簽章釘選的實際 DS Bot 執行器、限定資料夾與最小權限、單向導出、合法來源授權、Prompt Injection 測試、獨立人手審批，以及確實生效的 main 保護／CI 必要檢查。任何一項未完成均維持 **HOLD/DISABLED**；不得自動投注、付費升級、合併／部署、讀取 Secrets 或修改封存 A/B/C、原 V4.1。
