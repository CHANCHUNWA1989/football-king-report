# 參考開源足球系統：四模型同場評分接駁

## 原始來源及可採用做法

| 系統／原始文件 | 查到的做法 | 本系統採用及限制 |
| --- | --- | --- |
| [Penaltyblog 回測文件](https://penaltyblog.readthedocs.io/en/latest/backtest/backtest.html) | 透過歷史資料、lookback 訓練回呼及逐場策略評估；同時公開盈利及虧損示例 | 參考透明比較及如實報告虧損；沒有執行示例、下注、安裝套件或把其示例收益當成本系統表現 |
| [goalmodel README：Evaluating predictions](https://github.com/opisthokonta/goalmodel#evaluating-predictions) | 可輸出 Log、Brier、RPS；明確說明展示例子是樣本內，正式評估應為樣本外 | 補齊既有 A／B／C／市場同一批封存前瞻研究個案的 RPS，保留既有 Log Loss／Brier |
| [goalmodel README：模型及 Reverse engineering expected goals](https://github.com/opisthokonta/goalmodel) | 提供 Poisson、Dixon–Coles、負二項、CMP、時間權重等；由三項結果概率不能同時唯一識別兩個入球參數及 rho | 模型選擇只屬未來 challenger 候選；不能把1X2倒推入球分布當成已驗證事實，不能改寫原封存模型 |

2026-10-25 經 Firecrawl 搜尋後讀取以上頁面正文；來源是工具處理文字，非獨立原始賽果證據。
沒有比較部署負載或重跑它們的模型，亦沒有取得其供應商資料使用權。
本次採用評分方法的獨立實作，未複製外部程式碼、未加入第三方依賴。

## 已落地的接駁

現有市場收縮／每日評分程式已有 RPS，但 `research_center.json` 的嚴格四方同場
比較只輸出 Log Loss／Brier。本次在同一個 cohort 的 `prospective_four_way_research`
增加 `a_rps`、`b_rps`、`c_rps`、`market_rps`、`rps_outcome_order` 及
`rps_lower_is_better`，涵蓋總體及各聯賽 JSON。網站沿用「完整六聯賽實證資料」連結
讀取此 JSON；沒有新增手機畫面控制項。

對順序 HOME／DRAW／AWAY，採用標準化三分類 RPS：
`((p_home - I[y=HOME])² + (p_home+p_draw - I[y∈{HOME,DRAW}])²) / 2`。
數值較低較好；它是補充評分，不能代替校準、Log Loss、Brier、來源認證或市場優勢證明。
沿用既有概率驗證及封存精度容差，不重新正規化、修改原概率或回填缺失 B／C。
四方沒有完整有效封存輸入時四項 RPS 都為 null；完全沒有樣本時既有 metrics=None 不變。

## 驗收及尚欠工作

新增測試先重現缺少介面／輸出，再以 Fraction 獨立計算檢查分類順序及標準化；
驗證無效概率／布林賽果拒絕、缺封存不得增加 cohort、輸入不改寫、舊評分及閾值不變，
並經實際 publish 至臨時 JSON 核對總體／聯賽輸出。最終完整測試、獨立覆核及
GitHub CI 結果以此更新 PR 實際紀錄為準。

沒有訓練或升格新模型，沒有修改歷史封存、供應商採集、API 密鑰、私人保存或下注設定。
新增評分使用的賽果仍未獨立認證；不是認證樣本，也不是獲證明的前瞻優勢。
完整可信賽果入口、私人跨流程盤口保存、認證樣本統計及校準仍未完成。
正式推薦維持 HOLD／DISABLED；未證實預測命中率或盈利能力提高。
