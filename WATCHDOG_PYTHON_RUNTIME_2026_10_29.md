# 網站監控固定 Python 3.12

2026-10-29 的網站監控 run `40940594833/1`（來源 `7091ec706409357abf7f0ffadd8808628e03abd5`）在單元測試階段失敗，公開網站檢查因此未執行。該 runner 已使用 Ubuntu 26.04／Python 3.14；核心回歸及四模型流程則明確使用 Python 3.12。

失敗測試 `test_api_failures_and_malformed_context_do_not_use_saved_success` 提供 30,000 層、60,001 bytes 的 JSON array。Python 3.12 的 decoder 會拒絕過深輸入；該 Python 3.14 runner 解碼後由既有根物件檢查拒絕，產生另一個安全錯誤代碼。兩條路徑都拒絕輸入，沒有接受異常 metadata，但測試依賴未指定的 runner Python 版本而阻斷監控。

本次只在監控 workflow 加入與核心回歸相同、固定 commit 的 `actions/setup-python`，明確選擇 Python 3.12。既有測試、錯誤代碼、metadata 驗證、監控新鮮度規則、通知及排程全部保留；沒有更改 flat `ops` 程式，所以私人原件 broker 的來源版本 registry 不需變動。

驗收包括既有正常／異常 context 測試、完整 ops 測試、compile、根目錄回歸、獨立精確來源覆核及相關 hosted CI。合併後另核對真正 watchdog 的 Python 設定、單元測試及公開網站檢查三個步驟。若公開盤口因保留配額而過期，網站檢查仍應報 `DERIVED_MARKET_DATA_STALE`；修復測試環境並不代表所有健康閘門通過。

- 已實際修改：監控 Python 版本設定。
- 測試通過：以當次 PR／合併驗收記錄為準，不把程式測試當作賽果認證。
- 需外部資料／授權：這項修復不需要新 API；正式推薦仍欠可信賽果、可執行盤口及前瞻校準證據。
- 未證實能提高預測：本次是監控可靠性修復；正式推薦維持 `DISABLED／HOLD`。
