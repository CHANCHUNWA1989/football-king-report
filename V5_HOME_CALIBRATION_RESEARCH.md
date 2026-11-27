# 足球王者 V5.0 — 第一階段（研究）
修正 V4.1 的主場方向偏差：獨立 home-logit shift + temperature 校準器。
固定搜尋網格及正則化；完整星期時間切分，測試集不參與該次擬合。
原始 A/B/C 不變。全量擬合只供未來、早於開波的獨立研究觀察。
歷史 archive 欠逐場賽果實際可用時間及獨立來源認證，回放不屬正式前瞻驗證。
不改 API、免費配額、部署、EV 或投注風控；目前只涵蓋原六聯賽。
命令：
```sh
python -m unittest discover -s ops/tests -p test_v5_home_calibration.py -v
python -m ops.v5_home_calibration --evidence evidence/settled.json --output /tmp/v5-research.json
```
下一階段：凍結候選、真實前瞻同場比較、歐聯雙來源接入，再獨立入球模型。
正式推薦 DISABLED；不宣稱勝率提升、不自動提升模型。
