# 來源政策及逐場原件審計｜2026-10-19

2026-10-20接續：[原站擷取鏈v2](INDEX_ORIGIN_CHAIN_2026_10_20.md)補上新原件的拒絕轉址／final URL／逐次時間驗證；本文件所述缺final URL適用舊v1，舊原件不會補寫。獨立來源與賽果資格仍未完成。

關聯：#274（#111子工單）。本次補上可信驗證鏈的來源政策／缺項審計及舊觀察升格防護；**尚未完成獨立賽果認證或正式推薦資格**。

## 已修正的實際問題

舊 `result_consensus_gate`／`shadow_verified_adapter` 可根據 caller 提供的兩個 provider／group、網址及64字元雜湊輸出 `VERIFIED`，進入四模型評分。它們沒有重新核對原件或認證來源上游；全域正式推薦一直有 HOLD 保護。本次先以失敗測試重現，再將一致聲明保留為 `AGREED_UNVERIFIED`，舊評分介面 `verified_record` 不再接受這些輸入。caller 的 true 旗號、分組、網址或 hash 都不能建立認證結果。

`two_source_ft_evidence` 的 `verified_records`／`two_source_verified_count` 維持空／0；一致觀察改列 `observation_records`／`observation_consensus_count`。統一 manifest 接納未認證一致數作診斷，拒絕舊 JSON 偽認證及觀察攜帶 true 評分旗號。四模型日報的這條輸入路徑維持零認證樣本，不改任何歷史封存或原模型。

## 可重驗輸入／輸出

新增 `ops/trusted_result_evidence.py`，只接受原始 `ndr-capture.tar`、`capture.sigstore.json` 及可信運行 context；每次呼叫既有 capture audit 真正執行 `gh attestation verify`。重新讀取兩份原件後，比對該次驗證的 tar／bundle SHA，防止驗證後換檔；再使用相同嚴格 canonical tar／HTML 重播器。

固定政策 `ops/policies/result_sources_v1.json` 的 schema／ID／SHA 一併核對，沒有 caller policy 路徑或 group 覆寫。NDR、DFB、OpenLigaDB、OpenFootball 特定德甲2026–27／90分鐘賽果獨立採集證據仍未齊，政策均 UNKNOWN。官方 imprint 的一般內容供應聲明只作發現線索，不能推定特定比分資料同源或獨立；政策不授權新抓取或公開轉發原件。

每場輸出固定 NDR 賽事／主客球隊 ID、賽季／本地日期、顯示比分、Ende／90分鐘補時事件、detail 原件 SHA、記錄擷取時間及可信 Rekor 上界。分欄列明：

- 受控擷取／重播成功與同來源顯示身份吻合。
- index 缺 final URL 擷取鏈；不能補寫舊原件或由 detail 網址反推 index 身份。
- 跨來源映射、實際開波及上游獨立性 UNKNOWN；預定／實際開波 UTC 均不補推。
- 90分鐘賽果仍 UNVERIFIED，未連結獲認證賽前預測；獨立結果／評分／正式推薦旗號一律 false。

coverage 分開列出列表已接受、detail 已嘗試、已得到顯示觀察、仍未覆蓋的固定 ID；抓取／解析失敗亦列為未覆蓋。目前仍是首3場有界取樣，尚未有輪換，不假稱覆蓋完整。

## 執行及發布

需要支援 `gh attestation verify` 的 GitHub CLI；無工具或驗證失敗時拒絕。只新建既有父目錄內、proof 以外的獨立衍生檔；拒絕覆寫、別名及符號連結。

```bash
python -m ops.trusted_result_evidence --proof /tmp/ndr-proof \
  --source-sha 4267459eb737276ea919aff3b29cd712b6aa1480 \
  --workflow-sha 4267459eb737276ea919aff3b29cd712b6aa1480 \
  --run-id 39270352020 --attempt 1 \
  --capture-audit-output /tmp/capture-audit-new.json \
  --output /tmp/result-evidence-new.json
```

上例 context 必須配合該次原件；新運行必須使用其自身可信 context。每日唯讀驗證 job 呼叫新 CLI，保留原 capture audit artifact，另增 `ndr-trusted-result-evidence`。永久封存仍只保存兩份原件；沒有新增足球來源/API請求。

## 驗收及尚欠證據

本地 compile、完整1,449項測試、73項相關測試通過；其中25項新原件／政策／CLI測試包含換檔、saved verification偽旗號、非法政策、擷取失敗、零觀察及輸出路徑反例。本地 crypto boundary 替身只測程式行為，真正新CLI簽章與原件重播須以合併後 main 原生運行驗收。

`audit_completed=true` 只表示缺項審計完成。全套 readiness 可信證據驗證器仍未完成，#274保留未完成狀態，仍需可核證來源上游、原站擷取鏈、跨來源固定身份、實際開波／獨立90分鐘賽果及前瞻預測連結。之後另須足夠同場前瞻樣本、校準、相對市場優勢、不確定性及實價風控；不得調低300場／12週等門檻。

正式推薦仍 `HOLD／DISABLED`，本次沒有增加已認證樣本，未證實提高命中率或盈利。
