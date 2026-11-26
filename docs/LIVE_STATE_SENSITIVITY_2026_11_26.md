# 第四批：即場狀態敏感度研究（2026-11-26）
新增 opt-in 本地 CLI，重用 live_score_identity_guard 的預先封存賽事ID及雙來源比分一致性。另要求 90 秒內上游時刻、兩來源相同正規比賽分鐘、完整紅牌歷史聲明、同隊同分鐘事件及獨立來源ID（只驗證各來源內部不重複）。無資料唔當零；來源聲明不等於真正獨立認證。只限正規1–89分鐘，無補時／加時。用明確假設全場入球率按剩餘正規時間縮放，三組人數差敏感度（1/1、0.85/1.15、0.65/1.35）純粹壓力研究、不是實證校準係數。輸出條件性最終1X2、大小2.5、落後隊最終反勝概率；不產生賠率、EV、投注建議。未使用實際xG或紅牌後xG資料、無自動即場採集、無部署；不修改原有模型。全部保持 DISABLED/HOLD。
運行：python -m ops.live_state_sensitivity --input CASE.json --output OUT.json
測試：python -m unittest discover -s ops/tests -p test_live_state_sensitivity.py -v
新增5個合成測試方法，未有真實樣本外驗證。CI 及獨立覆核前不得合併。


Consolidated extension: optional 0/3/6 hypothetical future added minutes, up to nine scenarios; same remaining-goal distribution drives 8 AH and 6 totals projections. No announced added time or actual odds. Strict JSON input. Existing default remains zero extra minutes.
