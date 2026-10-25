# 重用成熟足球系統做法：三市場共用的歧義隔離

## 重用取向及授權

沿用已讀過的公開參考，不重新搜集同一批資料：

- [Penaltyblog](https://github.com/martineastwood/penaltyblog) 提供入球模型、評分與回測元件。
  本輪另外直接讀取其 [LICENCE](https://github.com/martineastwood/penaltyblog/blob/master/LICENCE)：
  Copyright 2021 Martin Eastwood；MIT 條款容許使用、複製、修改及合併，但複製實質部分須保留
  copyright 與 permission notice。軟件授權不等於供應商資料權利或實盤盈利證據。
- [goalmodel](https://github.com/opisthokonta/goalmodel) 原始 README 已描述不同入球模型、
  時間權重及樣本外 Log／Brier／RPS 比較。這些方法可作獨立實作及新 challenger 候選；
  本輪未核實其整庫程式授權，不把它的源碼整批搬入本項目。

現有封存、前瞻比較、Log Loss／Brier／RPS 元件繼續重用；不因外部套件也提供同功能而
建立第二套流程。本次未複製第三方源碼、安裝依賴或改動模型權重；外部模型及回測表現
不會被列成本系統已達標證據。

## 本次落地：一次修共用入口，現有消費者直接受益

將 PR327 已驗收的「先隔離全部歧義 scope，再輸出觀察」方式用於
`market_quote_gate.extract()`，涵蓋 h2h／spreads／totals：

- 相同 native event ID 的全部副本隔離；同 event 的重複 bookmaker key 隔離；
  同 bookmaker 的重複 market key 隔離，不能拼接不同 block 或不同更新時間的殘缺側。
- 單一 market block 內同 side／line 的重複原始 outcome（包括其中一條 price 壞掉）
  污染該 line 全組，不能 first-wins 丟棄矛盾後向下游提供假乾淨 pair。
- 以同一 signed HOME spread 座標識別讓球組：HOME 的 point 或 AWAY 的負 point。
  HOME -0.25 與 HOME +0.25 是不同盤；原用 abs(point) 會合併兩盤而漏算，現分開。
  gate 與完整組統計沿同一 quarter units 精度契約分組，原始 point 值保留不重寫。
  其他合法博彩公司、市場或盤線保留，沒有整批清空所有獨立來源。

同一改動透過既有 `private_multi_market_audit`、`verified_market_pipeline`、
`integrated_market_consensus` 及 opt-in sampler 消費；沒有新增孤立工具。
partial 合法觀察的舊診斷契約保留，完整市場統計仍由其既有 consumer 驗證雙側／三側。
duplicate quote 拒絕數現計整個被污染 line 的觀察，duplicate event 數計全部隔離副本；
不再用只拒絕第二筆的數字掩蓋 first-wins 行為。

## 已重現及驗收

舊程式會將兩個同 key bookmaker 或重複 market blocks 的半邊資料拼成
`h2h=1/spreads=1/totals=1`，實際沒有任何原始 block 完整；亦會在完整
Over／Under 後多一條矛盾 Over 時，丟棄第三條仍報完整 totals。
新測試先重現上述失敗，再從現有 consumer 驗證拒絕、輸入順序不影響結果、
獨立 book／line 保留、原價／book 名不進公開彙總，以及所有安全旗號維持 false。
opt-in 測試只用 mock，確認原請求及配額保護未變。

## 本次沒有完成的部分

未擴大採集、API 配額、地區或排程，沒有手動 provider 探測，沒有改寫歷史封存。
沒有新增永久私人保存、可信賽果 admission、認證統計或模型校準。
報價結構驗證不證明實際成交、來源獨立或實際開波時間。
新鮮度、時序、in-play 標示及正式推薦 HOLD／DISABLED 契約保留。
本次提高資料處理一致性，未證實預測命中率或盈利能力提升。
