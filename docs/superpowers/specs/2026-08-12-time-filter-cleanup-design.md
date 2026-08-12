# 按发布时间范围检索 + 定时清理 + 个人分析标注 设计稿

日期：2026-08-12
状态：设计稿（用户已确认全部决策点，待用户审阅定稿后进入实施计划）。

## 1. 背景与现状（取证）

- `video_info` 表含三个时间字段：`publish_time`（发布时间）、`crawl_time`（采集时间）、`update_time`（更新时间）；
- 现有查询接口均无时间范围过滤：`GET /api/videos`（搜索/排序/分页）、`GET /api/stats`（全局统计）、`GET /api/analyze/personal`（按作者聚合）；
- `analyzer.summarize_rows` 的互动率：`like_rate=like/play`；评论/分享率在无播放量时退化以点赞为分母（既有用户规则）；**尚无收藏率**；
- 前端个人分析页已有「非主页来源」提示（基于 `play.missing_rate >= 0.99`），但未标注互动率的计算标尺；
- 项目无定时任务基础设施（FastAPI + uvicorn 常驻进程，有 Redis）；数据库结构改动需用户授权（本设计不涉及改表）。

## 2. 已确认决策

1. **时间检索**：按 `publish_time` 自定义起止日期（闭区间），作用范围 = 视频数据页 + 数据总览 + 个人分析（三处）；
2. **定时清理（升级版）**：后端内置定时任务，每 30 天执行一次；**按作者维度精准清理**——作者选择器支持「全部作者」或**多选指定作者**；删除条数可自定义（前端填写，默认 200，存 Redis 持久化）；规则：被选中作者中，行数 > 条数 N 的按 `update_time` 升序删最旧 N 条，行数 ≤ N 不删；「全部作者」= 遍历所有作者各自按规则执行；手动开关、默认关闭；开关与配置存 Redis；
3. **开关入口**：数据质量页 + 视频数据页各放一套控件（开关 + 作者多选 + 条数，共用同一 Redis 状态，两侧同步）；
4. **个人分析标注**：非本人数据（play 缺失率 >= 0.99，复用现有判断）时，标注「分享率/收藏率以点赞为分母计算」；同时新增**收藏率**指标（`collect_rate`，与评论/分享率同一退化规则）；
5. 清理执行前完整备份待删行并写日志，可恢复。

## 3. 时间检索设计

### 3.1 后端参数（三个接口统一）

- `GET /api/videos`、`GET /api/stats`、`GET /api/analyze/personal` 新增可选参数：
  - `start_date`：`YYYY-MM-DD`，`publish_time >= start_date 00:00:00`；
  - `end_date`：`YYYY-MM-DD`，`publish_time <= end_date 23:59:59`；
- 校验：格式非法或 `start_date > end_date` → 400；缺省 = 不过滤（行为与现状一致）；
- 组合语义：
  - `/api/videos`：时间过滤与 search/sort_by/order/分页叠加；
  - `/api/stats`：统计 SQL 的 `WHERE` 增加 `publish_time` 范围；
  - `/api/analyze/personal`：先按 author_id + publish_time 范围取行，summary/trend/play_trend/top_videos 全部基于过滤后的行。

### 3.2 前端

- 视频数据页、数据总览页、个人分析页各加日期范围选择器（起止日期 + 快捷「本月」）；
- 无日期 = 不过滤；切换日期后重新加载数据；
- 个人分析页的日期选择器与作者选择、排序下拉组合。

## 4. 定时清理设计

### 4.1 规则

- 开关开启时：后台循环任务每天检查一次，距 `last_clean_time`（Redis）满 30 天则执行；
- 配置读取（Redis）：`douyin:cleanup_enabled`（0/1）、`douyin:cleanup_last_time`（ISO 时间）、`douyin:cleanup_batch_size`（条数，默认 200）、`douyin:cleanup_authors`（指定作者 id 列表，JSON 数组；空 = 全部作者）；
- 执行：取全量行 → 按作者分组 → 只处理被选中作者（空 = 全部）→ 每组行数 > N 时取 `update_time` 升序最旧 N 条为待删 → 全部待删行一次性完整备份 → `DELETE` → 更新 `last_clean_time`；
- 没有任何待删行时记录日志跳过，不更新 `last_clean_time`（下一周期再检查）；
- 常量：`CLEANUP_INTERVAL_DAYS = 30`；`CLEANUP_BATCH_SIZE` 默认 200 仅作 Redis 缺省值；
- API：`GET /api/cleanup/status`（开关+上次执行时间+条数+作者列表）、`POST /api/cleanup/toggle`（`{enabled: bool}`）、`POST /api/cleanup/settings`（`{batch_size: int, authors: list[str]}`，写接口走令牌守卫；batch_size 限制 1-1000，authors 为空=全部）；
- 备份目录：项目外默认路径（常量 `CLEANUP_BACKUP_DIR`，默认系统临时目录 `douyin_cleanup_backup`），文件名含时间戳；备份格式 CSV（video_id/标题/作者/互动/时间字段全集）。

### 4.2 边界与容错

- 后端重启：循环任务随进程重新注册，Redis 中的开关/条数/作者/上次执行时间不丢；
- 执行失败（DB 断开、备份失败）：记录日志，不更新 `last_clean_time`，下个周期重试；
- 备份失败时**不删除**（先备份后删除，保证可恢复）。
- 作者选择器数据源：`GET /api/analyze/authors`（已有，含 author_id/author_name/count）；
- 前端控件：条数用 `el-input-number`（1-1000，默认 200），作者用 `el-select multiple filterable`（空=全部作者），两侧页面共用同一 Redis 状态。

## 5. 个人分析标注与收藏率

- `analyzer.summarize_rows` 的 `engagement` 新增：
  ```python
  'collect_rate': _rate(total('collect_count'), total('play_count') or total('like_count')),
  ```
  （与评论/分享率同一退化规则：无播放量时以点赞为分母；播放量与点赞均为 0 → None）
- 前端个人分析页：
  - 互动率卡片区新增「收藏率」卡；
  - 非本人数据（`play.missing_rate >= 0.99`）时，互动率卡下方显示标注：「该作者数据非主页采集来源，播放量缺失；分享率、收藏率以点赞数为分母计算」；
  - 现有「非主页来源」完整度提示保留。

## 6. 测试策略（T2 严格 TDD）

- 后端纯逻辑（`analyzer.py` / 新增 `cleanup_service.py`）：
  - 日期参数校验与过滤条件构建（含非法格式、起止倒置）；
  - `summarize_rows` 的 `collect_rate`（有播放/退化以点赞/两者为 0 → None）；
  - 清理选择逻辑：按作者分组、指定作者过滤（空=全部）、每组行数 > N 取最旧 N 条、行数 ≤ N 跳过、30 天到期判断、开关判断、备份先于删除；
- API 层（`tests/test_api_guard.py` 或新增）：三接口时间参数（正常过滤、缺省、非法 → 400）、toggle/settings 接口守卫、settings 参数校验（batch_size 越界 → 400）；
- 前端：`npm run build` 验证三页选择器与清理控件（无单测基建）；
- 回归：pytest 全量、`node --test`、`npm run build`；
- 真机（可选）：面板设置日期范围看数据变化；开启清理开关观察下一次到期执行日志（30 天不等待，可用测试注入缩短间隔验证）。

## 7. 文件结构

| 文件 | 动作 |
| --- | --- |
| `api.py` | 三接口时间参数 + 清理 status/toggle/settings 端点 |
| `analyzer.py` | `engagement.collect_rate` |
| `cleanup_service.py`（新增） | 清理规则/调度/备份/删除纯逻辑 |
| `frontend/src/pages/Videos.vue` | 日期范围选择器 + 清理控件（开关/作者多选/条数） |
| `frontend/src/pages/Dashboard.vue` | 日期范围选择器 |
| `frontend/src/pages/PersonalAnalyzer.vue` | 日期范围选择器 + 收藏率卡 + 非本人标注 |
| `frontend/src/pages/Quality.vue` | 清理控件（开关/作者多选/条数） |
| `tests/*`（新增 test_cleanup_service.py 等） | 上述测试 |
| `docs/superpowers/specs/2026-08-12-time-filter-cleanup-design.md` | 本设计稿 |
| `docs/superpowers/plans/2026-08-12-time-filter-cleanup.md` | 实施计划（下一步） |

## 8. 非目标

- 不做其他时间字段过滤（仅 `publish_time`）；
- 不改数据库结构（开关/上次执行时间存 Redis，不建表）；
- 不引入新依赖（定时用后端内置线程循环）；
- 不做清理任务的前端手动"立即执行"按钮（仅开关，执行由后台调度）；如需手动触发另议；
- 不动数据总览页布局（仅加日期选择器与统计过滤）。

## 9. 风险与已知边界

- 清理为破坏性操作：默认关闭；开启后每 30 天按作者规则删除（可配置条数与作者范围）；删除前备份 + 日志；备份失败不删；
- "每 30 天"从上次执行时间起算（Redis 持久化），后端重启不重置；
- 单作者行数 ≤ 条数 N 时不删该作者（已确认）；「全部作者」= 遍历所有作者各自执行；
- 个人分析标注依赖 `play.missing_rate >= 0.99` 的既有判断，与「非主页来源」提示同一数据源，语义一致。
