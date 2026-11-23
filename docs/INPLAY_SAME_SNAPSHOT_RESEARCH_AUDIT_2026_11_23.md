# VNext：同場同時點雙模型研究配對閘（2026-11-23）

## 目標與依賴
這係疊加在 Draft PR #529（獨立剩餘時間 Poisson 基準模型）之上嘅研究工具，**唔修改** #529、未合併 PR #433（動態勝平負研究 challenger）、或封存 A/B/C/D。此 PR 的 base 應該指向 #529 的研究分支；等 #529 獲獨立審核並合併後，才考慮重新指向 main。#433 另有 #429→#430→#431 依賴，不能偷步合併。

檔案：
- `ops/inplay_same_snapshot_comparison.py`：`compare(case, challenger_snapshot, challenger_output)`
- `ops/tests/test_inplay_same_snapshot_comparison.py`：模擬快照、異常證據與偽造認證正反向測試。

## 檢查範圍
只接受 PR #529 `evaluate(case)` 返回 `RESEARCH_ONLY` 的輸入，且候選的聲稱快照具有**完全一致嘅賽事ID、開球UTC、決定時刻（容許不同時區書寫但必須同一瞬間）、常規分鐘、比分、紅牌、賽前估計主客入球率及賽前預測時間**。候選必須具 PR #433 格式，包含自報證據與賽前輸入 SHA256，並宣告未校準、無外部時鐘見證、無正式投注資格。

遇到資料源聲稱過時、分鐘錯誤、模型賽前時刻倒灌、不同球隊賽事ID、賽後賽果或博彩公司盤口混入、快照紅牌矛盾、模型機率 NaN／總和≠1、把 `certified` / `positive_ev_verified` 之類加成通過旗標，都直接 `HOLD`。

合格時只比較兩個**聲稱**的三向機率及相差的百分點。嚴格 `certified_paired_samples=0`、`eligible_for_formal_comparison=false`、`prediction_execution_authenticated=false`、`probabilities_calibrated=false`、`positive_ev_verified=false`、`production_recommendations=DISABLED`、`recommendation=null`。唔讀最終賽果，唔計算 EV、ROI、CLV、勝率或下注額。

## 安全限制及未完成
1. **對照只係輸入／輸出聲稱的形式配對**：目前只核實欄位互相一致，不能證明 PR #433 模型真正執行過。自填 SHA256 唔係第三方封存，兩個發佈者亦可能共用上游。即使通過，都唔屬正式前瞻樣本。
2. PR #433 output 只有 `fixture_id`，冇獨立官方主客球隊 native-ID 證據；本模組只做 ID 格式及一致性驗證，唔宣稱球隊身份已實證。
3. PR #529 基準明確排除紅牌影響：一旦紅牌非零／未知就 HOLD，唔可以拿佢與紅牌修正 challenger 誤比；補時亦未建模。
4. 本工具冇直接導入 #433，唔會用假候選數據當作真前瞻；日後須建立同一已核實事件截點嘅實際程式調用收據，外部可信時間與原始資料 hash，並在另一層做模型執行核驗。
5. 未有經授權現場實際 xG、雙來源獨立身份認證或可成交盤口；維持正式 `HOLD / DISABLED`。

## 驗收
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```
要求獨立審查 exact-head CI、資料時序及上述禁止升級嘅安全旗標。真正證明模型較佳，仍須同場同一時間點前瞻封存、獨立賽果核實、至少300場／12週／4聯賽每聯賽至少40場及配對不確定性檢驗。測試通過不代表提升準確率。

## 11月23日驗收示例
以**純合成** 1比1半場、45分鐘、賽前主客入球率1.5/1.1作測試，研究比較只回傳「兩模型三向機率差異」，沒有真實賠率、推薦或盈利數值，不等於河床／拉魯斯實際賽前驗證。
