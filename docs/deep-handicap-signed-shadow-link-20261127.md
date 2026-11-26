# 第十九階段：已簽署影子預測與深盤重構連結

現有 forecast_provenance_audit 固定 main 的 football-king-iphone workflow、三個subject、GitHub證書及Rekor時間。不能把該簽署挪作DHE候選或私人盤口的簽署。新增私有離線重構入口，真正呼叫既有 verifier（驗證器本身可需要 gh／網絡），不接受保存的驗證JSON；固定外部提供的source/workflow SHA與run/attempt，重新讀取shadow.json核對已驗證subject SHA256，要求可信影子見證不晚於DHE聲稱cutoff，並使用原三份衍生輸入pins重構候選，維持開波前10分鐘緩衝。沒有發布任何報價，不新增API供應商調用、不修改簽署流程或封存。該時間規則可能拒絕早於影子簽署的有效候選；刻意保守。簽署只證明影子文件的受控見證，不證明DHE候選或報價的存在時間；實際開波、來源、結果、前瞻資格仍未認證。此入口仍未接駁實際私有檔案或部署排程。

四組合成測試：模擬已驗證簽署結果、真正驗證器拒絕缺原件的假保存報告（無網絡）、晚見證／更換原件、簽署失敗／錯誤pin。沒有執行真實DHE簽署驗證，不宣稱真實來源證據。HOLD/DISABLED、0真前瞻。第十八階段10項CI成功；新CI待驗收。