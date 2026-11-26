# V5.0 第三階段
固定 L2 正則化聯合估計攻擊、防守、主場與聯賽截距；中心化識別限制，帶回溯步長的梯度最佳化。
獨立球季訓練與凍結評估；未知隊伍拒絕。不調用已看過的評估標籤選參數。
比較凍結聯賽平均入球基準，而非原封存 V4.1；未有市場對照、跨聯賽強度、真實 xG、前瞻資格。
執行 python -m ops.v5_joint_poisson --train train.json --assessment test.json --output /tmp/v5-joint.json。
正式推薦 DISABLED；不得自動升級。