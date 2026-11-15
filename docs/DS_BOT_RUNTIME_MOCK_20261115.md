# 足球王者 VNext × DS Bot — 第三階段：真 Web 程序＋模擬模型之 Bot 交接驗收

狀態：**研究測試 / HOLD / DISABLED**。此項目接續 Draft PR #471（受限研究交接）與 Draft PR #472（已驗證上游套件安裝與 mock 單元測試）。**不曾將 DS Bot 安裝到用戶手機、電腦或 VNext 正式站點，也沒有永久運行的可供 ChatGPT 連線之 DS Bot 服務。**

## 已核實的來源與固定版本（2026-11-15）

- DS Bot 社群上游：`Fei2411/DS-Bot` v0.3.6，源碼 commit `a66cc737cfb6c3d8a2597e748cded6cab1206dd3`；`LICENSE` Apache-2.0，須尊重 `NOTICE`。
- DSH 官方上游：`deepseek-ai/deepseek-harness` v0.2.2-rc.1，原始碼 commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db`，MIT。這個版本與 DS Bot `dev/harness/package.json` 及官方測試設定相符。
- 官方 DS Bot `ds-bot/dev/check.sh --only smoke` 透過 `dev/bench.sh` 啟動本地 DeepSeek Harness Web 及**本地模擬模型**，由 `dev/smoke.mjs` 真正呼叫本地 `/api/bot`、建立 Chief / Writer / Coder、群聊及多段消息交接；重點包括 Writer → Coder → Chief 返回，並覆核實際 exchange log。這不是只測模組 import，而是對 localhost 服務作互通驗證。

## 本 PR 修改

只加入：

1. `.github/workflows/dsbot-runtime-mock-smoke.yml`：獨立 GitHub 臨時 runner、兩個上游來源及 actions 固定 SHA、Node24/固定 pnpm、鎖檔安裝、建立 DSH Web、跑上游 mock 模型真流程。所有實際 ChatGPT/DeepSeek、體育／博彩公司金鑰皆**不傳入**；GitHub token 只有 `contents: read`，且 checkout 設定 `persist-credentials: false`。
2. 本文件：驗收範圍與安全限制。

CI 執行結束後清理本地測試 mock Web／模型進程，GitHub runner 隨即銷毀。**不對外發布連接埠，不使用任何已連接的私人模型、賠率、檔案、帳戶或真實賽事資料**。這個測試可能需要為上游工作區安裝可執行依賴，只在無密鑰、臨時 runner 中進行；並不證明所有上游第三方依賴完全安全。

## 驗收與停止條件

- 最新 PR HEAD 的 GitHub Actions job 必須成功；核查原始 log 確認初始化 Web／模型服務、Bot 對話交接步驟及退場程序，披露任何跳過／失敗／未執行項。
- 如上游啟動、模型模擬回應、群聊及消息傳遞出錯，**修正根因後重跑**，不可將測試刪掉、改為靜態檢查或宣稱真正 Bot 互通成功。
- 不向 `main` 合併；未完成獨立人工審核及 Issue #439 中 `main` 保護、必需 CI 規則之前，繼續 Draft / HOLD。
- 這是**本地 Web 執行器＋模擬模型**，不等同任意一個真實 LLM 或 ChatGPT 已能直接同 DS Bot 通訊。
- 不啟動投注、正式賽事推薦、寫入市場／賽果／A-B-C、改動 V4.1；不將 synthetic 測試數當前瞻認證、正EV或提升命中率。
