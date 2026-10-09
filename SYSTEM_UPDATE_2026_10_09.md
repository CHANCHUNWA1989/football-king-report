# 足球王者｜2026-10-09 程式安全更新與真實未完成事項

## 本次已實作（PR #33）

- `ops/independent_results.py`：免費賽果來源缺失／錯誤開賽時間時跳過該觀察，不再中止所有獨立賽果核對。
- `ops/market_pair.py`：逐條檢查市場報價時間；畸形時間資料不能令同場另一條有效紀錄的配對失敗；保留市場早於預測的嚴格檢查。
- `ops/odds_market.py`：拒絕畸形 bookmakers／markets／outcomes 欄位，避免外部免費市場結構變化導致整批採集崩潰。
- `ops/forward_validation.py`：封存市場基線不得早於預測超過 750 分鐘、舊樣本禁止布林真假冒充賽果；維持至少 300 樣本同獨立證據認證的評估邊界。
- `ops/market_archive_guard.py`：禁止未來市場擷取時間，以及擷取時超過八小時的舊報價，避免污染最新市場封存。
- `ops/source_publish_guard.py`：來源計數欄位、球隊名稱、賽事識別碼、賽事狀態須符合安全型別與長度。
- 新增/擴展相應合成測試案例，毋須使用 GitHub Secrets 或免費 API 配額。
- 新增 `.github/workflows/football-king-ci.yml`：PR/主分支改動均執行 ops 全套回歸測試、原本 V4.1 ZIP SHA-256 驗證、原本 app 測試，無任何供應商 Key。

## 已存在，沒有重覆申請或收費

- The Odds API、TheSportsDB、API-Football、football-data.org、Sportmonks、OpenFootball、OpenLigaDB、OpenFootAPI、StatsBomb Open Data、MET Norway、BSD 等已有接駁／研究層；不是全部已取得免費帳號配額或當季賽事授權。
- 免費資料來源只在明確容許的賽程、賽果、研究邊界使用。BSD 共識 1X2 不等於可執行的個別博彩公司價格。
- 研究方向 shortlist／低證據模型觀察與真正能下注正 EV 不同；正式投注仍為 `DISABLED`。

## 尚未解決（不可以假稱完成）

1. `FOOTBALL_DATA_ORG_TOKEN`、`OPENFOOT_API_KEY`、`BSD_FREE_API_TOKEN` 缺席時，需要用戶到各供應商申請免費 Key 再設定 GitHub Actions Secrets；程序不能自行代辦真人註冊或繞過授權。
2. API-Football 免費方案對目前賽季的存取限制，無法靠修改程式解決。
3. 免費市場限額不能等同額外實際可下注賠率；當配額不足，保留純模型低證據觀察，不偽造市場、EV、ROI、勝率。
4. 已封存市場價、樣本外穩定性、至少 300 個已結算有效比較、多聯賽覆蓋、概率校準、獨立賽果及可執行賠率仍需真實長期觀察驗證，不能用更多 API 取代。
5. GitHub 工作流程和 GitHub Pages 是否成功，應以合併後實際 workflow run／Pages 檢查為準；PR 提交不等於已部署。

## 驗證指令

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -v
# CI 會另外驗證釘選的 V4.1 ZIP 與 app/tests
```

**安全守則：** 從不將新 API 未驗證資料覆寫舊預測；維持賽前封存、資料時點核對、免費用量護欄、推薦 HOLD。