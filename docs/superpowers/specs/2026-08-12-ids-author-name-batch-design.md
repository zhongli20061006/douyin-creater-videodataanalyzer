# 作者昵称映射 + 收集页批量管理 id（P2 收尾增强）设计

日期：2026-08-12
状态：设计已获用户确认。

前置设计：`docs/superpowers/specs/2026-08-12-video-ids-author-design.md`（P2-B，作者归属）

## 1. 背景与目标

- 收集页作者列当前显示 `author_id`（uid 数字），体验差；历史数据 author 为空显示「未知」；
- 收集页缺少批量操作（批量切换状态/删除）。

目标：
- 作者列显示昵称：后端按 `author_id → author_name` 映射（库为真源），前端显示 `author_name || author_id || '未知'`；
- 收集页表格加多选与批量操作（批量标记待采集/已采集、批量删除）。

## 2. 实现设计

### 2.1 作者昵称映射

- 文件格式不变（仍 `id|status|author_id`）；
- 新增纯函数 `attach_author_names(items, author_map)`：给 items 每项附加 `author_name`（缺失保持空串），可单测；
- `GET /api/extension/ids`：先查 `video_info` 的 `SELECT DISTINCT author_id, author_name` 构建映射，再 `attach_author_names` 返回 items；
- 前端作者列显示 `row.author_name || row.author_id || '未知'`。

### 2.2 批量管理

- 表格加 `type="selection"` 多选列 + `onIdsSelectionChange` 记录选中行；
- 批量按钮（选中后启用）：
  - 批量标记待采集：`POST /api/extension/ids/status {video_ids: 选中, status: 'pending'}`（接口已支持批量）后刷新；
  - 批量标记已采集：同上 `status: 'done'`；
  - 批量删除：从 `idsItems` 移除选中 → `PUT /api/extension/ids` 保存 → 刷新。
- 与现有作者/状态筛选联动。

## 3. 测试策略（T2 严格 TDD）

- `attach_author_names`：有映射/无映射/缺 author_id 行；
- 回归：pytest 全量、`node --test`、`npm run build`；
- `GET /api/extension/ids` 结构变化用重启后真库验证（items 含 author_name）。

## 4. 文件结构

| 文件 | 动作 |
| --- | --- |
| `extension_receiver.py` | 新增 `attach_author_names` |
| `api.py` | GET ids 查库映射并附加 author_name |
| `frontend/src/pages/Collect.vue` | 多选列、作者昵称显示、批量按钮 |
| `tests/test_extension_receiver.py` | attach_author_names 测试 |
| `docs/superpowers/specs/2026-08-12-ids-author-name-batch-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-ids-author-name-batch.md` | 实施计划 |

## 5. 非目标

- 文件格式不变；不改插件上报链路；
- 不做按作者整组操作（筛选 + 多选已覆盖）；
- 不做「未知」自动补全（历史数据补全仍走 `backfill_authors`，用户确认后单独执行）。

## 6. 实施阶段

1. `attach_author_names` + pytest（RED → GREEN）；
2. api.py GET ids 映射接线；
3. 前端 Collect.vue 批量管理 + build；
4. 重启后端真库验证 + 全量回归；
5. 用户确认后提交。
