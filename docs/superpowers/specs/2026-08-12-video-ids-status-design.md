# video_ids.txt 同步状态管理（P2-A）设计

日期：2026-08-12
状态：设计已获用户确认（P2 起步项 A：给每个 id 加同步状态，爬虫只推待采集 id，推送后标记已采集）。

## 1. 背景与问题

- `video_ids.txt` 目前是纯 id 列表（241 行，混合多个作者），无作者归属、无同步状态；
- 爬虫消费方式：前端「导入爬虫队列」→ `POST /api/crawl` 把 id 推入 Redis 队列 → `spider/start` 启动 Scrapy；
- 现状每次导入都推**全部** id，同一批 id 会被重复爬取；
- 无「已消费」标记机制。

## 2. 决策点（用户已拍板）

- **方案**：P2-A 起步，id 同步状态管理；
- **标记时机**：爬虫启动、id 被推入队列时标记为「已采集」（方案 A，非爬虫成功回写）；
- **非目标**：前端状态展示/重置按钮、按作者分区、定时采集、失败重试、三态（queued）。

## 3. 实现设计

### 3.1 文件格式（向后兼容）

每行 `video_id|status`，status ∈ `{pending, done}`：
```
7628491590348742758|pending
7628165724566059762|done
```
- 纯 id 行读取时视为 `pending`（现有 241 行无需迁移，读兼容、写时升级格式）；
- 非法状态值按 `pending` 处理；空行/空 id 行忽略。

### 3.2 纯函数（owner：`extension_receiver.py`，全部可单测）

| 函数 | 行为 |
| --- | --- |
| `parse_id_line(line)` | 返回 `(video_id, status)`；空行/空 id 返回 `None`；纯 id → `pending`；`id\|bad` → `pending` |
| `read_ids_with_status(path)` | 逐行解析，返回 `[{video_id, status}]`，保序 |
| `read_ids_file(path)` | 保持返回纯 id 列表（基于 with_status 取 id），现有调用方/前端零改动 |
| `append_ids_file(path, new_ids)` | 新 id 追加 `pending`；已存在 id 一律重置为 `pending`（插件又采集到 = 值得再爬）；返回 `(added, total)`，added = 新增行数 |
| `mark_ids_done(path, ids)` | 已存在 id 置 `done`；不在文件中的 id 追加为 `done`；返回实际变化行数 |
| `write_ids_file(path, ids)` | 前端纯 id 全量覆盖时：保留旧文件状态（存在则保留）、新 id → `pending`、删除的移除；返回写入条数 |
| `filter_pending_ids(records, requested_ids)` | 返回 requested 中状态为 `pending` 或不在文件中的 id（视为新可推），保序去重 |

- `merge_ids` 在改造后无生产引用，随本改动删除（含其测试），避免死代码。

### 3.3 API 接线（owner：`api.py` 薄层）

- `POST /api/crawl`：先 `filter_pending_ids(读文件, 规范化后的 video_ids)` → 只推可推 id → 推送成功后 `mark_ids_done`；
  响应 `CrawlResponse` 增加 `skipped` 字段（默认 0，跳过已采集数），前端无需改动；
- `POST /api/extension/ids`（插件上报）与 `PUT /api/extension/ids`（前端编辑保存）：走改造后的 append / write，签名不变；
- `GET /api/extension/ids`：返回不变（纯 id 列表）；
- Redis 不可用时 `POST /api/crawl` 返回 503 且**不标记** done（推送与标记同事务语义：先推后标）。

### 3.4 已知限制

- 强制重爬某条已 `done` 的 id：编辑文件删除该行后重新导入（视为新 id 重推）；
- 前端不展示状态（本轮非目标），文件层可直接查看 `video_ids.txt` 确认。

## 4. 测试策略（T2 严格 TDD）

- `tests/test_extension_receiver.py`：
  - `parse_id_line`：纯 id / `id|pending` / `id|done` / `id|bad` / 空行 / 空 id；
  - `read_ids_with_status`：混合行解析；
  - `read_ids_file`：兼容既有测试（纯 id 行 / 空行跳过 / 缺失文件）；
  - `append_ids_file`：新 id 追加 pending、已存在重置 pending、计数与文件内容、缺失文件创建、无 tmp 残留；
  - `mark_ids_done`：存在置 done、新 id 追加 done、返回变化数；
  - `write_ids_file`：保留状态、新 id pending、删除移除、空清空；
  - `filter_pending_ids`：pending 可推、done 跳过、不在文件可推、保序去重；
  - 删除 `merge_ids` 相关 3 个测试。
- 回归：pytest 全量、`node --test`、`npm run build`（前端未改，基线确认）。
- `POST /api/crawl` 的 Redis 推送不自动实测（避免污染 Redis 队列），由纯函数层覆盖筛选/标记逻辑，真机验收留待用户。

## 5. 文件结构

| 文件 | 动作 |
| --- | --- |
| `extension_receiver.py` | 新纯函数 + append/write 改造 + 删除 merge_ids |
| `api.py` | `/api/crawl` 筛选+标记接线、CrawlResponse 加 skipped |
| `tests/test_extension_receiver.py` | 新增/更新测试、删除 merge_ids 测试 |
| `docs/superpowers/specs/2026-08-12-video-ids-status-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-video-ids-status.md` | 实施计划 |
| `README.md` | 补充 id 状态说明（轻量） |

## 6. 实施阶段

1. 纯函数 + pytest（RED → GREEN）；
2. `api.py` `/api/crawl` 接线 + CrawlResponse.skipped；
3. README 更新 + 全量回归；
4. 用户确认后提交。
