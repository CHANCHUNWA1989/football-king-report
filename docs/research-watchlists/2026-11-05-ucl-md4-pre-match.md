# 足球王者｜歐聯第四輪賽前研究觀察表（香港時間 2026-11-05）

- **資料核對日期**：2026-11-04（香港時間；公開網站查閱快照，非持續實時 feed）
- **狀態**：`RESEARCH_WATCHLIST_ONLY`／`HOLD`
- **正式推介**：`DISABLED`；`positive_ev_verified=false`；`live_execution_allowed=false`
- **注意**：以下屬手動來源核對後嘅賽前分析方向，**唔係已部署足球 AI 模型計算嘅機率或者 +EV 推介**。所有賠率係公開網頁顯示嘅非可執行快照，無經官方訂閱 feed／盤口 selection ID、時間戳及可成交報價核實。賽前預計正選並非官方最終正選。

## 優先觀察賽事

| 香港開賽時間 | 賽事 | 研究方向 | 1X2 參考十進制賠率 | 單憑該賠率要打和所需勝率 | 判斷與風險 |
|---|---|---|---:|---:|---|
| 11/05 04:00 | RB 萊比錫 vs 曼城 | **曼城客勝** | 1.53 | 65.4% | 曼城此前歐聯勝波圖 2:0、AEK 5:1；萊比錫曾負科木 1:4、皇馬 1:4。曼城曾負 PSG 2:4；哈蘭特預計出場但最終正選未核實。 |
| 11/05 04:00 | 布拉格斯拉維亞 vs 阿仙奴 | **阿仙奴客勝** | 1.25 | 80.0% | 阿仙奴前三輪 2 勝 1 和，斯拉維亞未勝；但 Saka 缺陣、Saliba 有疑問，而且價格較低。 |
| 11/05 01:45 | AEK 雅典 vs 皇家馬德里 | **皇馬客勝** | 1.25 | 80.0% | 皇馬前三輪全勝，AEK 曾 1:5 負曼城；但部分皇馬球員輪休／傷缺、歷史作客希臘往績欠佳。 |

**價格只係判斷門檻：** 客勝 1.53 需要實際勝率高於約 65.4% 才有正數期望回報；1.25 需要高於 80%。**目前並無獨立驗證模型勝率，因此三項都唔能夠宣稱為正 EV 或可正式落注。**

## 次級觀察／暫不採用正式推介

| 賽事 | 候選方向 | 原因及限制 |
|---|---|---|
| 費倫巴治 vs 利物浦（11/05 01:45） | 利物浦客勝，**觀察**（約 1.53） | 利物浦歐聯 3 連勝，但 UEFA 指佢作客土耳其歷史紀錄偏弱；等最終正選及臨場價格。 |
| PSV vs 布魯日（11/05 04:00） | 兩隊入球，**只作觀察** | PSV 連續 21 場歐洲賽主場取得入球，布魯日此前攻擊數據不弱；未取得對應市場完整 bookmaker＋selection ID＋盤線＋價格，**不可作正式推介**。 |
| 多蒙特 vs 貝迪斯 | **暫不推** | 貝迪斯前三場歐聯全勝，單憑多蒙特主場熱門身份不足以證明優勢。 |
| 波圖 vs 拿玻里 | **暫不推** | 波圖前三場歐聯全負，拿玻里客場歷史差，兩邊訊號互相衝突。 |
| 朗斯 vs 科木 | **暫不推** | 客隊近期有進攻表現，但主客優勢、傷停及價格仍須專項校準。 |
| 維京 vs 沙巴 | **暫不推** | 主隊有熱門定價，但 1X2 勝率及盤口性價比缺獨立驗證。 |

## 發布前必須通過嘅閘門

1. UEFA 對照正確 `fixture_id`、主客隊、開賽時間及時區。
2. 比賽前約 60 分鐘核對**實際官方正選**；不得以 UEFA「預計正選」冒充官方正選。
3. 由有權限市場來源取得固定時間嘅 `provider/market_id/selection_id/line/side/decimal_odds`；只靠公開頁面表列賠率唔可以建立可執行訂單。
4. 使用樣本外、分市場校準嘅模型估計 `p_model`，先比較 `p_model × decimal_odds - 1`，並考慮抽水、交易限制及時效；未驗證就標記 `EV_UNVERIFIED`。
5. 任何來源過期、正式正選未出、盤線身份不明、CI 或獨立審核未過，都必須 `HOLD`。
6. 禁止自動下注、交易、合併主分支或部署；本檔案只係研究記錄，唔會自動寫入正式推薦 feed。

## 來源（截至 2026-11-04 公開查閱）

- UEFA 官方賽程與賽果：https://www.uefa.com/uefachampionsleague/news/02a8-2174c9e9019d-f909a77bd77a-1000--2026-27-champions-league-all-the-league-phase-f/
- UEFA 球隊賽程及前三輪戰績：https://www.uefa.com/uefachampionsleague/news/02a8-2176fa83582b-d99f0b27f405-1000--champions-league-league-phase-fixtures-by-team/
- UEFA 預計陣容與傷停：https://www.uefa.com/uefachampionsleague/news/02ab-21f9907f0a27-6a6a67e9775d-1000--champions-league-starting-and-predicted-line-ups-matchday-4-/
- UEFA 賽前統計：https://www.uefa.com/uefachampionsleague/news/02aa-21f10edb96af-f01ebdbd9935-1000--champions-league-matchday-4-key-stats-and-what-to-look-o/
- 參考 1X2 odds（非可交易報價／價格可隨時變動）：https://kickstein.com/en?day=2026-11-04 ；對照 https://www.betvictor.com/en-gb/sports/240/meetings/724920510/all

> 版本原則：事後按 **當時可取得** 嘅賽前證據留底，不准用最終結果倒灌事前模型；本觀察表未取得正式交易資格。
