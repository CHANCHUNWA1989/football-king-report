# 受控原件入口：當次run狀態重讀及安全診斷

2026-10-29自然run `40806106414/1` 的 `controlled-case-intake` job `123225700079` 失敗：單元測試、簽署capture附件下載均成功，Bind步驟的inline Python在line27發出bare AssertionError。該行只核對當次run rollup必須是in_progress或completed/success；原實物附件僅有selection.json，歷史forecast／case／paired pins正確，沒有保存API回應狀態。

因此只能確定是該狀態斷言拒絕，**不能斷言當時實際為queued或已證明是GitHub延遲**。較後同日08:10自然run `40840315245` 用未改程式已全部成功；本修正處理可重現的暫態狀態失敗及缺診斷問題，不聲稱當前服務仍全面中斷。

## 行為

daily workflow的同一inline script新增 `load_capture_run_context`。每一次authenticated `gh api`回應，均先嚴格重驗run／attempt、source SHA、main branch、workflow path／ID、schedule或workflow_dispatch事件、repo及head_repo固定ID／full_name。錯誤身份立即拒絕，不能等另一個好回應取代。

當次run只接受in_progress且conclusion=null，或completed/success。已驗相同身份的queued／pending／requested／waiting且conclusion=null，可以每兩秒重讀一次，最多五次；沒有取得合資格狀態便以固定碼失敗。歷史run仍只接受completed/success，不重讀queued。terminal failure／cancelled、未知或矛盾狀態、API失敗／超限／損壞JSON均拒絕，沒有saved-success fallback。

成功或失敗均新建 `capture-run-context.json`，只允許固定schema、預期run_id／attempt、白名單status／conclusion及整數attempted_reads六項。未知字串轉為INVALID，不保存任意metadata、URL、stdout／stderr、token或原件。原有diagnostic附件沿用既有JSON路徑，新增安全狀態檔供後續定位；已有檔案不覆寫。

原forecast／case／paired pins、四次fresh簽署驗證、原件／context重播、正規化比分規則及所有HOLD／certified=0閘門保持。沒有接受failed或queued代替成功，也沒有continue-on-error。

## 驗收範圍

新增九個methods，直接抽出實際workflow function作測試，涵蓋暫態→合資格、耗盡重讀、每項身份錯誤、歷史／terminal拒絕、API失敗、型別／輸入及診斷洩漏負例。這些是明示mock metadata，不是GitHub來源事實或正式認證。基線同一套測試因缺function失敗；另保留真實失敗log及selection附件。

沒有改動任何flat ops程式、私人Drive中轉workflow或public recipient，因此更新344的221個code pins及既有五小時broker設定仍相符。沒有新增足球供應商請求路徑或修改免費配額；合併後另驗當次自然／手動daily workflow的真實metadata及簽署／重播流程。

正式publisher／上游獨立、實際開波及法定時間FT仍未認證；本次不增加認證數、改sealedABC或證明預測提高。正式推薦維持HOLD／DISABLED。
