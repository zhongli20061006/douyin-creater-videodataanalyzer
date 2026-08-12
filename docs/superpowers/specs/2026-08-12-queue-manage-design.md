# 爬虫队列管理功能设计

日期：2026-08-12
状态：设计已获用户确认（清空 + 批量移除；实测可动 Redis 队列）。

## 1. 背景与目标

现状：后端只有 `GET /api/queue/length`、`GET /api/queue/items` 与爬虫启停；前端队列监控页只能看队列、启停爬虫，无法清理误入队列或已无用的任务。

目标：
- 后端提供清空队列、按 video_id 批量移除接口（写接口带守卫）；
- 前端队列监控页加「移除选中」「清空队列」管理操作。

## 2. 实现设计

### 2.1 纯函数（owner：`queue_service.py`）

`remove_items(raws, video_ids)`：从队列原始条目（JSON 字符串列表）中移除匹配目标 video_id 的条目，**保序**；空目标返回原列表。

### 2.2 API（owner：`api.py` 薄层，均带 `verify_write_guard`）

- `POST /api/queue/clear`：`Redis DEL` 队列，返回 `{cleared: true}`；
- `POST /api/queue/remove`：body `{video_ids}`；`LRANGE` 全部 → `remove_items` 筛选 → `DEL` 后 `RPUSH` 保序重建；返回 `{removed, queue_length}`；
- Redis 不可用返回 503。

### 2.3 前端（Queue.vue）

- 队列表格加多选列，记录选中条目；
- 操作栏新增「移除选中」按钮（POST /queue/remove，按选中 video_id）；
- 新增「清空队列」按钮（Element 确认弹窗，POST /queue/clear）；
- 操作后刷新列表。

## 3. 测试策略（T2 严格 TDD）

- `tests/test_queue.py`：`remove_items` 移除匹配/空目标保全部/保序；
- 回归：pytest 全量、`node --test`、`npm run build`；
- 实测：重启后端后 curl 清空/移除真实 Redis 队列（用户已授权可动队列）。

## 4. 文件结构

| 文件 | 动作 |
| --- | --- |
| `queue_service.py` | 新增 `remove_items` |
| `api.py` | 新增 `/api/queue/clear`、`/api/queue/remove` |
| `frontend/src/pages/Queue.vue` | 多选 + 移除选中 + 清空按钮 |
| `tests/test_queue.py` | `remove_items` 测试 |
| `docs/superpowers/specs/2026-08-12-queue-manage-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-queue-manage.md` | 实施计划 |

## 5. 非目标

- 不做队列去重/暂停恢复/按任务类型筛选；
- 不改 Redis 键名与条目格式；
- 不做前端分页（队列条目数量小，现有 limit 保留）。
