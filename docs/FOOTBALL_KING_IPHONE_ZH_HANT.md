# 足球王者｜手機版整合操作手冊

本功能仍屬研究階段，**正式推薦未開放**。中文頁面顯示已保存的研究快照，
並非即時報價，亦不等於已經核實獨立預測準確率。

## iPhone 查看報告
1. 開啟 [GitHub Actions](https://github.com/CHANCHUNWA1989/football-king-report/actions)。
2. 找到「足球王者｜繁體中文整合驗收」成功執行的紀錄。
3. 在該次執行的 **Artifacts** 下載 `football-king-zh-hant-mobile-report`。
4. 解壓縮後以 Safari 或 iPhone 檔案 App 開啟 `index.html`。

注意：GitHub Actions 的排程與手動啟動功能，通常需要工作流程存在於預設分支。
目前這些改動仍在待審核的 PR #188 研究分支；請勿只為啟用按鈕而跳過審核。
推送研究分支可觸發既有的 push 驗收。報告附件保留 14 日。

## 自動化範圍
- 在 workflow 生效的分支上，每日 UTC 02:35 重新產生研究報告。
- 每次均測試中文網頁、賽後評分與推薦證據驗收程式。
- 只讀取 repo 已保存的 JSON 快照；**不會自動購買 API 額度、抓取新賠率或補齊賽果**。
- 不會發佈原始莊家賠率、API 金鑰或投注指令。

## 報告資料來源
- `market/latest.json`：獨贏市場共識快照。
- `market/private_summary_latest.json`：研究覆蓋及證據進度。
- `sources/seven_quality_gates_latest.json`：七項品質關卡。
- 如提供 `--shadow`、`--readiness` 或 `--market`，可以額外加入獨贏賽後評分、驗收及三市場品質報告。

## 正式推薦所欠證據
必須取得真實、可追溯的賽前獨立預測、獨立核實的賽果、
足夠的樣本外回測、概率校準及人工審批。單純 CI 綠燈不代表命中率或盈利能力。
