# 个人分析「最近同步」语义修正设计

日期：2026-08-11
状态：方向已由用户确认（P1 待办项，交接明确「考虑用 MAX(update_time) 反映爬虫刷新而非仅 crawl_time」），本文件为实施真源。

## 1. 背景与问题

看板「个人分析」的 `latest_sync` 当前取 `MAX(crawl_time)`。经取证：
- 表结构：`crawl_time` 为 `DEFAULT CURRENT_TIMESTAMP`（无 ON UPDATE），`update_time` 为
  `DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`（任何写入/更新自动刷新）；
- 插件链路（`extension_receiver.build_upsert`）：`ON DUPLICATE KEY UPDATE ... crawl_time=NOW(), update_time=NOW()`，
  两个时间都会刷新；
- 爬虫链路（`douyin_spider/pipelines.py` 的 upsert）：`ON DUPLICATE KEY UPDATE ... update_time = NOW()`，
  **不更新 crawl_time**。

结论：`MAX(crawl_time)` 无法反映爬虫对已存在记录的刷新；`MAX(update_time)` 能同时反映插件与爬虫两条链路的任何写入/更新。

## 2. 目标

- `latest_sync` 改为 `MAX(COALESCE(update_time, crawl_time))`（老数据缺失 update_time 时回退 crawl_time）；
- 接口响应字段名与前端展示不变（零前端改动）。

## 3. 实现设计

- owner：`analyzer.py` 的 `summarize_rows`，`latest_sync` 取值字段从 `crawl_time` 改为 `update_time`（含 COALESCE 回退）；
- `api.py` 的 `/api/analyze/personal` 已是 `SELECT *`，查询无需改动；
- 不改表结构、不改爬虫/插件写入逻辑、不改接口字段名。

## 4. 测试策略（T2 严格 TDD）

- `tests/test_analyzer.py`：
  - fixture `make_row` 增加 `update_time`；
  - 用例 1：crawl_time 更旧、update_time 更新 → `latest_sync` 取 MAX(update_time)（模拟爬虫刷新）；
  - 用例 2：update_time 缺失 → 回退 crawl_time；
  - 用例 3：空行 → `latest_sync is None`；
- 回归：pytest 全量、`node --test`、`npm run build`（前端未改，构建用于确认基线）。

## 5. 文件结构

| 文件 | 动作 |
| --- | --- |
| `analyzer.py` | `summarize_rows` latest_sync 取 update_time（COALESCE 回退 crawl_time） |
| `tests/test_analyzer.py` | fixture 与断言更新 |
| `docs/superpowers/specs/2026-08-11-latest-sync-update-time-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-11-latest-sync-update-time.md` | 实施计划 |

## 6. 非目标

- 不改表结构 / 迁移；
- 不改爬虫与插件写入逻辑；
- 不改接口字段名与前端展示；
- 不引入新依赖。
