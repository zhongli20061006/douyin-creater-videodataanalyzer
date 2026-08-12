# video_ids.txt 作者归属 + 收集页表格（P2-B）设计

日期：2026-08-12
状态：设计已获用户确认（P2 收尾第二项，方向 A：文件带作者、接口返回作者、前端收集页升级为表格）。

前置设计：`docs/superpowers/specs/2026-08-12-video-ids-status-design.md`（P2-A，id 同步状态）

## 1. 背景与问题

- 插件上报 ids 时已带 `author_id`（`reportIds(ids, cfg.myUid)`），但后端 `append_ids_file` 丢弃了作者信息；
- 当前文件为 `id|status` 两列，241 行混合多个作者，前端收集页纯文本编辑，无法按作者查看/管理。

## 2. 目标

- 文件行格式扩展为 `video_id|status|author_id`（第三列作者，缺省 unknown，向后兼容）；
- 插件上报的新行记录作者，已存在行更新为最新采集作者；
- 接口返回作者信息；收集页升级为表格（id/状态/作者，可筛选、切状态、删行）；
- 可选：历史数据反查库补全作者（仅函数与测试，不自动改真实文件）。

## 3. 实现设计

### 3.1 文件格式

```
7628491590348742758|pending|64010164985
7628165724566059762|done|
7572455686752281290|pending
```

- 兼容解析：`id` → `(pending, unknown)`；`id|status` → `(status, unknown)`；`id|status|author` → 三列全取；
- unknown 用空串表示，前端显示「未知」。

### 3.2 纯函数（owner：`extension_receiver.py`）

| 函数 | 行为 |
| --- | --- |
| `parse_id_line(line)` | 返回 `(video_id, status, author_id)`；空行/空 id 返回 None |
| `read_ids_with_status(path)` | 返回 `[{video_id, status, author_id}]`，保序 |
| `append_ids_file(path, new_ids, author_id='')` | 新行 `id\|pending\|author_id`；已存在行重置 pending 且 author 非空时更新为最新作者；返回 `(added, total)` |
| `mark_ids_done(path, ids)` | 只改状态为 done，不动作者（内部走 `set_ids_status`） |
| `set_ids_status(path, ids, status)` | 通用批量设状态（pending/done），不存在的追加；返回变化行数 |
| `write_ids_file(path, ids)` | 前端纯 id 覆盖：保留状态+作者，新 id → `(pending, unknown)` |
| `backfill_authors(path, author_map)` | 把 unknown 行的作者按 map 补全，返回更新行数（仅函数，不自动执行） |
| `filter_pending_ids(records, requested_ids)` | 不变 |

- `_write_ids_records`：author 为空写 `id|status`，非空写 `id|status|author`。

### 3.3 API（owner：`api.py` 薄层）

- `POST /api/extension/ids`：把 `req.author_id` 传给 `append_ids_file`；
- `GET /api/extension/ids`：返回 `{total, video_ids, items}`，items 含 `{video_id, status, author_id}`（`video_ids` 保留兼容）；
- `PUT /api/extension/ids`：走 `write_ids_file`（保留状态+作者）；
- 新增 `POST /api/extension/ids/status`：body `{video_ids, status}`，status ∈ {pending, done}，调 `set_ids_status`，返回 `{updated}`。

### 3.4 前端（Collect.vue 第三个 tab 升级）

- 纯文本编辑升级为表格：视频 ID | 状态标签（待采集/已采集）| 作者（空显示「未知」）| 操作（切换状态、删除行）；
- 顶部：作者筛选下拉 + 状态筛选 + 条数统计；
- 保留「新增 ID」（粘贴多行解析）、「保存到文件」（PUT 全量，后端保留状态/作者）、「导入爬虫队列」（POST /crawl，后端只推 pending）；
- 状态切换调 `POST /api/extension/ids/status` 后刷新。

### 3.5 已知限制

- 手动粘贴新增的 id 无作者信息（unknown），保存后如需归属需由插件重新采集或后续迁移补全；
- 历史 241 行保持 unknown，反查补全为可选动作（函数就绪，执行前用户确认）。

## 4. 测试策略（T2 严格 TDD）

- `tests/test_extension_receiver.py`：
  - `parse_id_line`：三列/两列/单列/非法状态/空行；
  - `read_ids_with_status`：混合行含作者；
  - `append_ids_file`：带作者新行、已存在更新作者、计数；
  - `set_ids_status` / `mark_ids_done`：设状态不动作者、不存在追加；
  - `write_ids_file`：保留状态+作者、新 id unknown；
  - `backfill_authors`：unknown 补全、已有作者不动；
- 回归：pytest 全量、`node --test`、`npm run build`（前端类型检查）。

## 5. 文件结构

| 文件 | 动作 |
| --- | --- |
| `extension_receiver.py` | parse/read/append/write/status/backfill 改造与新增 |
| `api.py` | ids POST 传作者、GET 返回 items、新增 /ids/status |
| `frontend/src/pages/Collect.vue` | 第三个 tab 表格化 |
| `tests/test_extension_receiver.py` | 新增/更新测试 |
| `docs/superpowers/specs/2026-08-12-video-ids-author-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-video-ids-author.md` | 实施计划 |
| `README.md` | 补充作者列说明（轻量） |

## 6. 实施阶段

1. 纯函数 + pytest（RED → GREEN）；
2. api.py 接线（ids POST/GET、新增 /ids/status）；
3. 前端 Collect.vue 表格化 + build 验证；
4. README + 全量回归；
5. 用户确认后提交。
