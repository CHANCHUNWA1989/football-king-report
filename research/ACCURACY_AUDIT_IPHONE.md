# 命中率與主勝偏向審計（研究版）

2026-10-13 新增：`ops/accuracy_bias_audit.py`、獨立單元測試及手動 GitHub Actions。

## iPhone 操作

1. 開啟 GitHub → Actions → 「足球王者｜命中率及主勝偏向審計」。
2. 點 Run workflow，分支揀 `research/2026-10-13-accuracy-audit`。
3. `csv_path` 指向**已經存在於該分支**、包含封存賽前預測及已結算結果嘅 CSV。預設示範路徑不保證存在。
4. 執行完下載 `accuracy-bias-audit` artifact，檢查 `accuracy-audit.json`。

**若沒有合規 CSV，輸出 HOLD，不會杜撰命中率。**

CSV 使用既有 `ops/model_evidence.py` 的欄位格式：`case_id,prediction_utc,market_utc,kickoff_utc,p_home,p_draw,p_away,m_home,m_draw,m_away,outcome`。結果必須已完成、賽前預測必須早於開賽及有合法時間戳。CSV 可另帶 `league` 欄位，讀取器會保留該欄位以便分聯賽統計；缺少欄位則標示 `unknown`。**分類統計唔代表已完成分聯賽校準**。

報告比較同一批賽事中模型與市場最高概率方向嘅命中率、主/和/客選擇分佈、實際結果分佈。主勝偏向旗標只係描述性初篩：樣本至少20場、模型選主勝比例高於實際主勝比例20個百分點時標記；**唔係已驗證統計顯著性門檻**。

現時只支援勝和負（1X2）研究，未支援亞洲讓球、入球大小或即場盤。無獨立賽果認證、無可執行報價、無 ROI/CLV 驗證，永遠 `production_recommendations=DISABLED`。本工作流只手動執行、只上傳審計 artifact，唔改正式網站及唔扣賠率 API 額度。
