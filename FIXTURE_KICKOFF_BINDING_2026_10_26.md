# 市場配對：核對明確提供的開波時間

## 已重現的問題

`verified_market_pipeline` 原本只按來源 event ID、聯賽、主客隊配對。
即使個案明確提供 `fixture.kickoff_utc` 為翌日、無效文字、無時區時間、
布林值或 null，仍可把另一個開波時間的報價列為已配對研究報價，並在
`integrated_market_consensus` 形成研究共識及 `market_identity=True`。
正式推薦雖仍 HOLD，身份及時間診斷已失真；延賽或錯填時間不應默默通過。

## 修正及相容行為

如 `fixture` **含有** `kickoff_utc` 欄位，使用既有 UTC parser 驗證有時區的時間，
再要求與報價的 `kickoff_utc` 為完全相同時刻。UTC 與 UTC+8 的等價表示可配對；
相差一微秒亦不會被四捨五入成同場時間。無效、無時區、null、布林值及 UTC
轉換溢位均不能退回缺欄位路徑。

如時間不符或無效，清除對個案已配對的研究報價及市場認證輸入，不會沿用個案
自行宣稱的 `validated_by_market_quote_gate` 或可執行標記。原始報價 gate 的
去明細診斷可保留；它只說明來源結構通過，不代表已配對到此個案。
身份缺失而提早返回時亦清除自填 market，避免沒有配對報價卻顯示市場已驗證。

未提供此欄位的舊研究個案保留原有診斷契約，但兩個 consumer 都明確輸出狀態：

| `fixture_kickoff_binding` | 含義 |
| --- | --- |
| `MATCHED` | 有有效指定時間，且有同 native event ID、同 UTC 開波時刻的報價 |
| `NO_MATCHING_QUOTES` | 有有效指定時間，但沒有符合全部配對條件的報價 |
| `INVALID` | 明確提供的開波時間無效 |
| `NOT_PROVIDED_LEGACY_RESEARCH_ONLY` | 沒有提供開波時間，沿用舊研究診斷，沒有完成時間綁定 |

本輪只補上既有 pipeline → integrated consensus 的配對條件及診斷欄位。
沒有擴展採集、API 請求、排程或更改新鮮度／phase／盤口線規則。

## 驗收及未完成部分

先以原碼重現錯配，再測 UTC／UTC+8 等價、延賽、一微秒差異、無效／無時區／
溢位／null 時間、舊研究相容、跨來源 ID 不可混用、自填 market 標記不能通過及
原始輸入不改寫。經實際整合 consumer 驗證無配對時不能生成共識。
測試皆為合成離線案例，不計入真實認證樣本；完整測試、獨立覆核、CI 及部署
以本輪 PR 實際紀錄為準。

兩個時間相同只證明此次指定資料的一致性，不證明來源獨立、實際開波、原價可成交、
模型校準或90分鐘賽果可信。可信賽果 admission、認證 cohort 統計、私人賽前至
賽後原件保存及前瞻校準仍未完成，仍需真實來源證據及既有私人保存位置。
沒有改動原封存預測、權重、賽果、結果來源政策或正式門檻。
正式推薦維持 HOLD／DISABLED；未證實預測或盈利能力改善。
