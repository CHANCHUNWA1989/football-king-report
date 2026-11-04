# 日職 PropLine 限定既有四個博彩公司範圍

2026-11-04 的 J1 排程 `41760255276` 雖完成並封存摘要，PropLine 本身仍是 `HOLD / UPSTREAM_OVERSIZE`、只嘗試一次、零合資格市場。整體 `RESEARCH_ONLY` 來自另一供應商，不能當作 PropLine 已接通。

J1 bulk URL 沒有指定 bookmakers，而現有六聯賽已使用 `pinnacle,bovada,fanduel,draftkings`。已保存的官方 `/docs#odds` 合約說明逗號分隔的 `bookmakers` 可限制回應，省略即取全部。本次只將同一篩選加入 J1 固定 URL。

保留原本單次請求、1,700,000-byte 上限、15秒 timeout、header 認證及所有身份／新鮮度／共識／發布限制。沒有新增重試、未篩選 fallback、原始盤口保存或付費端點。正向測試檢查真正 `fetch()` 的固定 URL、header、一次 bounded read 及刪敏結果；負向測試仍要求過大回應輸出 HOLD，不重試。

官方文件證據擷取於10月30日，未聲稱11月4日已重新抓取。修復前的最新去敏感狀態、原排程及封存提交已核對；修復後仍須真實排程驗收，才能確認 filtered response 大小及市場覆蓋。單元測試成功本身不證明實際 API 已解阻。

- 已實際修改：J1 PropLine 固定請求範圍及兩項回歸測試。
- 測試通過：以當次完整回歸、相關 hosted CI 及獨立精確來源覆核為準。
- 需外部資料／授權：現有免費用途沿用；實際可用市場與來源證據仍須驗證，不擴大 raw retention。
- 未證實能提高預測：此修復不改模型、封存預測、校準、配額或正式資格；維持 `DISABLED／HOLD`。
