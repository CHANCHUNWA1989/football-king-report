# KPL V10：跨局歷史身分與時間證據安全修復（2026-11-03）

## 已重現的缺陷（PR391）
此前 `inspect_offline_battle` 在分析第2至第7局時，主要核查前局的事件ID、局數及兩隊已選英雄，卻未強制核對：
- 前局 `battle_id` 是否跟大場獨立索引一致
- 前局藍紅選邊是否跟逐局索引一致
- 前局 `bp_complete`、`source_authenticated` 及禁選英雄完整性
- 前局來源URL、發佈時間、擷取時間是否合理
因此，虛構或錯配前局可取得 `structural_validation_passed=True`，雖然原模組仍永久輸出 `HOLD`。

## 修正範圍
- V9正規化快照新增 `battle_id`、`league_id`，而非靠顯示中文隊名拼接歷史。
- 每個前局必須有對應 `match_index.battles[N]` 相同的 battle ID 和固定兩隊藍紅方。
- 前局須有 `bp_complete=True`、明確的外部 `source_authenticated=True` 註記、完整雙方5名選用英雄及合理禁選英雄、不相互重複；但程式 **仍不會獨立證實該註記真偽**。
- 前局來源路徑應精確對應其 battle ID，時區有效；前局發佈不能晚於擷取，前局擷取不能晚於當前局擷取。
- 第1至第6局執行同隊跨局英雄重用檢查；第7局巔峰對決容許重用，但歷史仍須完整。
- 全部結果仍固定 `status=HOLD`、`provider_data_usage_rights_verified=False`、`independent_match_authentication_verified=False`、`live_execution_allowed=False`。不存取網絡、不加入模型或盤口。

## 新增負向回歸
包含未認證前局、錯 battle ID、錯紅藍方、未完成BP、前局擷取時間晚於當局、前局英雄與禁用英雄衝突，以及非官方來源URL。正向驗證可接受合成且明確標示**外部模擬認證**的前局，仍然只能得到研究用途的結構檢查結果，不能視為真正官方證據。

## 採集及資料授權狀態
維持V9之評估：未有經獨立核實並允許自動擷取/商用/再發佈的KPL官方API特定條款。禁止將`source_authenticated=True`由payload自己設定並當成授權。現階段所有模擬資料都係本地synthetic；冇真實BP、經濟、龍區或投注賠率接通。

## 測試
```sh
python -m compileall -q ops research
python -m unittest discover -s ops/tests -p 'test_kpl_v9_offline_source_ingest.py' -v
python -m unittest discover -s ops/tests -q
```
以GitHub Actions原始日誌核實正式CI結果；測試通過唔代表真實模型準確率改善。PR392 stacked on PR391, PR391 stacked on PR390，全部應繼續保持Draft直到獨立審查及正式整合條件達標。
