# 足球王者 × ChatGPT Work / Codex：安全交接

## 呢次整合實際做到咩

原有 GitHub 工作流程 `.github/workflows/football-king-agent-audit.yml` 繼續定時／由成功採集工作流程觸發，使用 `ops/agent_orchestrator.py` 讀取本庫已存快照。本次增加**離線唯讀交接摘要** `chatgpt-handoff.md`，作為同一個 Actions Artifact `football-king-agent-audit` 的一部分。沒有新增 GitHub 排程，沒有新增付費 API、OpenAI API Key 或直接呼叫 GPT。

- 審計：檢查現有快照、缺失組件、狀態及證據。
- 交接：把有關項目整理成適合 ChatGPT Work / Codex 接手的安全摘要。
- 維護：在 ChatGPT Work 使用已授權的 GitHub 連接閱讀原始程式、AGENTS.md 及摘要；Codex 可在授權的環境提出修補 PR。
- 護欄：保留 `production_recommendations = DISABLED`、`automatic_bets = False`；不能聲稱已驗證正 EV、命中率或真實下注價。

**注意：這是工具接力，不是自動替 ChatGPT 開啟背景工作。** GitHub Actions 本身唔會自動觸發 ChatGPT Work；Work 需要由用戶喺 ChatGPT 介面啟動同授權。PR 必須按現有安全審核及 CI 要求處理。

## iPhone 最短使用步驟

1. 在 ChatGPT 選擇 Work（如帳戶介面提供）；到 Plugins／Apps 連接 GitHub，選擇 `CHANCHUNWA1989/football-king-report`。
2. 在 [GitHub Actions](https://github.com/CHANCHUNWA1989/football-king-report/actions/workflows/football-king-agent-audit.yml) 選擇最新一次成功執行，或在需要時按 `Run workflow`；唔需要貼出任何金鑰。
3. 在該次 Actions 執行下載 `football-king-agent-audit`，檢視 `chatgpt-handoff.md` 同 `agent-audit.json`。未成功執行就唔應該假定檔案已存在。
4. 在 Work 下指令：「請查看我 GitHub 足球王者最新 `AGENTS.md`、Agent audit 同 handoff，選一項有證據嘅問題作唯讀審計、修復及測試。保持免費來源及 `DISABLED/HOLD`，開草稿 PR，列出 CI 結果。」
5. 檢查草稿 PR 和實際 Actions 結果，再決定下一步；勿將 Workflow 顯示 `success` 當成預測模型已校準。

## 技術操作／離線檢查

```bash
python -m unittest discover -s ops/tests -p test_chatgpt_handoff.py -v
python ops/agent_orchestrator.py --output agent-audit.json || test "$?" -eq 2
python ops/chatgpt_agent_handoff.py --input agent-audit.json --output chatgpt-handoff.md
```

如現有資料不足，審計會 HOLD；交接檔案只反映已核實檢查結果。上述指令不讀取 API Keys、不觸發外部收費數據收集。**本庫為公開儲存庫，切勿提交 Secrets／私人報價。**

## 三個系統擴展

完成足球王者的 GitHub PR 及實際 CI 後，才逐個複製同一模式到全球籃球 AI 和金融 AI。每個倉庫各自使用獨立工作流程、風控、測試與權限，避免共享憑證或把未驗證模型自動升格為正式決策。
