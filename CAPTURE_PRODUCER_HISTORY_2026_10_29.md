# 歷史原件：逐一驗證producer，避免無關子工作連鎖阻塞

29日自然run `40806106414/1` 的controlled-case-intake失敗，但同一次shadow-daily、attest_openliga_capture、verify_openliga_capture、archive_openliga_capture全部成功。原件及簽署包已保留。較後實測run `40847355133/1` 的controlled入口已成功，D歷史重播卻在準備階段回報 `UNTRUSTED_CAPTURE_RUN_METADATA`：歷史讀取器要求舊run整體success，因此無關consumer的舊失敗會永久阻塞後續歷史。

這次不刪除／跳過舊原件，不用最新快照替代，也不把舊parent改稱成功。改為逐次讀取authenticated GitHub exact-attempt run及jobs metadata，明確驗證產生原件的工作鏈。

## 固定來源判準

- 歷史parent必須completed，conclusion只允許success或failure；cancelled、timed_out、未知／缺欄位、queued／in_progress仍拒絕。
- repo／head_repo數字ID及full_name、run／attempt型別、main branch、workflow path／ID、schedule或workflow_dispatch事件、40位source SHA全部沿用原嚴格核對。
- **不論parent是否success**，再讀同一attempt的 `/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100&page=1`。total_count必須是正整數、最多100，且與完整jobs長度完全一致；截頁、截斷或多頁需要不能靜默接受。
- 所有job row均須唯一正整數job ID，同一run／attempt／source SHA、main branch及精確run_url。四個固定producer名稱各只能出現一次，且每個都completed/success：shadow-daily、attest_openliga_capture、verify_openliga_capture、archive_openliga_capture。失敗／跳過／缺少／重複／錯身份的producer全部拒絕，不能由caller揀其他job。
- 每個API回應有30秒timeout及2MiB接受上限，錯誤只用固定碼，不轉印stdout／stderr。大小在gh subprocess回傳後核對，不宣稱是串流記憶體上限。

metadata檢查本身不驗簽，也不認證publisher或賽果。之後仍由既有replay在同次執行fresh重驗每份capture的簽署、source／workflow／run／attempt、原件bytes、manifest及時序。固定baseline／歷史範圍／31+current上限、完整預先盤點、同場cohort／去重／衝突處理均保持；有任何無效原件仍整批HOLD。

## 驗收與持續運作

保留真實failed parent、四個producer皆成功的authenticated metadata作正向素材；固定baseline `40258192078/1` 的相同四工作鏈亦已確認。負例涵蓋parent狀態、API錯誤、每個producer失敗／缺失／重複、job清單截斷、跨run／attempt／SHA及型別錯誤，不改其他封存／簽署／評分預期。

此檔改動屬flat ops程式，私人Drive broker的外部code pins必須隨精確覆核版本更新。保留舊v1配置供舊source批次，新增v2配置並在私人registry登記；每份run用已登記且全部source pins相符的配置，在隔離source worktree驗證後才執行。identity、public recipient及金鑰版本不因程式更新而更換。只更新現有五小時任務的足球配置指引，其他指示、金融全文及排程保留。

相關CI及獨立覆核通過後，另外驗收真實daily workflow：舊failed parent的原件能按四producer證據保留，仍經fresh簽署／內容重驗；整條新流程必須如實報告每個job結果，不能用單一成功child冒充全綠。

這是受控原件保存與研究重播的來源鏈，不是獨立採集、實際開波或法定時間FT的認證。D固定cohort及封存A／B／C不改；來源／正式資格flags保持false、certified=0、HOLD／DISABLED。未證實能提高預測，足量前瞻樣本及可信正向admission仍須完成。
