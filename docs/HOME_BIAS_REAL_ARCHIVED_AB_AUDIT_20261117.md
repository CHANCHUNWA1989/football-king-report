# 足球王者｜主勝集中警報修正：真實封存快照舊版/新版 A/B 對照

2026-11-17 HKT · Draft PR #465 · **研究用途、HOLD／DISABLED**。

## 目的與來源

為驗收 `ops/home_favourite_sentinel.py` 嘅時間／並列概率修補，
實際重播儲存庫內**原有三份 .json.gz 真實歷史 Shadow 預測**。
同一份原始位元載入相同**現有** `research_recommender.build()`，
唯一 A/B 變量係主勝集中警報函式：

- 舊版係從原始 Git blob `9e004db15e257bc58613410f26b92a82211e7f52`
  作逐位元複本，放於 `ops/research_baselines/home_favourite_sentinel_9e004db.py`；
  每次載入會獨立按 Git `blob LEN\\0CONTENT` 計 SHA-1 核對原雜湊。
  即使普通 CI 採用 shallow checkout，亦唔會讀唔到歷史 blob；
- 新版嚴格核實時區感知嘅 UTC `prediction < kickoff`、
  同一研究快照擷取時間差不多於120秒、
  預測唔可以比計算時點遲超過5分鐘，
  開賽距今1至7日、同時刻 UTC 去重、
  主勝／和局並列最高時唔可以虛報主勝第一；
- 兩邊都使用同一個當前候選篩選函式、同一份資料、
  同一個**假設評估時點 = 封存 `as_of_utc` + 5分鐘**。
  呢個係事後研究回放慣例，**唔係當日確實執行時間**。
  新版及舊版當時實際網站選項並無被重現或改寫。

## 真實封存快照 A/B 結果

首次真實來源執行驗證：
[GitHub Actions #44025583934](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/44025583934)
（程式碼提交 `fd2a823e3780072b59881983e99db89c909974bc`）。

| 原始快照位置 | 原始預測筆數 | 原舊版德甲警報樣本 | 新版德甲有效樣本 | 舊版德甲隔離 | 新版德甲隔離 | 舊版 model-only 名單 | 新版 model-only 名單 |
|---|---:|---:|---:|:---:|:---:|---:|---:|
| `shadow/2026/10/31/41253304164-1.json.gz` | 19 | 19 | 8 | 是 | 否 | 0 | 2 |
| `shadow/2026/11/07/42426195245-1.json.gz` | 26 | 19 | 3 | 是 | 否 | 0 | 1 |
| `shadow/2026/11/08/42438672053-1.json.gz` | 26 | 19 | 3 | 是 | 否 | 0 | 1 |

另外11月7日同8日各有英超2、西甲1、法甲1、意甲3個舊新警報樣本；
各自一樣、無相關隔離旗標變化。

**重要：共71條「快照內紀錄」，唔係71場獨立賽事；
修正前後 model-only `0 → 2,0 → 1,0 → 1` 係三份快照
共四次名單席位差異，絕對唔代表四場獨立成功預測、勝率或盈利。**
今次冇配任何真實完場結果，`independent_match_results_scored=0`。

### 技術發現

根因係原有 `assess(predictions)` 對字串非空即收，
唔解析 UTC 時間，亦冇觀察名單本身嘅1–7日開波限制；
即使後續 shortlist 只接收真正合資格場次，整體警報仍然被
更遠期賽事推高而誤將可用德甲候選隔離。新版先將統計
母體對齊後續名單嘅時間閘門，能減少**無效研究隔離**，
而非強行提升一個模型嘅預測概率。

## 測試及信任邊界

`ops/tests/test_home_bias_real_archive_ab_audit.py` 為
來源重播、相同輸入 A/B、不能改原件、重複JSON欄位、
非法來源路徑、壓縮炸彈、重複快照／失敗不輸出部分評分，
提供合成對抗性測試。

`ops/home_bias_real_archive_ab_audit.py` 只讀固定原件，
逐份寫出原始壓縮與解壓 JSON SHA256；每份只比較
`legacy_model_only_count`／`fixed_model_only_count` 等**工程指標**。
原始記錄冇因為新版結果而變更。

限制如下：

1. 封存資料不等同外部來源／開賽前 TSA 獨立見證。
2. 舊快照無法證明現代主客場樣本 metadata 喺當時完整；
   **不替舊預測補填新欄位**，亦唔聲稱已驗收 role-history 全面效果。
3. 評估時間係人為統一快照+5分鐘；實際歷史推薦執行時間未重現。
4. 呢個只係控制相同候選引擎、替換單一警報函式嘅工程 A/B，
   **唔係**兩個原封不動歷史網站嘅真實全鏈路發佈比較。
5. 完全冇實盤讓球／大細球賠率、成交、正 EV、ROI、CLV、賽後命中或模型校準驗證。
6. 舊版大量無效警報被修正並不保證新增候選較準；
   **禁止因為回放結果而冒充高信心投注。**

## 工程決定與下一關

本次修正能量化減少不合資格賽事影響，值得保留喺
**Draft PR #465**。已封存 A/Poisson/DC 等概率一律原樣，
`main` 唔合併，`HOLD`／`production_recommendations=DISABLED`、
`positive_ev_verified=false`、`certified_prospective_samples=0`。

下一關應由現在起取得**新鮮合資格**主客場角色樣本紀錄、
並於開賽前封存，日後對照真實 FT 計算同場 Brier/Log Loss；
而來源許可、獨立審核與 main 分支保護
仍需先完成 [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)。

可重現（不連線不收費）：

```bash
PYTHONPATH=.:ops python -m ops.home_bias_real_archive_ab_audit \
  --archive \
    shadow/2026/10/31/41253304164-1.json.gz \
    shadow/2026/11/07/42426195245-1.json.gz \
    shadow/2026/11/08/42438672053-1.json.gz \
  --output /tmp/home-bias-archive-ab.json
```
