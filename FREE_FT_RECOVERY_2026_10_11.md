# 足球王者：免費完場比分補查與安全結算（2026-10-11）

## 實測瓶頸

最新發佈的 `forward_cohort_backlog.json` 顯示：
- 40 場嚴格賽前封存的模型與早前市場配對；
- 7 場初步結算，全部德甲；
- 10 場已過完場時間但缺少可配對比分；
- 23 場等待開賽或完場緩衝；
- 0 場具有完整獨立認證。

同一時間，`sources/latest.json` 已保存來自免費供應商的 25
條 `FINISHED` 觀察，但原本 `forward_validation.py` 並無將呢份
**已經成功收集** 的比分加入賽後結算候選池。因此存在實際
未連線嘅資料管道，唔係欠缺另一個預測模型。

## 真正更新

- 在每次 iPhone research workflow 執行中，將原本已歸檔的
  `sources/latest.json` 以 `--free-source` 傳到前瞻結算與
  六大聯賽樣本瓶頸審核；**沒有增加任何外部 API 查詢或收費賠率配額**。
- 新 `ops/free_result_recovery.py` 重用正式來源發佈驗證規範，
  拒絕沒有四供應商元資料、虛報數量、含有商業原始賠率、
  非 `FINISHED`、無有效 UTC 時間、過期超過 48 小時、
  開賽後少於正常 100 分鐘就聲稱完場，以及開波兩小時內
  嘗試計分的資料。
- 賽事以相同聯賽、同一主客隊身份、相距不多於 45 分鐘嘅
  開球時間配對。任何相同賽事兩個比分即使係相同主／和／客
  （例如 0:2 同 1:3），亦不可擅自揀一個。完全相同嘅
  90 分鐘比分，可互相對照但只結算一次。
- `extend()` 附加嚴格賽前已封存身份檢查，禁止直接用一個
  已封存賽事身份配對另一隊或另一聯賽嘅比分。
- 對缺失、損壞、過期免費檔案採取安全降級；唔會中斷原本
  從 gateway 成功取得嘅結算，亦唔會以失敗補救覆寫資料。
- `validation.json.cached_free_final_recovery` 同
  `forward_cohort_backlog.json.cached_free_final_recovery`
  獨立展示免費來源有幾多完場比分候選通過驗證；
  **候選數唔等於新增真實已結算樣本數**。

## 真確性界線

這些依舊只是 **一個免費供應商公開完場比分觀察**。
`results_independently_verified`、
`fixture_result_source_independently_verified`、
`production_recommendations` 仍然必須係 `false/false/DISABLED`。
即使新一輪結算增加，亦唔代表完成正式推薦所需 300 場、
12 個賽週、4 個聯賽各 40 場、獨立結果認證、相對市場優勢、
合法可成交賠率以及人工風險審核。

## 驗收與跟進

跑全部回歸、壓力、零密鑰測試同最新 iPhone 發佈，
直接核對網站嘅 `forward_cohort_backlog.json` 同
`validation.json`：確認 `score_unavailable_or_unmatched` 是否下降，
`settled_forward_cases` 是否真有增加；不允許將 25 個候選
直接算做 25 個勝率樣本。變更只計發佈時已存在、賽前封存的
原始預測。
