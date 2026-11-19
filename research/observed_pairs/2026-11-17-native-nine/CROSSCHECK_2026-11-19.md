# 德甲第 9 輪賽果交叉核對

2026 年 11 月 19 日 11:54:51 UTC，足球賽果連接器回傳 11 月 6 至 8 日德甲第 9 輪全部 9 場賽事。**9 場同 OpenLigaDB 原件嘅 90 分鐘比分完全一致，0 場有分歧。** 德甲官網公佈嘅比分同官方賽程所列 UTC 開波時間亦逐場吻合。[德甲賽果](https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/9) · [官方賽程 PDF](https://products.bundesliga.com/fixtures/export/pdf?league%5B0%5D=1d570dd9-b10b-44de-9f64-8c91e56bf168&matchday%5B0%5D=9&season=b2f90c16-d6ef-40b1-a974-e6b1bf102c2a)

本次用德甲聯賽、精確 UTC 開波時間及有方向嘅主客隊作一對一配對，沿用 `ops.team_identity` 嘅聯賽別名。雙方各有 9 個唯一賽事 ID。配對完成後先比較比分，並核對連接器逐場標記 `FINISHED`、`REGULAR`。上一輪簽封對應嘅 9 個預測個案及概率沿用原值。[原始證據收據](receipt.json)

私人 CSV 保留原賽前概率、兩邊賽事 ID、開波時間及比分。離線驗證通過 9 筆逐場配對、唯一性、全場期間及 CSV 讀回。CSV SHA-256 為 `d1463f7c3b64490f065c215ebc8e02a9434f3e9eb04347649ae6adbd0cabf2c3`，私人核對報告 SHA-256 為 `03f01220b9da06f2ebd3ee2e7abb5e02746a1625a72f52809b4d7416ac082d31`。公開記錄只含核對結果同引用連結。

OpenLigaDB 說明資料由用戶輸入，仍欠呢 9 場逐場採集來源嘅證據。連接器回應亦未交代逐場上游，官方賽程提供嘅係預定開波時間。正式納入仍欠符合政策嘅獨立賽果來源及實際開波證據。正式認證樣本 **0**，HOLD／DISABLED，正 EV 未獲驗證。[OpenLigaDB 資料來源說明](https://www.openligadb.de/en/license) · [賽果來源政策](../../../ops/policies/result_sources_v1.json)
