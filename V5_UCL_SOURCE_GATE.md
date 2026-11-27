# V5.0 第五階段：歐聯雙來源研究接入
- Football-data.org 官方免費覆蓋包括 CL；需既有 FOOTBALL_DATA_ORG_TOKEN。官方文件 https://www.football-data.org/coverage 及 https://docs.football-data.org/general/v4/coding_client.html
- TheSportsDB 官方開發 API：一個有配額保護的歐聯日程探測（4480）， https://www.thesportsdb.com/docs/api ，條款 https://api.thesportsdb.com/docs_terms_of_use.php 。只輸出診斷摘要，不發佈原件。
- ESPN 未採用：未確認自動採集及模型使用授權。不得繞過 API 存取。
- 逐場按明確雙來源 native team ID 對照，完全相同 UTC 開賽時間；對照參考及來源身分尚須獨立驗證。不由隊名模糊配對，不以供應商數量證明獨立性。
- 研究 CI 只跑合成單元測試及一次免費 TSDB 探測，不取得 secret。CLI 可在已授權環境選用 --probe-football-data；不印 token。正式賽事模型、跨聯賽強度、歷史訓練資料及 xG 仍未接通。HOLD/DISABLED。
- CLI: python -m ops.v5_ucl_source_gate --probe-sportsdb --ledger /tmp/v5-budget.json --output /tmp/v5-ucl.json
