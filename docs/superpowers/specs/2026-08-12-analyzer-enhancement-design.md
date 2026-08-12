# 个人分析功能增强 + 分析页 UI 优化 设计稿（待用户审阅）

日期：2026-08-12
状态：设计稿，待用户审阅后定稿。已确认不做定时采集（P2-C 取消）。

## 1. 背景与数据现状（取证）

库内作者播放量缺失情况（2026-08-12 实测）：

| 作者 | 视频数 | 无播放量 | 无点赞 | 无评论 | 无分享 | 无发布时间 |
| --- | --- | --- | --- | --- | --- | --- |
| 戏京同志 | 305 | 305 | 0 | 0 | 0 | 0 |
| 柯只因 | 172 | 172 | 0 | 0 | 0 | 0 |
| Linvo说宇宙 | 141 | 141 | 0 | 0 | 0 | 0 |
| 尖头鳗 | 133 | 133 | 0 | 0 | 0 | 0 |
| 平原公子 | 60 | 60 | 0 | 0 | 0 | 0 |
| **黑白阿巴巴（自己）** | 57 | 19 | 18 | 36 | 46 | 18 |

结论：**非自己作者数据 100% 无播放量**（来源为详情页/爬虫，详情页不提供播放量）；自己的数据部分有播放量（主页采集来源）。这是数据完整度标注的核心依据。

## 2. 目标与范围

### A. 互动率指标
- 定义：点赞率 = like/play、评论率 = comment/play、分享率 = share/play（play > 0 时有效，否则不参与）；
- `summary` 新增 `engagement`：`{like_rate, comment_rate, share_rate}`（整体汇总：总点赞/总播放等）；
- 前端新增 StatCard「互动率（赞/播）」等 + Top 排序维度。

### B. 播放量月度趋势
- 新函数 `build_play_trend(rows)`：按 `publish_time` 月份汇总 `play_count`，返回 `[{month, plays}]`，升序；无发布时间或无播放量不计入；
- 前端在发布条数趋势图旁新增「每月播放量」图（面积/柱状）。

### C. Top 视频多维排序
- `GET /api/analyze/personal` 新增 `sort_by` 参数：`likes`（默认）| `plays` | `comments` | `shares` | `engagement`（互动率，play=0 排后）；
- `top_videos(rows, limit, sort_by)` 按指定字段降序；
- 前端 Top 表格上方加排序下拉。

### D. 数据完整度提示（用户重点）
- `summary` 新增 `completeness`：
  ```json
  "completeness": {
    "play":     { "missing": 19, "total": 57, "missing_rate": 0.33 },
    "like":     { "missing": 18, "total": 57, "missing_rate": 0.32 },
    "comment":  { "missing": 36, "total": 57, "missing_rate": 0.63 },
    "share":    { "missing": 46, "total": 57, "missing_rate": 0.81 },
    "publish_time": { "missing": 18, "total": 57, "missing_rate": 0.32 }
  }
  ```
- 前端新增「数据完整度」卡片：每字段缺失率进度条；
- **标注逻辑**（如实说明，不猜测是否自己）：
  - 若 `play.missing_rate >= 0.99` → 提示「该作者数据非主页采集来源（详情/爬虫），播放量无值属预期，完整度仅供参考」；
  - 否则 → 提示「播放量缺失表示该视频尚未被主页采集覆盖，可重新采集补齐」。

### E. 分析页 UI 优化（随增强一起做）
- 完整度用 `el-progress`；
- 图表配色统一到现有 tokens（主色/成功/警告）；
- 卡片间距与标题微调；Top 排序下拉；
- 不做整体重设计（保持现有页面结构）。

## 3. API 变更（向后兼容）

`GET /api/analyze/personal?author_id=xxx&sort_by=plays`：
```json
{
  "author_id": "...",
  "author_name": "...",
  "summary": { "...原有字段...", "engagement": {...}, "completeness": {...} },
  "trend": [ { "month": "2026-05", "count": 12 } ],
  "play_trend": [ { "month": "2026-05", "plays": 123456 } ],
  "top_videos": [ { "...原有结构..." } ]
}
```
- `sort_by` 非法值 → 400；
- 前端无 sort_by 时默认 likes，行为与现状一致。

## 4. 前端变更（PersonalAnalyzer.vue）

- StatCard 区新增互动率卡；
- 图表区新增播放量趋势图；
- Top 区加排序下拉；
- 新增数据完整度卡片（进度条 + 标注文案）；
- 类型定义同步扩展。

## 5. 测试策略（T2 严格 TDD）

- `tests/test_analyzer.py`：
  - `engagement`：有播放量/无播放量（None/0 不参与）；
  - `build_play_trend`：按月汇总、空值跳过、升序；
  - `completeness`：缺失计数与缺失率；
  - `top_videos` 各 `sort_by`（含 engagement 分母为 0 排后）；
- 回归：pytest 全量、`node --test`、`npm run build`；
- 真库：接口返回新字段与库一致。

## 6. 文件结构

| 文件 | 动作 |
| --- | --- |
| `analyzer.py` | engagement / play_trend / completeness / top_videos sort_by |
| `api.py` | sort_by 参数与校验、响应组装 |
| `frontend/src/pages/PersonalAnalyzer.vue` | 互动率卡/播放趋势图/排序下拉/完整度卡片/UI 微调 |
| `tests/test_analyzer.py` | 新纯函数测试 |
| `docs/superpowers/specs/2026-08-12-analyzer-enhancement-design.md` | 本设计稿 |
| `docs/superpowers/plans/2026-08-12-analyzer-enhancement.md` | 实施计划 |

## 7. 非目标

- 不做定时采集、不做收藏/涨粉等库中不存在的字段；
- 不做分析页整体重设计；
- 不改数据库结构；
- 不判断「是否自己」身份（无用户体系），完整度按字段缺失率如实标注。

## 8. 待用户确认点

1. A-E 五项是否全部纳入，还是只做其中部分；
2. D 的标注文案（非主页来源提示）是否 OK；
3. C 的排序维度是否够用。
