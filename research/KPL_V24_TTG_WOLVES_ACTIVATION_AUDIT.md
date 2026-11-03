# KPL V24｜11月4日廣州TTG vs 重慶狼隊：真實前瞻性影子試驗啟動閘門審計

研究時點：**2026-11-03 23:03 北京時間 (UTC+08) / 15:03 UTC**。本輪Draft PR以 #413（V23）為基礎。**尚未啟動任何真實賽前影子預測**；正式投注維持 `HOLD / DISABLED`。

## A. 真實官方賽程、名單、BP：逐項核查

| 核對事項 | 確認／限制 | 來源 |
|---|---|---|
| KPL年度總決賽淘汰賽長沙站 | KPL官方2026-10-11公告 10/27–11/08 每日 **18:00** 開賽，屬賽事SESSION時間，**非精確G1實際開局** | https://3g.sina.com.cn/news/detail/5352803217709884.html |
| 當場交手身份 | 狼隊王者荣耀分部官方認證頁 **2026-11-03 20:00** 宣布 **11/04 18:00 重慶狼隊 vs 廣州TTG** | https://3g.sina.com.cn/news/detail/5361259081630430.html |
| 賽程獨立交叉參考 | WanPlus列廣州TTG vs 重慶狼隊、2026-11-04 18:00、BO7，頁面無可獨立核實發佈時間，不能自稱可信TSA | https://m.wanplus.cn/schedule/94809.html |
| 狼隊官方最近首發公告 | 2026-11-02 狼隊對**北京JDG**：清清、皖皖、紫幻、道崽、信。**只屬11/02該場** | https://3g.sina.com.cn/news/detail/5360745601827581.html |
| 廣州TTG官方早前首發日 | 2026-10-31 KPL官方公布TTG對**長沙TES.A**首發；**不等於11/04當場首發** | https://3g.sina.com.cn/news/detail/5360020775504033.html |
| 9月12日TTG vs 狼隊BP | 可搜尋到2026KPL**夏季賽總決賽**逐局BP；屬另一次賽事、不同版本／場次，**絕不可當11/04的G1 BP** | https://sina.cn/news/detail/5342391771075291.html |
| 11/04雙方正式上場五人 | 截至本輪搜尋，**未找到兩隊針對當場、具可交叉核實官方公告的五人首發** | 不提供臆測名單 |
| 11/04 G1完整官方BP、精確G1開局／觀測時間、官方唯一series/battle ID | **未取得** | 不使用舊場BP、18:00賽事排程冒充G1開始 |
| 正式合法資料供應者、獨立TSA及完整撤銷狀態、可證明的真實KPL樣本外模型校準 | **未取得** | 不發佈真實概率／正EV |

**來源訂正：** V23引用新浪的聚合新聞頁，不如直接引用當事戰隊認證原帖。V24更新 `research/kpl_v23_20261104_ttg_wolves_fixture.json`，將狼隊預告URL改為 `https://3g.sina.com.cn/news/detail/5361259081630430.html`，仍保留 `independently_authenticated=false`，因URL本身不能由程式獨立驗證作者、時間、資料權利。

### 狼隊前一場首發非本場預測依據
`research/kpl_v24_20261104_ttg_wolves_readiness.json` 明確收錄11/02狼隊對北京JDG首發資訊為 `previous_match_lineup_context`，並設 `usable_for_current_match=false`；11/04對廣州TTG雙方實際首發為空陣列、BP及官方系列賽ID為null，未取得權利／真實樣本外回測及獨立TSA一律null，**不得填入過往英雄陣容當作已鎖BP**。

## B. V24啟動閘門：只審核、不自動登記

新增 `research/kpl_v24_trial_activation_gate.py`：

```python
audit_trial_activation(fixture, readiness, *, now=None,
  existing_trial_dir=None, timestamp_receipts=None,
  tsa_trust=None, revocation_crl_pem=None)
```

設計分三類：

1. **賽事來源及identity gate**：以V23多來源比對驗證同一BO7賽程聲稱，確保不晚於當前審核時間；本程式唔直接連線或驗證來源身份。應以官方唯一series ID及精確Game1開始時刻代替易混淆的18:00 session。
2. **同一場專屬陣容／BP及能力 gate**：需兩隊針對**同一series ID及11/04當日**的五位置首發；五名選手ID不得重複，發佈時間須可觀測且比賽未開始。G1必須同一series的5ban/5pick各隊完整資料、藍紅及觀測截止時間（本輪欄位只驗隊伍、選擇列表與時間相容，未宣稱對應實際藍紅）；BP鎖定及擷取必須在當前時點之前、早於實際G1開局。其他賽事首發/BP輸入會被拒絕。
3. **模型、法律、真正TSA evidence gate**：模型須有同BP鎖定資訊階段的最少40個獨立BO系列賽／120小局對照基線及分群證據；資料權利至少有研究用途之合約摘要及期間聲稱；如已有V20試驗，時間戳證據只能透過**直接呼叫V22對實際檔案核對RFC3161原始請求/token/nonce**，不能相信JSON裏的 `verified=true`。即使密碼學核對相容，若TSA信任根授權、完整CRL/OCSP及送達證據未經獨立審核，絕不宣稱賽前獨立見證成功。

### 為何純程式無法允許真實啟動？

GitHub repo和caller本地文件**無法獨立授予KPL官方來源認證、資料使用權、TSA Root來源可信性或真實模型樣本外校準**。V24因此採取一個有意保守的雙重防線：

- 即使有人填齊所有格式欄位、寫出看似極佳Brier、甚至用合成TSA簽出正確Token，最多得到 `structural_inputs_complete=true` 或 `tsa_crypto_locally_consistent=true` **技術診斷**；
- 始終 `status=HOLD`、`activation_allowed=false`、`registration_created_by_gate=false`、`trial_started_by_gate=false`、`real_kpl_forecast_count_created=0`、`real_kpl_accuracy_verified=false`、`positive_ev_verified=false`、`live_execution_allowed=false`、`production_recommendations=DISABLED`。

**V24從未呼叫 `register_shadow_trial`、`submit_shadow_decision`、任何TSA API、賽事BP API或投注接口。** 全部只係離線審核，唔係已經開始嘅真實試驗。若將來取得有效來源、正式授權及獨立TSA服務，仍需建立外部可信審核／先登記後見證流程；不得私自取消此HOLD保護。

## C. 驗收

- `ops/tests/test_kpl_v24_trial_activation_gate.py`：**33項**真實賽程候選 + 合成偽造攻擊測試。
- 包含：V23官方原帖直接來源、狼隊11/02對JDG的過期首發、TTG/狼隊11/04同場身份、9月夏季賽BP不可回收、錯系列賽ID、錯局號、錯時間、重複英雄、模型假正Brier、過期權利聲稱、自稱官方認證／TSA及V20註冊、假的本地V22簽章結果、時間到期、重複JSON key、賠率/勝者偷偷加入欄位及完全不自動註冊。
- `python -m unittest discover -s ops/tests -p 'test_kpl_v24_trial_activation_gate.py' -v`
- `python -m unittest discover -s ops/tests -q`
- `python -m research.kpl_v24_trial_activation_gate research/kpl_v23_20261104_ttg_wolves_fixture.json research/kpl_v24_20261104_ttg_wolves_readiness.json`

CLI會讀取當時機器UTC時鐘；若賽事已開始，應拒絕稱之為未來准入。測試使用已標明的2026-11-03T15:05Z和2026-11-04T09:45Z合成審核時點，**不等於真實開賽前完成任何預測或賠率判斷**。

## D. 唯一正確結論
**2026-11-04 18:00 TTG vs 狼隊：賽程已可公開交叉核查；本輪可用的當場首發、BP、外部TSA、授權、模型校準證據仍欠缺，故 `HOLD / DISABLED`。沒有真正V20試驗登記，亦無一筆真實KPL賽前概率封存。**

PR為獨立Draft，以上游#413及更早研究PR為base，不合併main，不變更正式投注。後續只在獨立來源、可信時間、官方BP及授權取得後再考慮正式前瞻試驗。
