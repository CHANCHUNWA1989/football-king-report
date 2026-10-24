# 原封存四方評分與受控賽果候選整合重播（2026-10-24）

本輪將原件接收、原封存A/B/C及市場、同案90分鐘賽果候選、逐場LogLoss／Brier及每日CI接成一個整合更新。這是有真實原件正例的研究重播元件，沒有完成可信outcome admission、來源認證或正式認證metrics consumer。

## 原有缺口與整合範圍

PR318可每次fresh驗章並連結原預測與受控capture，但其輸出沒有由同份已驗paired及tar直接產生四方評分。既有research_center的研究ledger統計不能代替這條逐案原件綁定鏈。

- `ops/case_fourway_scoring.py`：只用同一原pair已存在的model／ab／c／market向量，檢查既有B/C固定modelID及matches_sealed、身份、無賽果污染、安全旗號與市場／預測／記錄開賽時序。缺B/C、錯向量／版本、布林／非有限概率或賽果回填拒絕，不補算或改權重。用既有research_center.score的LogLoss及三分類Brier慣例，不重正規化原封存向量。A與market只有原欄位來源標籤，沒有虛構註冊modelID。
- `ops/controlled_case_replay.py`：只接兩個原proofdir、兩組固定source／workflow／run／attempt及case／pairedSHA。內部呼叫intake一次，fresh capture1＋forecast3個實際CLI；不接saved intake report。六份proof在前後及評分後比bytes，與本次驗證reference digest／context相扣；strict JSON唯一case與同tar raw／manifest／FT candidate再核對，拒換件、錯場、加時、未完場或引用衝突。CLI只可寫proof外全新衍生檔。
- 兩份four-model CI／daily workflow：原隔離job改為一次replay，不先intake再重跑造成8CLI。保留舊selection.json及report.json診斷，新增replay.json。舊capture／forecast API context、原pins、全部11項false及0cert斷言保留；原archive jobs不依賴本job。新增4個程式／測試path觸發CI。

新report同時包含fresh intake、scoring、原件references、不同來源時間及所有admission blockers。外層與case仍HOLD／DISABLED、11資格false、candidate_only=true、certified_case_count=0、derived_review_not_a_trust_input=true。沒有接入settled、verified_records、FT正式輸入或正式readiness；不把未認證比分改成result_verified=true。

## 正反向驗收

兩個模組均先red再修。新增25項測試方法：13項純計分、12項原件重播。純計分包含主／和／客、錯型別、zero-probability clipping、已封存B/C不一致、時序及極端日期；重播包含fresh CLI失敗、六份proof換件、評分期間換件、pins／FT期間／引用衝突、未完場、缺challenger及輸出界線。Mocked CLI測試明確只測語義，不當真實密碼學證據。

- compileall通過。
- `python -m unittest discover -s ops/tests -q`：1,801項通過。
- `python -m unittest discover -s tests -q`：150項通過，合共1,951項。
- 主助理真正執行兩份相同的實際YAML腳本本體，官方gh2.102.1 SHA d7e919c19ad89502313325c2690bf8a8556234ec734b7a4593e39244ab3e4a87、fresh GitHub run API及每次4個真驗章CLI，兩正例成功。Capture加一byte、錯forecast source、錯case三個真CLI負例均拒絕、無評分。Daily本地artifact交付來自既有永久proof還原，不冒稱hosted daily或新的來源採集。
- 原forecast39531309964/1、source/workflow99a855861d5836a85097de3271905412a632f636、paired SHA666628a233176eaf22e79c69ee847793127fcd4b924ca0f4e40b2c6306409830；受控capture40053042424/1、source/workflow79cbffadf8155344172a4e92054a3abfda71ab4e。真正native收據位於core-replay-batch/native-154839875664/receipt.json。

## 真實候選下的數學結果與界線

原case32760f90f88632237a2184f309f033d1d382d992dcf62cc53c53e9a85134266f，若以同受控tar顯示的未認證2:3作條件：

| 原封存向量 | LogLoss | 三分類Brier |
|---|---:|---:|
| A | 2.0979868477 | 1.3065619990 |
| B | 1.8688714258 | 1.1827017744 |
| C | 1.9982863454 | 1.2618883840 |
| 同截止市場 | 1.9671462473 | 1.2472004139 |

以上一場條件式研究數值不是認證校準、命中率、模型優勢、可成交價或ROI。B本案數值較低不能推定樣本外優勢；A與C本案亦未勝市場。市場共識不是可成交報價。

完整trusted outcome admission與只讀認證案例的consumer仍待真來源肯定證據與實作；凍結v1來源政策的upstream仍UNKNOWN。來源用途／獨立採集、權威model／market／結果身份橋接、actualKO、獨立regulation FT、300認證場／12合資格週／4聯賽各40、校準與可成交價及最終審批要求不變。官方Bundesliga頁tdm:mine需obtainConsent的已查界線保留，沒有新增provider採集。

原seal／model weights／賽果ledger／來源政策／ZIP／門檻不改，0新增認證／正式推薦、未證實預測提高。獨立覆核、PR CI及合併發布須看實際PR收據，不能把本地測試當已完成hosted或首個自然daily。
