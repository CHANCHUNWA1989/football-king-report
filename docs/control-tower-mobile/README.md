# AI 研究控制塔 v7｜手機版互動介面

研究用途，**只讀、不可落注、不可交易、不可自行發布**。

## 已交付

- [`index.html`](./index.html)：一個獨立 HTML，唔依賴 CDN 或第三方 JS。支援 iPhone Safari／Android Chrome 的響應式介面。
- 主導航：總覽、模組、GitHub、風控、設定。
- 四個模組：足球王者、KPL、籃球 Elo、量化研究。私人倉庫只有名稱與資訊性連結，不向佢哋發出 API 請求。
- 按鈕可手動對 **公開** GitHub API 進行唯讀同步：open PR、main SHA／protected flag、指定手機版 PR #416 的精確 HEAD check-runs，以及 #405 / #409 / #412 review 提交數。每次呼叫有 timeout，缺失或失敗必須顯示「未核實」。`8/8` 係精確 SHA **核實快照**，絕非未來所有 CI 已通過。
- 公開網站三份 JSON：`status.json`、`quality.json`、`production_gate.json`。只讀核對；無可信來源綁定、過期資料、資訊不足時一律 HOLD。即使網站自報 SHA 一致亦不代表第三方認證。
- 風險可展開；淺色模式、減少動畫、本地 JSON 匯出、複製摘要。
- 一切動作繼續 `release_authorized=false`、`live_execution_allowed=false`、`production_recommendations=DISABLED`；介面無寫入 GitHub、Pages、交易所或博彩 API 功能。

## 手機使用方式

1. 下載單檔 HTML，在支援執行 HTML／JavaScript 嘅瀏覽器或受信任的 HTTPS 靜態預覽服務開啟。
2. 若需真正 iPhone 「加入主畫面」網頁 App，先通過獨立審核，再將靜態檔案託管於經批准嘅 HTTPS 網址；**本 Draft PR 不會部署**，亦唔係已可安裝之 PWA。
3. 點選「模組」瀏覽研究線；點「GitHub」後手動同步。所有資料帶明確來源及「非實時」界線。
4. 網絡故障／GitHub API 匿名限額／CORS 禁止時顯示「未核實」，唔使用舊結果冒充本次成功。
5. 介面所示安全閘門由已驗證 GitHub 歷史快照和本地邏輯呈現。**瀏覽器本地 UI 不具有解鎖部署權限**。

## 測試與限制

- 瀏覽器 Playwright Chromium 手機視口 `320 / 375 / 393 / 430 / 768px`：點擊導航、KPL／籃球模組、公開 API 成功 mock、評論審核待驗證、網站 HOLD、主題切換；五個尺寸無頁面腳本錯誤或橫向溢出。
- 安全預設：僅同步成功可刷新該項狀態；未知／失敗會標示「未核實」，頁面全程 HOLD。
- Chrome Chromium 測試非真正 Safari 實機認證；Safari PWA 添加主畫面及實際私有網站存取未驗證。
- PR #405 / #409 / #412 屬控制塔研究，非 KPL 或量化新功能。手機視覺稿中曾出現嘅 PR 名稱唔應該用作真實系統名稱。
- 未包含自動後台通知、正式 GitHub Pages 部署、私人倉庫自動登入、精確認證來源或賭博／券商執行功能。

## 審核

本手機版 Draft PR 堆疊喺 #412 → #409 → #405，與 `main` 分支隔離。獨立人員審核、主分支保護、正規合併與公開版本回讀係正式網站驗收前置要求；缺一維持 HOLD。

## V8 附加修補（仍是 Draft／研究用）

- 首次開啟頁面時，main SHA、main 保護狀態、CI 指標全部顯示「未核實」，不使用歷史快照中的綠燈冒充當前狀態。
- 手動同步後才核對 PR #416 目前 HEAD 的 check-runs；來源不能取得、HEAD 不一致或部分結果缺失時繼續 UNVERIFIED/HOLD。已存在的 #412 仍顯示為研究依賴分支，不再被當作手機版最新 CI。
- 網站 JSON 的 `source_commit_sha` 只可以跟「本次開頁期間已成功讀取」的 GitHub main SHA 進行表面比對；歷史儲存值不得作為驗證來源。即使 SHA 相同亦無法證明獨立部署認證，因此整體發布仍 HOLD。
- 新增 `ops/tests/test_mobile_control_tower_v8.py` 的離線防回歸測試；須通過 GitHub 最新 HEAD CI、獨立審核與手機 Safari 實機測試後才可考慮合併。
- 這個 V8 修補只在基於 #416 的研究分支進行，**不寫 main、不部署 Pages、不啟用自動交易或投注**。
