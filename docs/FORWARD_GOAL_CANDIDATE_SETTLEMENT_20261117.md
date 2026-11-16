# 足球王者｜真實9場德甲賽前封存：賽後只讀雙來源候選對帳（2026-11-17）

> **技術研究，不是投注或已認證成績。** 呢項研究分支建基於 PR #489，尚未合併 main。未有兩個獨立官方可核實完場來源之前，不計算正式前瞻樣本、不作任何EV/ROI、禁止模型放行。

## 真實賽前原始證據（非虛構）

2026年11月16日23:38香港時間：
- GitHub Actions [run 43898363049](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43898363049) attempt1；repo PR489 HEAD `049a48acad32d9267d0c3ede3a11975a90213806`；
- GitHub Artifact `14241370204`，9場均有研究模型預測，zip created 2026-11-16T15:38:26Z，保留至2027-02-14；
- Artifact ZIP SHA256: `5f233605741a881f5716adc94b4f4547fee18d57c4685d98d17db1a36ed39150`；
- ZIP 內 JSON檔 SHA256: `996c2083181e92e42502ee0e241be3377473dac62989348fa52c5ace0868ffe2`；
- JSON envelope SHA256: `cd760b06c342ddf0748e2f7ca716941bf03ecf53951f2affbddad37dd9312e03`；
- source response SHA256 (未獨立認證): `820ff0480721b41ed829ad00e6ce359d99c2787ca133ca02c143e29d81b9385f`；
- Source received: `2026-11-16T15:38:25.366147Z`，原版A率研究模型同次 runner 計算；
- 九場固定原版大2.5及BTTS與75/25混合概率已放在 [PR489留言 #6922771574](https://github.com/CHANCHUNWA1989/football-king-report/pull/489#issuecomment-6922771574)。首場於2026-11-21 03:30 HKT開賽。

**ZIP hash有GitHub提供同幾乎同時戳記錄，但ZIP、PR留言或內部JSON SHA仍不等同 Rekor/TSA獨立認證、來源正式發布時刻或跨兩來源球隊身份確認。**

## 新增賽後只讀研究工具

`ops/forward_goal_candidate_settlement.py` 支持將**固定封存JSON**配對賽後來源候選觀察。必須明確傳入預期 snapshot SHA256及capture_id，否則不能把另一個檔案冒充原始9場。

每條來源觀察必須有：
- exact `fixture_id` （原本 `openligadb:xxxx`）
- `provider_namespace`、`provider_fixture_id`
- `captured_utc`、`raw_response_sha256`、`status:"FT"`
- `home_goals`、`away_goals` 為90分鐘完場比分

每場所有供應商候選都保留：
- 未到開賽+90分鐘、未有來源、只有一個來源、來源比分衝突、兩個來源共用相同原件SHA，全部**HOLD**。
- 兩個以上不同 provider 名稱、來源 SHA亦不同，且全數同分時，**只**稱「`MATCHED_TWO_PROVIDER_NAMES_UNVERIFIED`」，輸出描述性Brier/Log Loss；不能證實真係獨立官方來源。
- 未見過的賽事ID、重複供應商、布林比分、非法時間／日期、報價注入、修改原始 forecast SHA一律拒絕。
- 即使有來源一致仍固定 `certified_independent_forward_cases=0`、`official_final_result_independently_verified=false`、`positive_ev_verified=false`、`production_recommendations=DISABLED`。
- **全部9場永遠保留在分母**；任何源失敗／缺賽果必須留 PENDING，避免看結果揀有利場次。
- 未有任何實際賽後比分前，輸入 `[]` 應顯示9場全待核對、Brier/LogLoss=null，唔可以虛構準確率。

## 可重現命令

```bash
python -m ops.forward_goal_candidate_settlement \
  --snapshot original_pinned_snapshot.json \
  --observations genuine_two_provider_fulltime_observations.json \
  --snapshot-sha256 cd760b06c342ddf0748e2f7ca716941bf03ecf53951f2affbddad37dd9312e03 \
  --capture-id github-actions:43898363049:1 \
  --output future_read_only_report.json
```

`.github/workflows/forward-goal-candidate-settlement.yml` 自GitHub Actions API**下載原本9場的真實 ZIP**，核對實際SHA256、ZIP內JSON指紋、完整9場cohort及固定capture_id，再用 `[]` 產生賽前零成績HOLD報告，跑全部安全回歸。

## 追加公平比較與完整批次閘門（2026-11-17）

為避免只係混合模型與原版兩者比較而忽略簡單但有用的基準，賽後同一場、同一結果會**同時**計算：

- `original` 原版A入球率推導的大2.5／BTTS概率；
- `exploratory_75_25_blend` 已封存75/25混合概率；
- `training_only_prior` 已封存的上一期聯賽頻率基準（不得從該9場賽果重新估計）。

每個市場輸出三方配對Brier、Log Loss。暫時有部分對帳比分時，
`paired_market_diagnostics` 僅屬 **partial descriptive diagnostics**；
新增 `full_nine_fixture_cohort_scored` 及
`full_cohort_market_metrics_unverified`，後者只有固定9場全部有可評分的兩來源候選、
無失預測或衝突，先會有數字；否則永遠為 `null`。
即使9場全數有兩來源候選，也唔會因此聲稱獨立官方來源已獲認證，
`full_cohort_independently_certified=false`、`HOLD/DISABLED` 保持不變。

再加入來源原生賽事ID跨 fixture 重用檢查：一個外部 provider 的同一個
`provider_fixture_id` 唔可以同時聲稱屬於封存9場入面兩個不同比賽。
此項只係防明顯誤配，**唔證明原生ID真確**。

新增3項回歸測試：同場訓練基準正確結算；同provider跨賽事native-ID誤用被拒；
合成9場全部有候選結果時，全批結果閘門先會打開。
合成比分只測程式，不納入真實績效樣本。

## 待完成（不能假裝已成功）

1. 本輪9場最快11月21日香港時間踢完之後，先可接入**真正合法、有來源原件及時間**的FT結果；不能提前填比分；
2. 所有球隊ID／來源native ID對照及官方＋第二來源需獨立交叉核實，僅靠兩個provider字串不足以認證；
3. 須新取得真實同場、同時間的亞洲讓球／大小球可成交盤口，才可計正式EV/ROI；目前沒有；
4. 正確的前瞻比較仍需更多**事先封存**、真正未知的聯賽和場次；9場唔足以證明準確率。
5. 本研究未有合併、部署或排程每日跑。測試結果若通過只能證明稽核紀律，不等於盈利能力。

**永久保持 HOLD / DISABLED / NO BETTING / DRAFT。**
