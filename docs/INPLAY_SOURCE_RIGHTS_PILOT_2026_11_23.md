# 足球王者｜首個真實即場資料試點：來源授權與覆蓋准入（2026-11-23 HKT）

## 為何今次唔再接入一個未授權「即場 API」

已提交的研究 Draft #544 → #547 → #550 → #553，可以核對操作者聲稱的比分/盤口/圖片時刻、保留原始 bytes，並以真正本地測試 TSA 驗證整份檔案的 SHA256+nonce。但上述流程仍缺「**合法可用的來源原件**」、「**外部真實 TSA**」及「**當時已捕捉並固定的模型輸出**」，不可用已完成的 2026-11-23 長野 vs 浦和賽果倒填。今次改為獨立、直接基於 main 的 no-network 准入守門程式，唔連動上游 Draft、唔耗用現有免費 API credit。

## 2026-11-23 核查政策（只係文件現況，唔係法律意見或正式合約）

| 供應商 | 已可核實的公開資料 | 本專案未獲得的權利/資格 |
| --- | --- | --- |
| WE League Official | <https://weleague.jp/legal/> 網站條款指官方網站內容/數據有權利限制，未經許可不可任意重用／複製 | 未有官方書面資料接入/自動擷取/存檔及重用權限，亦未有可認證 source-native 即場事件 feed |
| FotMob | <https://www.fotmob.com/tos.txt> 2026-10-22 版明言未經明確書面同意不得自動擷取或系統性資料檢索 | 未取得書面授權；**唔可直接用非官方 API 或爬蟲** |
| HKJC | <https://www.hkjc.com/en-us/disclaimer> 官方資料的網站免責及第三方性質聲明 | 未核實任何可供本專案自動獲取「讓球主客和」即場價格之授權端點、競賽/市場 ID、可成交性證據。單張手機截圖不是授權來源 |
| The Odds API v4 | <https://the-odds-api.com/terms-and-conditions.html> 允許研究分析及部分存檔/展示用途，禁止轉售為獨立 raw feed；<https://the-odds-api.com/sports-odds-data/sports-apis.html> 列出日本 J League `soccer_japan_j_league` | **J League 不等於 WE League**。未證實 WE League 及 HKJC 讓球主客和市場覆蓋，更未證實此帳戶有相關即場/market entitlements；API 共識賠率不是 HKJC 可成交報價 |
| FreeTSA | <https://www.freetsa.org/freetsa.html> 公開 RFC3161、每 IP 每秒最多一個請求、盡力運作無 SLA；<https://freetsa.org/index_en.php> 現行 CA/TSA 憑證及指紋 | **尚未真正簽發和獨立核實本案 token**；未核對 pinned CA、issuer/policy/revocation/服務時間質素。不能把 local self-issued test CA 當可信第三方 |

## 本 PR 的可執行改動

`ops/inplay_source_rights_preflight.py` 是純 Python、read-only 的來源准入與覆蓋審核。

```bash
python ops/inplay_source_rights_preflight.py
# JSON 會列明每一項來源阻塞及不可執行原因，退出碼 2
```

- 五個角色：賽事身份（fixture）、兩個不同賽事更新來源（score_primary／score_secondary）、市場（market）、第三方時間戳（timestamp）。
- 只接受已在程式政策中固定的 provider ID、支援角色、賽事 scope、及讓球市場類型。必須區分 HKJC `HKJC_THREE_WAY_HANDICAP` 同 `ASIAN_HANDICAP`，絕不以日本 J League 覆蓋冒充日本女子 WE League 覆蓋。
- **明確拒絕** caller 嘅 `approved=true`、未登記 provider、不屬於該角色的提供商、同源兩次冒充雙源。
- 即使兩個 provider 名稱不同，亦未能證實其真實上游來源獨立。全部輸出 `status=HOLD`、`decision=HOLD`、`allow_network_collection=false`、`allow_automatic_scraping=false`、`allow_raw_data_publication=false`、`production_recommendations=DISABLED`、`model_scoring_eligible=false`、`certified_forward_samples=0`。
- 無網絡 call、無 TSA request、無 API Key、無新第三方原始數據下載、無更動資料 pipeline 與正式推薦。

`ops/tests/test_inplay_source_rights_preflight.py`：17 項合成測試，驗證 5 角色被正確隔離、三向讓球型別、日本兩種聯賽不可偷換、FotMob 不可自動使用、第三方 TSA 未核對、假授權／未知供應商／同源冒充／role mismatch／null/boolean input 都 fail closed。

## 要真正解除阻塞，必須取得的外部證據（目前無）

1. **資料來源**：與供應商權利人明確核准的用途範圍（私用研究、原件留存/再展示、程式讀取、聯賽/市場 coverage）及可信的賽事 ID。任何寄來的文件都需要獨立核實簽發者，唔能夠在 JSON 自己填 `approved`。
2. **雙源時效**：賽前 fixture ID 封存；賽中兩個**實際獨立** publishers 嘅原始比分事件、紅牌、上游 update UTC 及當時讀取原件；有誤差要拒絕。
3. **市場**：有合法授權嘅真正 HKJC 三向讓球盤（或清楚標示不同市場），原本 wager receipt/available quote window 及更新 timestamp。未有就不計可實行 EV。
4. **TSA**：只對已經在當時採集好的 bytes digest 發送；實際 TSA token、可信 pin / issuer、policy OID、revocation/鏈時效，獨立查核。FreeTSA 最多 1req/s/IP，無 SLA，不能長期佔用公開服務；用戶亦可另選有 SLA 供應商。
5. **評分**：相同時刻封存模型參數及結果，事後以雙來源核實 90 分鐘賽果，嚴格前瞻及樣本外測試；不能將今天的歷史比分倒填。

## CI 及 merge boundary

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

本 PR 的 role-registry **不提供授權升格功能**。真正有書面授權、現場 coverage、有可信外部 timestamp，必須另外經獨立人工 code/contract review，再加入限定 scope 的連接器。拒絕用 GitHub Actions 免費 key 自動開始抓取未核准網站。

所有研究與 production 保持 `HOLD / DISABLED`。無任何認證前瞻樣本、已核實正 EV 或準確率改善。
