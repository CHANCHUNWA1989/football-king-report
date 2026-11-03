# KPL 第21階段｜完整母體結算閘門及防選擇性命中率報告

日期：2026-11-03。研究型 Draft PR #407，以上游 Draft PR #404（V20）為 base。沒有正式部署、真實KPL預測或投注功能變更。

## 審計發現：V20有「局部樣本準確率」泄漏風險

舊版 `audit_shadow_trial` 會將**已完成且來源聲稱已確認嘅個別系列賽／個別小局**拿來計算Brier、Log Loss和方向命中率，並顯示 `diagnostic_only_not_real_kpl`。就算：
- 原先登記嘅另一場BO7未結束／賽果尚缺；
- 同一個研究母體有部分結果係 `UNVERIFIED`；
- 完整BO7其餘小局冇任何賽前 `FORECAST` 或 `HOLD`；
- 有額外已封存研究決策，但對應BO7四勝後根本冇嗰局；

分數仍可只使用「有利且已知」嘅觀察，被誤解成真正實戰模型命中率。這個問題不等於有外部人惡意篡改，單純資料缺失都可產生偏差。

## 先測試再修復：V21實作

1. 新增 `ops/tests/test_kpl_v21_complete_cohort_gate.py`，22項全部使用虛構時間、虛構BO7、無外部授權資料嘅合成負向測試；其中4項直接呼叫V20舊 `audit_shadow_trial`，要求未完成/未核實/缺決策/額外決策時必須**完全隱藏準確率指標**。
2. 第一輪 GitHub CI：上述舊介面負向檢查失敗，問題已由雲端測試具體重現。
3. 直接修改 `research/kpl_v20_shadow_trial.py`：只有全數已登記系列賽完成、已打所有小局都存在事前FORECAST或HOLD、全部賽果至少標示SOURCE_ASSERTED、沒有未實際發生嘅多餘決策，才計算內部診斷分數。其餘情況保留母體、已打局數、缺局、HOLD和覆蓋率但 `diagnostic_only_not_real_kpl=null`。
4. 新增 `research/kpl_v21_complete_cohort_gate.py`：在舊V20結算之上施加額外研究報告門檻，預設最少40個完整BO系列賽、120個事前FORECAST小局（係預先寫明嘅篩查門檻，**未經真實KPL數據調參**）。各條件不達標時，公開留低缺失數同問題原因，但不發佈易誤導嘅準確率。測試有獨立傳入2系列／1預測嘅合成低門檻，**不代表真實世界已達到要求**。
5. 即使內部母體診斷閘門達標，`SOURCE_ASSERTED` 只係輸入者聲稱；來源身份／授權、賽果、當地時鐘、GitHub/第三方TSA不可變性均未獨立認證。所有輸出永遠 `status=HOLD`、`production_recommendations=DISABLED`、`live_execution_allowed=False`、`real_kpl_accuracy_verified=False`。

## 對預測方向嘅實際改善

- 不再讓單場命中局、已完成但偏向成功嘅部分系列賽喺完整試驗未完時扮成整個KPL模型命中率；
- 缺任何一局賽前FORECAST/HOLD，嗰局仍計入缺口，而唔係自動刪除；
- HOLD仍然喺場次覆蓋率分母，不能以少量高信心預測隱瞞整體拒絕預測比率；
- 未核實賽果來源、異常局數、低樣本，都禁止對外聲稱完整研究結果；
- 無將事後知道北京WB實際反勝嘅資料倒灌到模型，亦無將合成測試冒稱實戰命中率。

## 測試及交付

```sh
python -m compileall -q research ops
python -m unittest discover -s ops/tests -p 'test_kpl_v21_complete_cohort_gate.py' -v
python -m unittest discover -s ops/tests -q
```

PR #407 要求最後提交SHA嘅5/5 GitHub Actions全部成功並檢查原始測試日誌；先前上游 Draft PR仍待獨立審核。今次功能沒有連接KPL官方賽事接口、實時BP、真正賽前外部時間戳或可成交盤口，未有可以獨立證明模型勝率改善之資料。下一步首要工作仍係建立**真正獨立賽前時間見證**及合法賽後結果來源，累積完整前瞻性試驗，然後按分組樣本外統計研究實戰表現。
