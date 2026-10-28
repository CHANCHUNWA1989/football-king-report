# 私人市場回應原件：同次捕捉與重播

原collector只留下篩選、正規化後的h2h rows，不能還原完整回應body。本次補上**既有同一次HTTP回應的原始body bytes與有限receipt**，以及私人目錄封裝／讀回；不新增供應商請求、市場種類或額度支出路徑。

## 已接入範圍

`odds_market.retrieve()`新增可選capture session。只有私人workflow啟用：先核對固定catalog／六聯賽h2h endpoint及四個固定參數，才發原有GET；要求成功回應及final URL與原request一致，拒絕觀察到的redirect。既有response只read一次，原bytes不重排、不重寫JSON。完成時刻在讀取／關閉回應後立即取得，先於保存寫檔；私人quote binding沿用同一個完成UTC，重播才能逐row一致。

receipt僅保存固定endpoint path、非密鑰參數、provider quota counters、開始／完成UTC、原件SHA及大小、工作流程source SHA／run／attempt。完整URL、headers及API密鑰不落檔；寫入前檢查raw bytes、decoded JSON keys／string values及serialized receipt是否包含當次key；JSON字串及key另外最多兩次percent解碼檢查，涵蓋普通、部分及雙層URL編碼，原bytes保持不變。這是有界防護，不聲稱識別任意未知編碼的秘密。錯誤只輸出固定碼，不帶body／URL／exception文字。

新原件目錄放在`RUNNER_TEMP`、在checkout之外；新建0700，檔案0600及單連結regular file。拒絕symlink／FIFO／hardlink、已有目錄／檔案、git ancestor、觀察到的換件、損壞及額外項目。最多7個回應：1個catalog＋最多6個現有聯賽h2h，各body最多5MB。保留FD／inode及重讀檢查；標準POSIX同UID極短競態區間仍不能宣稱完全排除。

manifest最後寫入，逐檔SHA及固定context讀回。seal SHA經GITHUB_OUTPUT交予下一步作manifest pin；未簽署manifest只提供完整性及內部context核對，不能成為獨立可信證書。換錯context或pin、篡改body／receipt／manifest、缺檔及超限整批拒絕；capture失敗不重試其他聯賽，避免在新quota未知下多扣額。

私人workflow重播所有body，再以既有`bind_response()`及同一完成UTC重建quotes，與原collector的normalized rows按canonical JSON比對，保留bool／int／float區別並拒絕非有限數值。CLI只輸出safe counts／context／hash及HOLD。公開artifact仍只有原來兩個明確刪敏摘要檔；原件不加入artifact、cache、commit或Pages。

## 驗收及限制

正向測試保存含原始空白及benign percent編碼的bytes、catalog＋odds同次還原、逐quote一致、另一個Python process讀回、catalog-only QUOTA_GUARD及0額外GET。負向包括換件／連結／缺檔／錯pin／錯context／超限／密鑰raw、JSON escape及最多兩層percent編碼／來源轉址／公開附件allowlist／seal失敗及固定offline clock不可冒充live capture。測試資料及opener為明示合成fixture，不算真實provider認證。

若真實配額保護只允許catalog，雲端只能證明catalog body被捕捉及重播，不能聲稱已驗證真實odds原件路徑或新鮮報價。空pack／0quotes亦不算來源認證。後續自然／既有合法採集取得odds時，才可新增相應實物觀察。

**目前仍是臨時私人工作目錄，job完結後不保證保存。**沒有接通私人長期目的地、跨job／跨輪持久化、外部時間見證、publisher身份或獨立上游認證。git路徑及POSIX權限防護也不是遠端私隱／ACL審核。

`raw_source_authenticated`、`capture_time_authenticated`、`durable_archive_verified`保持false，0 certified、HOLD／DISABLED。此階段完成原件producer／private replay工程；可信正向結果admission、certified-only統計／校準、實際開波／90分鐘結果認證、可成交報價及足夠前瞻樣本仍未完成。現有API接駁及部分內部研究使用依據沒有被否定；測試通過不代表預測或盈利提高。
