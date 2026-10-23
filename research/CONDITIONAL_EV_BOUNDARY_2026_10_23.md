# PR305：有限二元 EV 算術，不是可信推薦資格

本輪修正既有 PR305 的輸入處理及輸出語義。原版本未合併、主線沒有該模組 consumer，不能把此次缺陷描述成已放行正式投注。這項修補不建立可信 admission、不提高模型命中率，亦不改既有預測、模型權重、來源政策、seal、ledger 或正式門檻。

## 已重現的缺陷

原精確版本 `ad939da8adcd73b0ab01cb97c068aee74254b8c5` 的8項測試通過，但獨立9組輸入重現：

- 三個 caller 認證欄位使用 truthiness；字串 `"false"`、整數1及任意物件仍可回傳 `ELIGIBLE_RESEARCH / POSITIVE_EV_VALIDATED_INPUTS`。
- `now=False` 或0被默認成目前時鐘，無效呼叫者輸入沒有被拒絕。
- `source=1` 及超大整數賠率分別觸發 `AttributeError`／`OverflowError`，沒有依函式合約回傳 HOLD。
- 極小正概率可產生 `fair_odds=inf`，即使結果為 HOLD仍帶非有限數值。

公開精確版本審查：[PR305 comment](https://github.com/CHANCHUNWA1989/football-king-report/pull/305#issuecomment-6361099827)。

## 修正後的範圍

保留既有最低賠率1.80、EV必須大於0、報價最多20分鐘，以及只處理全贏／全輸二元情況的範圍。它不處理亞洲四分之一盤、和局退回或其他派彩結構。

正常輸入只能產生 **UNVERIFIED_RESEARCH／CONDITIONAL_EV_ARITHMETIC_ONLY**：這表示依輸入概率計算條件算術，不表示概率、來源、事件／盤口身份、校準、可成交價格或正期望值已獨立認證。caller 的 bool 欄位僅是嚴格型別檢查的聲稱，不是證據；沒有新增讀 caller flag 就通過的驗證器，也沒有接到正式推薦 consumer。

數值、來源及時鐘輸入須明確有效；只有 `now is None` 可以使用預設時鐘。非 bool 認證欄、非字串來源、NaN／無限／無法安全表示的數值、無效日期／時區、過時／未來報價或已開賽皆安全 HOLD。回傳的數值欄位必須有限，能使用 `allow_nan=False` 嚴格 JSON 序列化，不把異常數值帶到下游。

正向測試只核對條件公式 `odds × supplied_probability − 1` 及相應公平賠率，合成輸入不加入真實樣本、策略優勢或推薦紀錄。負向及獨立紅隊驗收處理錯誤型別、極端數值、時間邊界及不當認證聲稱。實際測試數、精確 SHA、CI、獨立覆核及發布讀回以本 PR 的完成紀錄為準，不預先寫成通過。

## 正式主推仍未完成

#274 仍需肯定來源採集／上游／用途原件、確實獨立第二來源、固定跨源身份、actual kickoff／regulation FT及原封存連結，再以真實原件完成版本化可信 admission。現有 `TRUSTED_EVIDENCE_VERIFIER_NOT_IMPLEMENTED` 不因加入算術 helper 而消失。

正式推薦維持 HOLD／DISABLED；原300場、12個合資格週、四聯賽及其他前瞻校準、市場比較、不確定性要求不變。沒有本輪新認證樣本或模型改善聲稱。
