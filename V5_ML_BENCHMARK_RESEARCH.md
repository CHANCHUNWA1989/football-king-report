# V5.0 第四階段：機器學習競爭研究
Logistic Regression、LightGBM、CatBoost、XGBoost 固定參數，同場特徵及同一時間切分。
12項歷史特徵，只用之前日子完場結果；同日先全數生成特徵再更新。訓練與評估球季不重疊；不做超參數搜尋、不選勝者。
評估期間前日賽果用於更新特徵（歷史回放，非真實可用時間證據）。依賴缺少時 HOLD。模型概率不代表入球分布、獨立認證或市場EV。
安裝 research/requirements-v5-ml.txt；執行 python -m ops.v5_ml_benchmark --train train.json --assessment test.json --output /tmp/v5-ml.json。
保留原版、配額及安全閘門。正式推薦 DISABLED。