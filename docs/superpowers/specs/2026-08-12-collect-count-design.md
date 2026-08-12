# 收藏字段（collect_count）纳入 设计稿

日期：2026-08-12
状态：设计稿（用户已确认全部决策点，待用户审阅定稿后进入实施计划）。

## 1. 背景与现状（取证）

- `video_info` 表（1443 行）当前 12 个业务字段，**无 `collect_count` 列**；
- `share_count` 列与 `items.py` 的注释均为「分享/收藏数」，但所有采集路径（爬虫 `statistics.share_count`、插件 hook JSON `stats.share_count`、详情页 DOM `video-player-share`）实际写入的都是纯分享数，**无历史混入**，注释系误导；
- 数据分布（2026-08-12 实测）：1443 行全部有至少一个互动计数（like_count>0），1377 行 like/comment/share 全有，38 行有播放量（主页/列表路径），1405 行无播放量（详情/爬虫路径）；**无全零兜底行**；
- 三条采集路径中，hook 接口 JSON（`statistics.collect_count`）与详情页 DOM（`[data-e2e="video-player-collect"]`）都能拿到收藏数；主页卡片不显示收藏数，靠 hook 补全；
- MVP 设计（2026-08-11-personal-analyzer-extension-design.md）曾明确「收藏数不采集（现有表无收藏列）」，本次将该决策反转。

## 2. 已确认决策

1. **范围**：插件路径 + 爬虫路径两端同时支持；
2. **字段语义**：跟随现有四个计数（like/comment/share/play）语义——`bigint DEFAULT '0'`；插件路径 `None`=本批未采集、upsert 跳过更新；爬虫路径接口值覆盖、缺失写 0、兜底数据 `INSERT IGNORE` 不碰已有行；
3. **历史数据**：不做专门回填，新列对存量行保持「未采集」（INSERT 未覆盖时为 NULL），靠后续插件详情同步/爬虫成功刷新自然补上；
4. **前端展示**：个人分析页 + 视频数据页接入；数据总览页（Dashboard）保持现状不动；
5. **数据库改动**：本设计中的 ALTER TABLE 语句已经用户明确授权。

## 3. 数据库变更（已授权）

```sql
ALTER TABLE video_info
  ADD COLUMN collect_count bigint DEFAULT '0' COMMENT '收藏数' AFTER share_count,
  MODIFY COLUMN share_count bigint DEFAULT '0' COMMENT '分享数';
```

- 只加列 + 改注释，不迁移数据、不删数据；
- 实测（2026-08-12）：MySQL 按 `DEFAULT '0'` 将存量 1443 行填充为 0（非 NULL）；完整度统计把 0 视为缺失（与现有计数一致），展示上等效「未采集」，不影响功能；插件路径 INSERT 显式写 NULL 的语义不变。

## 4. 爬虫路径变更

### 4.1 `douyin_spider/items.py`

- `DouyinVideoItem` 新增 `collect_count = scrapy.Field()`；
- `share_count` 字段注释「分享/收藏数」改为「分享数」。

### 4.2 `douyin_spider/spiders/douyin_video.py`

- `parse_video_data()` 在 statistics 映射处新增：
  `item['collect_count'] = statistics.get('collect_count', 0)`；
- 兜底路径（页面异常，incomplete=True）不涉及收藏字段。

### 4.3 `douyin_spider/pipelines.py`

- `build_insert_params()` 新增 `'collect_count': item.get('collect_count', 0)`；
- `upsert_sql` 与 `insert_ignore_sql` 的列清单各加 `collect_count`；
- 覆盖标准（与现有四计数一致）：正常数据全字段更新（含 collect_count，缺失写 0）；兜底数据 INSERT IGNORE 不覆盖已有行；`crawl_time` 保持首次写入不变。

## 5. 插件路径变更（`extension/content/parse.js`）

- `parseAwemeList`（hook 接口 JSON）：从 `statistics.collect_count` 提取，缺失时计入 `missing_fields`；
- `parseVideoDetail`（详情页 DOM）：从 `[data-e2e="video-player-collect"]` 提取，缺失时计入 `missing_fields`；
- `mergeCardWithHook`：透传 `collect_count: hook.collect_count`（hook 无该字段时为 undefined，上报后后端按 None 跳过更新；主页卡片本身无收藏字段）；
- `parseProfileCards`（主页卡片）不采集收藏（页面不显示），主页采集靠 hook 补全；
- `collect.js` 无需改动（merge 与详情上报自动带上新字段）。

## 6. 后端接收器 / API / 分析层变更

### 6.1 `extension_receiver.py`

- `COUNT_FIELDS` 追加 `'collect_count'`；
- `INSERT_COLUMNS` 追加 `'collect_count'`；
- `build_upsert` 无需改结构，自动获得「NULL=未采集、非 None 才更新」语义；
- `normalize_record` 自动继承计数校验（非负整数、无效返回 None 拒绝）。

### 6.2 `api.py`

- `VideoItem` 模型新增 `collect_count: Optional[int] = None`；
- `/api/videos` 的 `allowed_sort` 追加 `'collect_count'`；
- `/api/stats` 与 `StatsResponse` 不变（Dashboard 不动）。

### 6.3 `analyzer.py`

- `summarize_rows`：新增 `total_collects`（`SUM(collect_count)`）；`completeness` 新增 `collect` 维度（0/NULL 视为缺失，与现有计数一致）；
- `SORT_KEYS` 新增 `'collects': 'collect_count'`，`top_videos` 支持 `sort_by='collects'`。

## 7. 前端变更

### 7.1 `frontend/src/pages/PersonalAnalyzer.vue`

- `PersonalData.summary` 新增 `total_collects`，`top_videos` 新增 `collect_count`；
- StatCard 区新增「总收藏」卡（原 6 卡 span=4，新增后 7 卡：调整为首行 4 卡 + 次行 3 卡）；
- 互动总量图新增「收藏」项（点赞/评论/分享/收藏）；
- 数据完整度新增「收藏」行；
- Top 排序下拉新增「按收藏」（value: `collects`）；
- Top 表格新增「收藏」列。

### 7.2 `frontend/src/pages/Videos.vue`

- `VideoItem` 接口新增 `collect_count`；
- 表格新增「收藏」列；
- 排序选项新增「收藏数」（value: `collect_count`）；
- 详情抽屉「点赞/评论/分享/播放」行改为含收藏。

### 7.3 `frontend/src/pages/Dashboard.vue`

- 不变。

## 8. 测试策略（T2 严格 TDD）

- `extension/tests/parse.test.mjs`：
  - hook JSON（`parseAwemeList`）含 `statistics.collect_count` → 提取正确；缺失 → missing_fields 含 collect_count；
  - 详情页 DOM（`parseVideoDetail`）含 `video-player-collect` → 提取正确（含万/亿缩写）；缺失 → missing_fields 含 collect_count；
  - `mergeCardWithHook` 透传行为；
- `tests/test_extension_receiver.py`：
  - `collect_count` 校验（合法/负数/小数/缺失）；upsert SQL 含收藏列；None 不更新；
- `tests/test_analyzer.py`：
  - `summarize_rows` 的 `total_collects` 与 `completeness.collect`；`top_videos(sort_by='collects')`；
- `tests/test_pipelines.py`、`tests/test_spider_fallback.py`：
  - `build_insert_params` 含 `collect_count` 默认 0；兜底 item 不携带收藏；
- 回归：pytest 全量、`node --test`、`npm run build`；
- 真机（可选）：插件详情页同步后库中收藏数与页面一致。

### 8.1 真机验收（用户指定）

- **爬虫路径**：实现完成后，从历史数据中选 2 条视频（来源 `video_ids.txt` / `video_info` 表），推给爬虫跑一轮详情采集，验证 `collect_count` 随接口数据写入库中（接口有值时写入真实收藏数；被反爬拦截时走兜底路径不覆盖已有行）；该操作涉及联网启动爬虫，执行前再次向用户确认所选 2 条 video_id；
- **插件路径**：由用户手动在浏览器中验证——重新加载扩展 → 刷新抖音页面 → 在自己主页采集/详情页同步，确认收藏数入库与页面一致；本窗口完成后向用户提供验证步骤清单。

## 9. 文件结构

| 文件 | 动作 |
| --- | --- |
| MySQL `video_info` 表 | ALTER TABLE 加 collect_count + 修正 share_count 注释（已授权） |
| `douyin_spider/items.py` | 加字段 + 注释修正 |
| `douyin_spider/spiders/douyin_video.py` | statistics 提取 collect_count |
| `douyin_spider/pipelines.py` | params + 两处 SQL 列清单 |
| `extension/content/parse.js` | hook/DOM 提取 + merge 透传 |
| `extension_receiver.py` | COUNT_FIELDS / INSERT_COLUMNS |
| `api.py` | VideoItem 字段 + 排序白名单 |
| `analyzer.py` | total_collects / completeness / SORT_KEYS |
| `frontend/src/pages/PersonalAnalyzer.vue` | 总收藏卡/互动图/完整度/Top 排序与列 |
| `frontend/src/pages/Videos.vue` | 收藏列/排序/详情 |
| `tests/*` 与 `extension/tests/parse.test.mjs` | 上述新增断言 |
| `docs/superpowers/specs/2026-08-12-collect-count-design.md` | 本设计稿 |
| `docs/superpowers/plans/2026-08-12-collect-count.md` | 实施计划（下一步） |

## 10. 非目标

- 不做历史存量数据批量回填（重爬 1443 行）；
- 不动数据总览页（Dashboard）；
- 不改 `collector.py`（仅预览字段，不写库）；
- 不删数据、不改其他表结构；
- 收藏不参与互动率分子（点赞/评论/分享率维持现状，仅新增展示与排序维度）。

## 11. 风险与已知边界

- 爬虫全字段 upsert 下，若接口返回缺失 `collect_count` 会写 0 覆盖旧值——与现有四计数同一标准，抖音接口 statistics 基本恒有该字段，实际几乎不触发；
- 历史存量行收藏完整度短期显示缺失，属预期（已确认不主动回填）；
- 插件真机采集受合规边界限制（仅自己主页/详情页）。
