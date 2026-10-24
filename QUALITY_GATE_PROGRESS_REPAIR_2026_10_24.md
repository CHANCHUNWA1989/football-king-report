# 七項品質進度一致性修復（2026-10-24）

## 實際問題與處理

公開進度對同一 key 的第一個 PASS 計數，忽略後續 HOLD；grounded_progress 更會把沒有 key、未知 key 或重複的 PASS 算入總數。研究 inventory 及繁體中文 dashboard 直接採用來源 passed/total，空 checks 配上 passed=7 也會顯示7/7；inventory 更會移除 QUALITY_GATES_INCOMPLETE。這些是描述進度錯誤，原有正式推薦沒有被開啟。

四個出口改用 recommendation_readiness.quality_gate_states 的同一套七個固定 key：必須恰有一筆、state 是 PASS/PARTIAL/HOLD 的字串；缺漏、非法型別或重複（包括 PASS/PASS）均為 HOLD，未知 key 不計數。來源 aggregate 不能取代逐項檢查，總數固定7。inventory 原有數值型別、上下界及300樣本要求的拒絕檢查保留。

公開 JSON 新增 quality_gates_remaining 及七個 quality_gate_states；首頁列出香港繁體中文逐項狀態及未達標數目。renderer 由逐項狀態重算，不能用傳入的假 aggregate 改成7/7。這些狀態仍只是來源檢查報告，不是可信認證或正式推薦審批；過期警告照舊保留。

## 驗收

修改前先執行新增回歸，重現 public 1/7、grounded 3或4/7、inventory/dashboard 7/7 的錯誤；改後通過。原正例 fixture 補上真實固定 key，不降低預期或刪去舊安全檢查。

- compileall ops；1,750 ops tests＋150 top tests＝1,900，全數通過。
- 新增8項測試方法，含重複兩種次序、重複PASS、未知／缺key、非法state/checks、全七項唯一PASS、偽aggregate及逐項顯示。
- 真正 subprocess 驗證 inventory、dashboard 兩個絕對路徑 script 及兩個 ops.* package CLI：清空 PYTHONPATH，在臨時目錄執行 script，不靠測試插入搜尋路徑掩蓋載入錯誤。
- 獨立助理覆核及GitHub CI／發布讀回另記於對應 PR；未完成部署前不能稱網站已更新。

## 最新資料差距與界線

離線核對來源 quality 時刻24日03:55:46.570892Z：四個出口一致1/7，仍有6項未達標（5 PARTIAL、1 HOLD）。公開readiness04:20:08.947033Z、cohort04:18:53.515707Z仍是48未認證研究、0認證／欠300、3已記錄週非合資格週、0聯賽達40；38四方同案封存、11完場待配對。以上不是本次新採集或認證樣本。

六項未達標是賽事身份／實際開波時間、來源時間配額授權、亞洲盤大小球雙邊完整性、跨來源博彩公司去重、完整賽前封存、樣本外校準。與四大正式阻礙（可信前瞻結算、獨立校準、可成交價／正EV、最後人工審批）重疊，不相加成10項。#274仍缺特定用途及採集/upstream證據、真正獨立來源、權威身份橋接、actual kickoff/regulation FT及可信admission驗證器。

本次只修進度統計及顯示，沒有更改採集排程、免費配額、模型／權重、來源政策、舊seal／ledger、300場／12合資格週／4聯賽各40及獨立四模型1000門檻。沒有額外provider GET；既有受影響CI按原流程可能採集資料。production_recommendations=DISABLED、HOLD、0正式推薦不變，未證實提高預測。

現有自動維護任務按用戶指示每5小時執行，與此處既有GitHub工作排程不同；不要把排程配置成功當成每輪工作已成功執行。
