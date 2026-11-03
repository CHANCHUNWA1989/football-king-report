# KPL V19 — 全樣本預測封存驗證及授權期間修復（2026-11-03）

## 背景及主要審計結論
2026-11-03 北京WB對上海EDG.M錯判提醒：有研究模型、全部GitHub CI成功，**仍唔代表方向準確或KPL實戰校準已獲證實**。V17/V18提供Elo prequential回放、封存證據及來源權利*聲稱*格式檢查，但本次獨立審計找出兩個會使技術准入誤報通過的程式缺陷。

### 漏洞一：V18只核對測試集封存概率
原本 `audit_history_intake` 只拿 `report["test_forecasts"]` 同已封存研究概率逐局比對，訓練集嘅模型概率即使同真實Elo回播不一致，只要當地雜湊鏈及測試用簽章重新製作，技術准入仍可通過。此漏洞涉及「資料重算冒充賽前完整記錄」；即使結果用作訓練組，亦須保留真實、事前固定之研究預測證據。

**修復：** V17 `replay_elo_shadow` 額外回傳 `all_forecasts`，涵蓋完整封存母體內每局預測；V18強制要求筆數等於 `len(rows)`，每個 series/game 身份完全一致，並逐局比較預先封存機率與Elo prequential重算值（浮點容差1e-12）。缺任一局或更改訓練組概率，回傳 `SEALED_FORECAST_DISAGREES_WITH_ELO_REPLAY`，`technical_preflight_passed=False`。

### 漏洞二：合約權利檢查只核對第一局
V18過去僅確認聲稱的權利文件 `grant_expires_at` 晚於**最早** `forecast_at`。若資料集歷經幾個月，第二週起嘅賽事可能已超出聲稱授權期，原本格式檢查仍通過。

**修復：** 在原有授權文件完整性檢查之上，要求 `grant_expires_at >= max(row.forecast_at)`，兼顧最早及最晚一局研究預測。此條件仍僅核對**使用者提供的授權聲稱欄位**，程式唔會獨立驗證原權利人是否有簽約、是否容許再分發/商用及實際用途；`licence_independently_verified` 永遠 False。

## 回歸測試
測試更改：
- `ops/tests/test_kpl_v18_history_admission.py`：增加「中途失效之權利文件」、「有效期準確覆蓋最後一局」、「重新計算整條封存雜湊鏈及全部測試Ed25519簽章後，訓練局概率被篡改亦必須拒絕」3項測試。
- 合成V18封存fixture更新為**訓練＋測試全部真實Elo回放概率**，不再把訓練集偽裝成全0.5。
- `ops/tests/test_kpl_v17_elo_replay.py` 增加2項：完整16局輸出覆蓋；第一局0.5、後續只使用已公開賽果。

所有測試使用自建 synthetic BO7賽果及測試期臨時產生Ed25519金鑰；沒有真實KPL逐局資料、私鑰或供應者原始資料提交至GitHub。

## 來源調查（資料是否可用於真實準確率檢驗）
截至本輪再次搜尋，KPL非官方研究平台自述全歷史涵蓋2,901大場、11,138小局，但時間戳顯示更新至**2026-10-26 19:20**；且分鐘級歷史資料只有221/11,138局（平台自述2%），**不能**充當11月3日即時BP/經濟資料：
https://kpldata-site.hccccc01333.workers.dev/about

直播及第三方賽程可能延遲，同一時間存在0:0未開賽／已進行等互相矛盾畫面；其頁面狀態不能反推當時官方真實結果：
https://www.huya.com/kpl
https://arena.zswclub.com/hok/2026-kpl-grand-finals/schedule

官方KPL認證微博第三局戰報：https://3g.sina.com.cn/news/detail/5361256752220737.html
賽前/頭三局新聞不足構成完整、事前封存嘅BO7資料集。非官方BP整理項目之下載權限及原始賽事資料使用授權，仍待權利人另行核實：
https://github.com/Fire-Phoenixs/kpl-bp-dataset

本輪無下載／複製該資料集、無合法授權歷史BO7整套可證明事前預測記錄，仍**不能**報出真實KPL歷史模型命中率、可靠校準、正EV或即時預測優勢。

## 驗收及安全邊界
```sh
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v18_history_admission.py' -v
python -m unittest discover -s ops/tests -p 'test_kpl_v17_elo_replay.py' -v
python -m unittest discover -s ops/tests -q
```

PR #402（本輪）以 #400 為 base，依賴前置 Draft PR。需完整GitHub CI及獨立審核後方能合併，**不部署、不接通盤口或任何投注**，`HOLD / DISABLED` 不變。`all_forecasts` 只是根據聲稱資料時間嘅離線重播，並無密碼學認證之可信外部事前時間戳，亦不能單憑測試通過宣稱已修好真實預測方向。
