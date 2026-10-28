# 私人原件持久傳輸：create-only上傳及跨job讀回

PR342已捕捉同一次HTTP回應原始bytes，但job完結後沒有長期保存。本階段新增可選的私人GitHub儲存傳輸，沿用同一份原件，不再向足球供應商請求資料。這是存檔工程，不是來源認證或預測模型改動。

## 端到端流程

1. 沿用capture／manifest pin，先重驗本機原件；封裝exact allowlist、bounded ZIP_STORED，不重寫原body或receipt。
2. 只接受明確設定的私人目的地：嚴格full_name、數字repo ID、private及visibility核對；使用固定api.github.com及禁轉址的HTTP客戶端，認證只在header，錯誤只用固定代碼。
3. 使用Contents API建立一個新檔案，路徑綁定source SHA、run／attempt及manifest SHA；PUT不帶舊sha、不覆寫、不自動重試。檔案在private repo正常git commit內，並非只有未連結blob。
4. 用returned commit核對相同Contents path及blob SHA，讀回blob；核對Git blob SHA、archive SHA256、原件manifest／context，還原至新建0700目錄／0600檔案，再執行既有capture replay。
5. 成功才把blob／commit／archive及manifest雜湊交給另一個job。第二個job沒有THE_ODDS_API_KEY，從私人目的地獨立讀回同一commit及原件，不能使用採集job本機檔案取巧。

公開artifact仍只有原本兩個刪敏摘要；不加入原件、ZIP、私人庫名稱／ID、token、cache或Pages檔案。目的地及憑證只放GitHub Actions Secrets，CLI不接收token參數、不打印原始例外／HTTP body／網址／私人路徑。失敗不會產生供下一job使用的成功locator。

## 啟用所需的具體設定

這三項是**私人儲存傳輸設定**，不是要重新申請足球API。現有THE_ODDS_API_KEY沿用。

在[足球repo的Actions Secrets設定](https://github.com/CHANCHUNWA1989/football-king-report/settings/secrets/actions)新增：

| 名稱 | 內容及限制 |
| --- | --- |
| PRIVATE_ARCHIVE_REPOSITORY | 一個專用、已初始化且有預設branch的私人足球原件庫full_name，例如OWNER/PRIVATE_ARCHIVE；不能填公開足球repo或默默挪用其他系統私人庫 |
| PRIVATE_ARCHIVE_REPOSITORY_ID | 同一私人庫的固定數字ID，防止同名替換／轉移／錯誤目的地 |
| PRIVATE_ARCHIVE_TOKEN | 只允許該私人庫Contents讀寫的fine-grained token或對應App token；不要授予其他repo權限 |

密鑰由擁有人在Secrets設定，唔好貼喺聊天、公開issue或repo。現有聊天GitHub／Drive連接不會自動成為GitHub Runner可用的跨庫傳輸憑證；目前連接沒有提供Secrets管理工具，不能冒稱已自動配置。讀回job沿用同一專庫限定token；其一般GITHUB_TOKEN仍只有contents:read。

三項皆缺時，上傳明示NOT_CONFIGURED，不呼叫儲存API、不產生locator，跨job讀回跳過；這不是保存成功。只配置部分、token無權限、私人身份不符、公開庫、無預設branch或遠端錯誤均拒絕，已配置路徑的失敗會令工作流程失敗。只部署程式而未填設定，仍不能說原件已持久保存。

## 驗收界線

本機正負測試使用明示合成HTTP opener，走實際request方法／路徑、create-only寫入、commit可達性、blob下載、ZIP解包及既有capture replay；不把mock當作真實GitHub保存成功。負例包括公開／錯ID目的地、錯commit或blob、損壞bytes／manifest／context、覆寫／權限／轉址、不安全ZIP／路徑／檔案及資料洩漏。工作流程另驗證跨job依賴／hash pin、credential範圍及公開artifact allowlist。

實際私人庫設定接通後，須有真實上傳成功及另一job讀回成功的run，才可記錄跨job保存驗收；缺設定則保持未驗證。一次讀回不保證無限期保留，GitHub管理者仍能刪除庫或改可見性；客戶端只能拒絕觀察到的身份／可見性變更，不能原子鎖定遠端行政操作。它也不是獨立外部時間見證。

原件內既有source／time／durable authentication flags不改寫。私人存檔讀回成功亦不證明publisher權威、上游獨立、實際開波、90分鐘賽果、可成交報價或正EV。可信正向admission、certified-only統計／校準及足夠前瞻樣本仍未完成；0認證、HOLD／DISABLED，未證實提高預測表現。

## 官方接駁依據

- [GitHub Contents API：新建不帶舊sha、base64及commit回應](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)
- [GitHub Contents：以commit ref讀取、1–100MB的object media限制](https://docs.github.com/en/rest/repos/contents#get-repository-content)
- [Git blobs：base64下載及100MB上限](https://docs.github.com/en/rest/git/blobs#get-a-blob)

2026-10-28直接讀取官方文件；本模組另設更小的原件及封裝上限。文件檢索plugin額度不足後沒有重試或付費升級。
