# 研究結算保留原預測已有的固定來源身份

原 archive loader 已檢查預測來源身份，但 `forward_validation.extend()` 的結算投影丟失這些欄位；direct-call 邊界及既有 sample validator 亦沒有延續同一檢查。合成重現顯示 event ID 與 typed match ID 互相矛盾的直接輸入仍能產生研究結算。尚未證明正常每日完整 archive 路徑曾因這個缺口重複計分。

現在新結算只複製原預測已有的身份 claim，並深拷貝該 metadata；保留 `UNAUTHENTICATED` 及 false 安全旗號。直接候選與既有 sample 同樣檢查選填身份。沒有 ID 的舊資料維持缺省，不從名字、日期、比分或較後來源回填。

結算前先檢查合法既有 sample 與候選的 scoped provider ID／fixture 綁定；同一來源 ID 被綁到不同 fixture 時整批拒絕，先於結果選擇及 pending／已結算跳過。UTC 等價表示正規化，偽造 direct key 不可污染其他候選；輸入 materialization 及綁定沿用既有容量限制。舊原件、模型概率與賽果不覆寫。

內部去重索引亦使用同一 UTC fixture 身份，避免 `Z` 與 `+00:00` 表示同一場而重複結算；保留輸出中原有 row／key 文本。同一 canonical 身份但內容矛盾的既有結算整批拒絕。只複製結算實際使用的候選欄位，不遞迴複製無關額外內容。

驗收涵蓋身份保存、深拷貝、錯 ID／偽造認證狀態拒絕、舊資料相容、跨批次 ID 重用、pending 候選衝突、輸入次序及等價 UTC。所有案例為合成程式行為測試，並非新認證賽果。

- 已實際修改：研究結算身份驗證與投影及回歸測試。
- 測試通過：以此 PR 的實際本機／hosted CI 及獨立精確來源覆核記錄為準。
- 需外部資料／授權：真正 positive admission、兩源權威與獨立性、actual kickoff、90分鐘賽果原件及 certified-only 統計仍未完成。
- 未證實能提高預測：這項修復保留可追蹤身份，不認證其真偽，不改 sealed 預測或正式資格；維持 `DISABLED／HOLD`。
