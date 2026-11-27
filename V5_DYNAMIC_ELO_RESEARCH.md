# V5.0 第二階段：Dynamic Elo + 近期攻守（研究）
固定 K=20、主場 Elo 55、近期入球權重半衰期120日、先驗6、Elo與入球率對數融合各50%。參數為研究設計選擇，未經優化。主場入球均值不再重複加主場 Elo。
只使用早於比賽日期的已完成資料；同日全數預測後才更新 Elo。逐聯賽本地來源名稱，不做跨聯賽實力比較或未核實身份配對。
比較無時間加權的 V4.1 式入球率基準（同一分布與樣本），不是已封存 V4.1 原始概率。
2025/26 歷史資料已被研究檢視過，僅供探索，並非未見樣本外或正式前瞻。沒有獨立賽果／市場對照，不可宣稱市場優勢或 EV。
執行：
```sh
python -m unittest discover -s ops/tests -p test_v5_dynamic_elo.py -v
python -m ops.v5_dynamic_elo --archive /path/to/archive.json --output /tmp/v5-elo-replay.json
```
原有 V4.1、PR #634、已封存預測、正式推薦及配額不變。HOLD / DISABLED。
