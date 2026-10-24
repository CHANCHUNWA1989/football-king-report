# Agent來源覆蓋判斷修復（2026-10-24，沿用PR320）

本輪完成既有草稿PR320，沒有重複開PR。處理有限研究來源被誤判為沒有資料，以及同一條判斷／統計路徑的錯誤格式問題；沒有完成賽果認證、模型校準或正式推薦資格。

## 實際重現

最新主線 `f2c908d3fc1248647bd8ed311c11fa292d599a54` 的 `sources/latest.json` 收集時刻為2026-10-24T10:06:44.150673Z。TheSportsDB 為 `PARTIAL`、configured=true、10個抽樣賽程；其他來源HOLD或未配置。`agent_orchestrator` 原只接受READY_RESEARCH／PARTIAL_COVERAGE，誤報EMPTY_SOURCE_COVERAGE及0來源／0樣本。既有free_source_failover已將PARTIAL列為有限研究覆蓋。

原草稿head `9ed40dce78d0c3272c2bc489c56ce8703cc54cb4` 加入PARTIAL後，原20測試通過，但獨立反例發現：

- status為list／dict時，frozenset membership會拋TypeError。壞資料在有效資料前可令整份來源HOLD；在後則可讓來源READY但覆蓋數錯歸零。
- 判斷有檢查provider身份，統計沒有；有效來源旁邊的缺失／空白／錯型別身份資料仍會灌大來源及樣本數。

先對現主線套原PR測試重現1失敗，再在原草稿加入混合資料等測試重現20個失敗子情境，之後才修正。反例均為隔離測試資料，沒有寫入正式來源檔。

## 最終改動

`ops/agent_orchestrator.py` 以同一 `_usable_provider` 同時供snapshot判斷及覆蓋統計使用：必須為物件、非空白來源字串、configured嚴格true、status字串且為三種研究可用狀態、樣本為嚴格正整數。壞row安全排除，不會抹走同批有效row；全批不合格則HOLD。時間、新鮮度、頂層安全旗號及研究ledger檢查不變。

`ops/tests/test_agent_orchestrator.py` 保留全部原測試，合共新增9個方法（原草稿2項＋本輪7項），涵蓋三種有效狀態、混合資料順序、身份與欄位錯型別／缺失、無效provider集合、零／負數／布林／浮點樣本、過時／未來／無時區／缺時間及不安全旗號。

只修來源研究覆蓋的檢查與統計；沒有把狀態名稱或10筆樣本當成獨立認證，沒有呼叫provider、修改已封存預測／權重／賽果ledger／來源政策／原ZIP／門檻，亦沒有改動排程或新建AI服務。

## 實際驗收

- `python -m compileall -q ops` 通過。
- `python -m unittest discover -s ops/tests -q`：1,776項通過。
- `python -m unittest discover -s tests -q`：150項通過，合共1,926項。
- 實作agent另跑27項來源審計及88項相關回歸，與完整套件有重疊，不另加成新的測試總數。
- 真正執行agent_orchestrator CLI及agent_report CLI，使用現有封存來源而無網路採集：來源READY_RESEARCH、1個研究來源／10個樣本。當次市場快照04:18:14.244855Z、來源快照10:06:44.150673Z，審計11:09:11Z各自保留，不把審計時間當來源更新。
- 當次審計READY_FOR_MANUAL_REVIEW只代表輸入可供研究審查；actions_performed=[]、end_to_end_workflow_verified=false、所有獨立驗證／模型優勢／六項完成能力仍false，DISABLED及automatic_bets=false。

獨立助理最終覆核、更新同一PR後的CI、合併及網站發布須另讀實際收據，不能以本地通過代替。本輪保留PR321的認證不足額修復；仍0認證、48筆未認證研究、6品質關卡未達，完整trusted admission與認證cohort／metrics consumer、外部來源獨立性／權威ID／actualKO／獨立90分鐘賽果、足量前瞻校準及可成交價仍待完成。未證實命中率或盈利提高。
