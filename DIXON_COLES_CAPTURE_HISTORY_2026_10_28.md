# 固定D批次：跨日結果原件核對

舊每日復盤只提供當次capture；即使核心會隔離兩份原件之間的比分矛盾，前一日原件沒有交入時仍看不到修訂。本次補上有界歷史還原及每日交付，不改模型、權重、固定預測母體或正式認證政策。

## 選擇及還原

`ops/dixon_coles_capture_history.py`只看固定run範圍內**本次checkout實際保存**的OpenLigaDB capture。固定下限為已保存的`40258192078/1`（26Oct，早於固定D預測）；上限為輸入current run／attempt。按run／attempt納入所有現有檔案，不以比分、是否完場、命中或最新N份篩選。資料夾日期只作合法路徑核對，不用日期排除較後run。下限原件必須存在，重複run／attempt路徑視為含糊而拒絕。

先凍結整個目錄清單及數量，再讀取壓縮原件及查詢metadata。每份歷史只接受tar與bundle兩個gzip檔，限制壓縮／解壓大小、regular單連結檔案、拒絕symlink／FIFO／hardlink與觀察到的換件。tar按二進制還原，不誤當JSON；bundle仍須結構有效。所有候選原件預檢後，逐run／attempt重新查官方Actions API，核對repo ID／名稱、main、daily workflow ID／路徑、schedule或dispatch、成功完成及來源commit。bundle宣告及保存的audit JSON不能提供可信metadata。

歷史原件還原到新的獨占輸出目錄，沿用既有保留FD、manifest最後發布及只清理自有檔案的保護。當次capture仍原位供應；若其同run／attempt已封存，只有逐byte完全相同才去重，較舊attempt仍保留。缺檔、損壞、metadata失敗或衝突一律整批HOLD，不能跳過後改用最新一份。

最多31份歷史加1份當次，核心上限同步為32。超限整批拒絕，不截斷歷史；這是固定pilot的資源界線，長期擴展仍需另行設計。兩個獨立復盤job的逾時改為45分鐘，以容納最多31次歷史metadata、2次預測metadata及38次逐subject驗簽的最壞30秒限時；不增加供應商請求或排程。

## 復盤及驗收

核心先選固定預測cohort，再對manifest中**每份**capture重新驗簽及重播原tar。跨日身份、KO或完整FT比分有衝突便隔離，即使兩個比分的主和客方向相同。合成端到端測試實際經過gzip還原、metadata核對、獨占輸出及核心驗證：前日2:1／次日3:1一起交入為0評分、1隔離；僅交最新一份的舊行為會有1個未認證研究評分。測試CLI回應為明示mock，不能充當密碼學證據。

CI的真實驗簽入口固定用27Oct既有capture `40437105506/1`及26Oct歷史下限，來源commit由官方metadata核對；不再用早於pilot的24Oct capture測試歷史交付。當次CLI及tar原件仍需真正驗證，不能由單元測試的mock代替。

完整回歸另揭示舊controlled-case工作流程測試把其後所有job一起讀入，令新D job的獨立環境值覆蓋舊case值。本次只修正測試選取自己job的範圍，保留controlled-case原有24Oct來源摘要、run及安全預期，沒有放寬驗收。

## 範圍及未完成事項

這只保證納入固定範圍內**checkout中現有原件**，不能證明所有遠端執行或出版者歷史都已保存。缺失的中間capture、不在checkout中的新封存、未抓到的修訂及超過上限後的長期交付仍有範圍限制。`remote_history_completeness_verified=false`；沒有改稱完整來源歷史。平台標準POSIX極短same-UID競態限制仍如既有文件披露。

所有輸出維持HOLD／DISABLED、0 certified，不認證出版社身份、上游獨立、實際開波、常規90分鐘賽果、可成交報價、校準或模型優勢，不寫入正式或研究settled ledger。私人原件長期保存、可信正向admission及certified-only統計仍未完成。測試成功及修補跨日檢查不等於命中率或盈利提高。
