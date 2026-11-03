# KPL 第十八階段：真實資料准入、原件綁定及回測資格（2026-11-03）

> 本輪研究：PR #400（stacked on PR #399）。正式預測與投注保持 HOLD / DISABLED。沒有下載、鏡像或提交任何第三方真實KPL逐局資料。只使用合成自建原始JSON與測試用臨時Ed25519密鑰。

## 1. 最新證據與權利審計

- 2026年11月3日北京WB對上海EDG.M：KPL認證官方微博11月3日18:44、19:17、19:51分別發佈前三局戰報。公開頁：
  - G1 https://3g.sina.com.cn/news/detail/5361239930179321.html
  - G2 https://3g.sina.com.cn/news/detail/5361248166481423.html
  - G3 https://3g.sina.com.cn/news/detail/5361256752220737.html
- 維基百科該賽事2026年年度總決賽條目現列WB 4:2 EDG.M及G4–G6逐局勝方；本輪未取得G4–G6每局完整BP、逐分鐘可觀察數據及具可靠發布時間嘅官方完整結果檔。因此唔係一個合資格可事前回放的BO7樣本：
  https://zh.wikipedia.org/wiki/王者荣耀职业联赛2026年年度总决赛
- 非官方BP整理項目 Fire-Phoenixs/kpl-bp-dataset 自述2019–2026年約11,141局，整理結構採CC BY-NC非商業條款，賽事資料權利屬原權利人；資料可被公眾閱讀不等於明確授權自動採集、再發布或商業建模。未取得與本次用途相匹配的供應者合約／權利人授權。本輪無抓取相關原始文件：
  https://github.com/Fire-Phoenixs/kpl-bp-dataset
  https://github.com/Fire-Phoenixs/kpl-bp-dataset/blob/main/docs/source.md
- 非官方KPL研究平台自述2,901場／11,138局，截至2026-10-26 19:20更新，並自稱與騰訊無關；不可當作11月3日當晚官方即時資料或獨立授權證明：
  https://kpldata-site.hccccc01333.workers.dev/about

**進度結論：真實、授權且事前可見的完整BO7樣本＝0；真實KPL樣本外Brier、方向命中率及正EV均不能核實。** 前三局有賽後官方公開紀錄，並不代表存在當時封存的賽前Elo預測。

## 2. 新增可實際使用的離線准入閘門

檔案：research/kpl_v18_history_admission.py

函數：audit_history_intake(rows, packets, forecast_archive_path, signed_envelopes, trusted_keys, rights_claim, *, model_frozen_at, expected_model_version, registered_series_ids, universe_registered_at, ...)

**核對五種相互分離的記錄：**

1. V17逐局資料必須覆蓋完整BO7系列賽，具唯一 series_id + game_number、固定雙方team_id、來源類別及可信格式嘅時間欄位，不得混合synthetic／unknown public／license claim；事前登記完整series universe（只做格式核對，唔證明登記時間真實）。
2. 每局要有獨立提供的原始 `raw_record_json`，SHA256必須與V17行指紋一致，並檢查series、局數、隊伍、勝方、開局／結果時間完全一致；拒絕重複JSON鍵、跨局重播、冒牌子域、發布晚於首次賽果觀測及原件篡改。URL匹配只係形式檢查，唔係權威來源身份認證。
3. V11/V13事前預測封存必須存在、鏈式雜湊一致；每局series/game、team A/B、forecast_at、game_start_at、PRE_GAME及expected_model_version必須精確對應。無事前封存就唔可以將賽後倒算出的Elo稱為實際預測。
4. V14 Ed25519封存收據逐筆驗簽、固定SPKI指紋及整個預測宇宙覆蓋；缺漏、偽簽章、不同archive重播都拒絕；公鑰由函數外部提供，其信任根仍要獨立證實。
5. V17以訓練／測試時間順序重播Elo（只使用當時已發布賽果），並比對**每一條測試組**預測概率與真正保存在賽前封存中的同局概率一致。即使重新計算本地整份封存鏈並更改概率，亦會因Elo輸出不符或簽章核對失敗而被拒絕。

提供的 `rights_claim` 僅包含provider、hostname、授權參考、合約內容hash、RESEARCH_BACKTEST用途及有效期**聲稱**。填寫全部欄位、提供自簽公鑰或偽造已授權合同的SHA256，不能證明實際取得權利。輸出固定：

- status=HOLD
- licence_independently_verified=False
- source_identity_independently_authenticated=False
- independent_pregame_existence_verified=False
- real_kpl_accuracy_verified=False
- eligible_for_real_kpl_performance_claims=False
- live_execution_allowed=False
- production_recommendations=DISABLED

`technical_preflight_passed=True` 只代表合成／自填資料內部一致；**決不**代表真正獲官方授權、可信賽前封存或市場預測效果。

## 3. 合成回歸

測試檔：ops/tests/test_kpl_v18_history_admission.py

19項合成測試，包含完整四場BO7各四局、16筆原始JSON、16筆V11事前封存及16份本地臨時Ed25519簽章，並測試缺失來源、資料hash衝突、勝方偷換、假域名、錯發布時間、資料夾中少一個BO系列、universe事後登記、缺签章、簽章損壞、錯公鑰、事後改概率再重算全條SHA鏈、假授權聲稱仍不得批准實測結果。

```bash
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v18_history_admission.py' -v
python -m unittest discover -s ops/tests -q
```

## 4. 真正實測下一步必須獲得

- 權利人或獲授權供應者清晰涵蓋逐局資料用途的書面權利及穩定來源接口；
- 完整match_id、battle_id、BP、比分、來源發佈時間、比賽版本，且每個系列賽最終賽果已核實；
- 真正事前提交的、可以由獨立見證機構查證的預測封存與賽果公開時間證據；同樣嘅模型必須喺測試開始前固定；
- 事前定義完整測試母體；不能事後只揀成功預測的系列賽；
- 按相同資訊時點比較50:50、Elo、BP模型與有真實時間報價的去水市場基線，計算有效樣本數、Brier/Log Loss/ECE、方向覆蓋率、按BO系列分群bootstrap及EV不確定性。

資料不足就停在HOLD，唔宣稱提升命中率。PR #400保留Draft，須經獨立程式碼、合規及安全審核後方可考慮整合；不可在上游研究PR未完成時直接合併main。
