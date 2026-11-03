# AI 研究控制塔｜第三階段：定期只讀監察

狀態：獨立研究分支；正式放行未批准。正式交易推薦 DISABLED、live_execution_allowed=false、verified_positive_ev=false、HOLD 均不變。

## 新增範圍

- ops/control_tower_monitor.py：只讀倉庫內已封存 h2h 市場快照，及 GitHub 公開 main、PR、最近 workflow runs API。不查投注供應商 API，不讀私人倉庫及密鑰。
- .github/workflows/football-king-control-tower-readonly.yml：每六小時 best-effort 排程及手動執行，生成 control-tower-public-evidence artifact（七日保留）；不寫入 main、不部署 Pages、不建立 Issue。
- ops/tests/test_control_tower_monitor.py：來源時鐘、10 小時過期、未來時鐘、格式錯誤、API 缺失、PR CI 樣本不足、API URL 白名單等 fail-closed 測試。

## 證據界線

1. 只有來源 as_of_utc 帶時區、十小時內、無異常未來時間，且符合 RESEARCH_ONLY、h2h 和數據完整性，才報 CURRENT_RESEARCH_ONLY。
2. generated_at_utc 僅為監控報告建立時間，並非上游資料發布時間，更非即秒實盤。
3. 最近 workflow runs 只屬樣本，不保證涵蓋所有 required checks。OBSERVED_PASS_NOT_EXHAUSTIVE 不代表可以合併、模型有預測優勢或可下注。
4. 資料不齊、失效或 GitHub API 不可用，報 HOLD／UNKNOWN；不推定最新、不推定 CI 通過。
5. JSON 只包含公開足球倉庫的摘要，不包含籃球／量化私人倉庫內容、API keys、下注或交易帳戶。
6. 排程只在預設分支啟用；本 Draft PR 未合併不會啟用定時監控。另需獨立安全審批。

## 本地驗收

python -m unittest discover -s ops/tests -p test_control_tower_monitor.py -v
python ops/control_tower_monitor.py --offline --output /tmp/control-tower-public.json

GitHub Actions → Football King Control Tower (read-only evidence) → Run workflow → 查看 artifact。
