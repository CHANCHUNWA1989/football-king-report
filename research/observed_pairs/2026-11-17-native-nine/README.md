# 德甲 9 場已完場研究樣本

本批包括 2026 年 11 月 6 至 8 日開賽嘅 9 場德甲。每場保留原始賽前主勝、和、客勝概率，以及 OpenLigaDB 其後報告嘅全場比分。**已完場研究樣本 9 場，經獨立賽果來源核實 0 場。** 正式推薦維持 HOLD／DISABLED。

## 賽前預測

11 月 5 日工作流程保留咗預測、配對同賽程三份原件。以 GitHub CLI 2.83.1 重驗原有 Sigstore 簽章，三份原件嘅雜湊、簽署工作流程身份同透明日誌記錄均吻合。日誌時間為 **2026-11-05 02:11:41 UTC**，早過 9 場各自記錄嘅開波時間；當中最早一場係 11 月 6 日 19:30 UTC。實際鳴笛時間及程式執行所載入嘅模型檔案仍待獨立核實。[原始預測工作流程](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41953346254) · [另一個開賽前已包含同一封存嘅 GitHub 記錄](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/42133264108)

每場原始配對嘅賽事 ID、預測時間、開波時間及三項概率，都同已簽署嘅 shadow 預測逐項吻合。shadow 記錄咗模型版本 `poisson-shrinkage-unvalidated-v4.1`、訓練截止日、訓練場數及訓練資料雜湊。今次沿用原始概率。[原始配對封存](https://github.com/CHANCHUNWA1989/football-king-report/blob/af0524236b0304dffe621f22f64adfdbd71fed07/research_pairs/2026/11/05/41953346254-1.json.gz)

## 賽果及選樣

賽果沿用 11 月 17 日私下保存嘅 OpenLigaDB 回應。每場均有唯一 `openligadb:<matchID>`、相同 UTC 開波時間、聯賽、球季及主客隊，且 `matchIsFinished=true`。9 場各有唯一 `resultTypeID=2`、`After90Minutes` 嘅比分。採集時間只表示本地幾時觀察到結果。賽果由同一供應商提供，仍欠獨立 FT90 核實。[資料來源及署名：OpenLigaDB／community contributors](https://api.openligadb.de/getmatchdata/bl1/2026) · [來源使用記錄](../../OPENLIGA_CONTROLLED_CAPTURE_2026_10_20.md) · [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)

呢批樣本係事後按身份及證據條件整理。選中嘅 11 月 5 日封存共 29 列，11 列欠相應原生 ID，9 列喺採集時仍欠完場結果，其餘 9 列全部納入。呢個單週末樣本可用作研究診斷。跨封存選樣偏差仍未評估，亦欠可成交報價及獨立樣本外驗證。

## 取用

`private_samples.age` 使用專案既有收件人公鑰加密。收件人可於私人目錄解密及解壓，讀取 `samples.json` 逐場預測與比分、原始來源回應、模型對應及驗簽報告。公開收據列明密文同各原件嘅 SHA-256。本次已驗縮包內容及雜湊；解密仍待持有私鑰嘅收件人驗證。[收據](receipt.json)
