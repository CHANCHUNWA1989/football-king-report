# 足球王者｜零額外 API 額度賽果數據補強（2026-10-12）

## 已核實嘅瓶頸

- 每日結算目前主要讀 `sources/latest.json` 一份公開免費來源快照。每次來源只抽樣部分賽事；舊賽果會隨日子過去逐漸消失。
- GitHub `sources/history/YYYY/MM/DD/*.json.gz` 已經存有多次**較舊**、經原有資料格式防護清洗的公開來源觀察，但結算流程之前冇重用。
- 最近一次檢視 `sources/latest.json` 有50場樣本，其中38筆「已完場」來自**同一個**免費供應商；其他三個來源當時分別係 HOLD／未設定。所以不能把資料筆數增多冒充**獨立賽果認證**。
- `evidence/settled.json` 最近已有24個已結算研究樣本、0個獨立認證。樣本數會隨賽事實際結束增加，不能靠程式假造。

## 實際修正

1. 新增 `ops/free_score_history.py`，零網絡請求、只讀 `sources/history` 過去14日公開快照；最多70份檔案，單檔壓縮上限150KB，解壓上限500KB，最多100筆已完場候選。
2. 使用既有 `source_publish_guard.verify` 核對來源公開 schema、供應商資料、時間、禁用私密欄位；只接受**快照擷取在原開賽100分鐘後、現在至少120分鐘後**已列為完場的足球結果。
3. 同一供應商、賽事ID、相同正式比分只計一次；如果舊快照與新快照報告相反**比分不會揀其一**，全部保留，交由 `forward_validation.build_index` 偵測及隔離。唔會因為來源愈多就亂湊勝率。
4. 每日 `football-king-iphone.yml` 的結算、待處理賽事清單都增加 `--free-history sources/history`；新歷史候選加上最新免費快照，總數嚴格維持原本 `<=150` 筆上限。
5. 研究網頁 `validation.json` 與 `forward_cohort_backlog.json` 附有歷史來源驗證、拒絕、去重及補回筆數，可以知道有冇真正增加候選資料。
6. 沒有改動 A/B/C 模型、原有封存預測、原有結算歷史、賠率推介閘門、GitHub API Key 或 The Odds API 免費配額。

## 驗收指令

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

新增 `ops/tests/test_free_score_history.py`，覆蓋過期最新快照但有效歷史比分可補回、同一來源重複去重、比分衝突隔離、只有已封存賽前模型可以結算、偽造/未完場/未來/超大來源拒絕。

## 不能誤解的限制

- 此功能**只改善免費完場數據覆蓋率**，不等於新的即時正選、傷停、xG、亞洲盤或大小球資料。
- 來源快照較舊不等於符合「真實可靠獨立賽果認證」，回報仍標明 `independently_verified=False`，`production_recommendations=DISABLED`。
- 不能保證每次會補到新的**已封存同場配對**；是否增加，必須睇網站下一次實際運行後嘅 `newly_settled` 與來源回收數據。
- 如要真正提高經驗證勝率，下一階段需要第二個獨立真實賽果來源、準確正選及更多未來封存樣本；不能用重複比分湊到300場。
