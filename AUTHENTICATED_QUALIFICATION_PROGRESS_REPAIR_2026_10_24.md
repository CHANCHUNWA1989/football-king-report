# 研究記錄與正式認證進度分開（2026-10-24）

本輪修正資格進度失實，沒有完成可信賽果 admission、增加認證樣本或啟用正式推薦。

## 已重現問題

`production_gate.gate` 接收符合既有研究 ledger schema、全部獨立賽果旗號為 false 的300筆合成測試行，分布12週及4聯賽各75筆，原先會將300場／12週／4聯賽三項正式條件標為 true。`evidence_progress.measure` 亦將認證不足額算成0場／0週。手機版把這些數字標成「正式模型驗證進度」及「獨立週期」。正式推薦仍被其他條件擋住；本輪處理錯誤資格與完成度，並非已重現自動下注放行。

實際發布前讀回：2026-10-24T10:08:54Z 的公開 production_gate／evidence_progress 為48筆研究、3個記錄週次，顯示差252場／9週；同期 official_readiness 已正確顯示0認證／仍欠300。本輪統一這條現有發布鏈，避免互相矛盾。

## 改動與驗收範圍

- `ops/production_gate.py`：保留頂層舊研究統計及明確 `recorded_research_*` 欄位。正式三條件保持 false；認證統計0／0／0、不足額300／12／4，新增 `AUTHENTICATED_FORWARD_ADMISSION_NOT_IMPLEMENTED`。巢狀 validation_progress 的舊正式計數與不足額也修正為0及完整不足額，不能靠舊 consumer 再將研究數當正式達標。來源自行標記另列，不當認證。
- `ops/evidence_progress.py`：研究結算、週次、聯賽覆蓋仍可查看。保存的 JSON、簽章／reviewer 布林標記及自行聲稱 authenticated aggregate 不能減少認證不足額。兩出版者比分一致只列 `recorded_two_publisher_exact_score_agreements` 研究觀察，原認證意味欄位保持0；亞洲盤報價亦不當可成交價。
- `ops/mobile_dashboard.py`：動態與靜態手機面板均分開顯示已記錄研究與已認證資格。動態 renderer 保留舊報告研究欄位作描述相容，但不信任保存 JSON 自報的認證計數、要求值或剩餘值；因目前無 admission，正式顯示固定0/300、0/12、0/4。靜態面板同樣處理；未來真 admission 接入時需要一起改 consumer 並另行驗收。

這是既有 fail-closed 研究計數鏈的修復，並非新建一個永遠拒絕的 stub 後宣稱完成驗證器。其餘獨立概率校準、來源採集／上游、權威身份橋接、實際開賽時間、獨立90分鐘賽果、可成交價及最終審批仍待完成。固定來源政策、原 A/B/C 封存、權重、賽果 ledger、原 ZIP 及所有正式門檻未修改。

## 測試

先加入並執行失敗測試，再修復。新增7個測試方法：300筆有效研究 ledger 反例、偽造 aggregate／簽章聲稱、來源核實行旗號拒絕、缺 schema、真 Node 執行發布用 renderer、靜態手機面板反例。這些合成行只在測試記憶體及清楚標記的診斷收據，沒有寫入任何正式研究 ledger 或當作真實球賽。

- `python -m compileall -q ops`
- `python -m unittest discover -s ops/tests -q`：1,767項通過。
- `python -m unittest discover -s tests -q`：150項通過。
- Node 執行 renderer 的舊報告／偽造認證聲稱／空值／錯型別情境通過；研究數字保留、認證不足額不變。
- `git diff --check` 通過。

獨立覆核、PR CI、合併及發布結果以相關 PR 的實際收據記錄；未完成的步驟不能視作已驗收。本輪程式及離線測試無新增供應商請求，既有 CI／網站發布仍會按原流程讀取公開足球來源。測試通過不證明預測命中率、校準或盈利改善。正式推薦仍為 DISABLED／HOLD。
