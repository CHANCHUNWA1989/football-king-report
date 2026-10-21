# 認證樣本數量的信任界線（工單 #301）

本輪修正資格進度計算，沒有完成可信賽果 admission，也沒有新增認證樣本或改動模型、評分、ledger、舊封存及正式推薦閘門。

## 已重現的問題

300個僅有基本身份／記錄開波及 `fixture_result_source_independently_verified=true` 的輸入，經 `grounded_progress`、公開 aggregate sanitizer、readiness inventory 到 unified manifest，曾被計成300個獨立認證，差額變0，缺樣本 blocker 消失。更少只需一個標記及 caller 傳入 `required=1`。原系統一直維持 DISABLED；問題是數量及門檻的信任界線，並非已解鎖投注。

PR275已保護另一條 FT／評分來源入口，本輪修正的是 readiness aggregate 分支，沒有重做舊解析／封存／來源ID功能。

## 修正後的規則

- 自報標記只保留為 `result_rows_marked_independently_verified`；不能當成 `independently_verified_result_cases` 或 `independently_verified_settlements`。
- 本流程尚無可信 admission，真正認證數維持0。新舊 aggregate 的正數都只能是來源聲稱，不能扣減認證差額。
- sanitizer 固定原有300場門檻；inventory／manifest 邊界拒絕任何非300或非整數的要求。原12個合格週、聯賽及其他證據門檻沒有改動。
- inventory 及 manifest 保留缺獨立認證樣本 blocker。manifest 加入實際認證數0，剩餘300；手機摘要亦拒絕 caller 偽造這三個數字。
- 網站原有 `marked` 及「假如通過獨立審計」條件式欄位保留其含義；另列實際認證數與差額。HTML不以來源聲稱或記錄日曆週當認證進度。
- 保留去重、類型、矛盾計數檢查及私人資料 allowlist；不輸出賽事身份、莊家或原始報價。

例如，合法形狀的300個未認證聲稱可被記錄為 claims300，但 certified0／remaining300。`required=1`、布林數字、錯誤類型及超過 archive 的矛盾數量不能減少門檻或認證差額。額外 hash、reviewer 名字或 caller 驗章旗號亦不構成證據。

## 仍未完成

#274仍需特定feed／賽季／90分鐘採集及用途原件、確實獨立第二來源、固定跨源fixture/team橋接、實際開波、獨立regulationFT及當次CLI重驗原預測連結。取得真實必要輸入後，才另行實作版本化 admission；不能把本輪固定0的保護改成相信來源標記。

本輪測試只驗證程式拒絕虛假資格進度，不證明命中率、概率校準、正EV或盈利改善。正式推薦維持 HOLD／DISABLED。
