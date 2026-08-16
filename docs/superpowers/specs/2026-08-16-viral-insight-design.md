# 个人分析「爆款洞察」模块 设计稿

日期：2026-08-16
状态：设计已获用户确认（方向：数据分析增强 → 爆款/异常检测 → 成熟度分桶 + 多指标百分位 → 个人分析页新增模块）。

## 1. 背景与目标

当前「个人分析」页已经能按作者展示概览卡、发布趋势、互动总量、Top 视频与数据完整度，但缺少一个明确的结论层：用户仍需要人工判断「哪条视频表现异常好 / 异常差」。本设计在现有个人分析页内新增「爆款洞察」模块，自动识别该作者视频中的**潜力爆款**与**异常偏低**视频，并给出可解释的评分原因。

目标：

- 复用现有作者下拉与日期范围筛选，不改动现有页面结构；
- 只使用 video_info 现有字段，不新增数据库列、不新增采集链路；
- 输出可解释结果，例如「播放超过同发布时长视频中 95%」。

## 2. 非目标

- 不修改数据库结构，不新增字段；
- 不引入机器学习模型或外部服务；
- 不做定时采集、不做自动推送报告；
- 不做多账号对标、不做按作者分库；
- 不新增独立路由页面，只嵌入个人分析页。

## 3. 评分算法

### 3.1 输入与清洗

输入为「按当前作者 + 日期范围过滤后的视频行」，每行至少包含：

video_id, video_title, play_count, like_count, comment_count, share_count, collect_count, publish_time

清洗规则：

1. publish_time 为空或无法解析的视频不参与评分；
2. play_count、like_count、collect_count 全部为空或 0 的视频不参与评分（评分不使用 comment/share）；
3. publish_time 晚于当前时间的记录按 0 天处理。

若清洗后样本数小于 MIN_SAMPLE_SIZE = 5，直接返回 insufficient_sample = true，top 与 bottom 为空数组，前端展示「样本不足」。

### 3.2 成熟度分桶

按 days_since_publish = (today - publish_time.date()).days 分桶：

| 桶名 | 条件 |
| --- | --- |
| 0-7天 | days_since_publish <= 7 |
| 8-30天 | 8 <= days_since_publish <= 30 |
| 31-90天 | 31 <= days_since_publish <= 90 |
| 91天以上 | days_since_publish > 90 |

### 3.3 分项指标

对每个视频计算三项原始指标：

1. play_metric = play_count
2. engage_metric = like_count / play_count（play_count > 0 时有效）
3. collect_metric = collect_count / play_count（play_count > 0 时有效；play_count 缺失或为 0 但 like_count > 0 时，退化为 collect_count / like_count，沿用现有「无播放量以点赞为分母」的规则）

某指标无法计算时标记为 null，不参与该视频的评分，权重按可用指标重新归一化。

### 3.4 百分位计算

在视频所属成熟度桶内计算每项指标的百分位（0–100，保留 1 位小数）：

percentile(v) = 100 * (less + 0.5 * equal) / bucket_size

- less：桶内该指标严格小于 v 的视频数；
- equal：桶内该指标等于 v 的视频数；
- 桶内样本数 < MIN_BUCKET_SIZE = 3 时，回退到该作者清洗后的全量样本计算。

### 3.5 综合分

score = 0.5 * play_percentile + 0.3 * engage_percentile + 0.2 * collect_percentile

当某项指标为 null 时，其余指标权重按比例重新归一化；若三项全部为 null，该视频不参与 Top/Bottom 排名。

### 3.6 Top / Bottom 与解释

- top：按 score 降序取前 limit 条（默认 10，上限 50）；
- bottom：按 score 升序取前 limit 条；
- top 与 bottom 独立计算；当样本量小于 2 × limit 时可能重叠，前端按接口返回原样展示，不做去重。
- 每条记录生成 explanation，规则：
  - 取该视频三项百分位中偏离 50 最大的那项；
  - 若该项 ≥ 50：「{指标名}超过同发布时长视频中 {percentile}%」；
  - 若该项 < 50：「{指标名}低于同发布时长视频中 {percentile}%」。
- 指标名：播放量 / 互动率 / 收藏率。

## 4. API 变更

新增只读接口：

GET /api/analyze/insights

查询参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| author_id | 是 | 作者 ID |
| start_date | 否 | YYYY-MM-DD，按 publish_time 过滤，闭区间 |
| end_date | 否 | YYYY-MM-DD，按 publish_time 过滤，闭区间 |
| limit | 否 | 默认 10，上限 50，非法值 400 |

鉴权：Depends(verify_read_guard)，与现有读接口一致。

响应示例（缩进表示 JSON）：

    {
      "author_id": "sec_uid_xxx",
      "author_name": "示例作者",
      "sample_size": 57,
      "insufficient_sample": false,
      "top": [
        {
          "video_id": "7xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
          "video_title": "示例视频标题",
          "publish_time": "2026-08-01T12:00:00",
          "days_since_publish": 15,
          "maturity_bucket": "8-30天",
          "play_count": 120000,
          "engage_rate": 0.081,
          "collect_rate": 0.019,
          "score": 88.4,
          "percentiles": { "play": 95.0, "engage": 82.5, "collect": 76.0 },
          "explanation": "播放量超过同发布时长视频中 95.0%"
        }
      ],
      "bottom": [],
      "generated_at": "2026-08-16T06:00:00"
    }

sample_size 为清洗后参与评分的视频数；insufficient_sample = true 时 top / bottom 为空。

## 5. 后端实现

- analyzer.py 新增纯函数：

    def analyze_insights(rows, now=None, limit=10) -> dict:
        """返回 insufficient_sample、top、bottom 等结构化分析结果。"""

  保持纯函数，便于单元测试；now 可注入以测试分桶边界。

- api.py 新增路由 GET /api/analyze/insights：
  1. 校验 author_id 非空，否则 400；
  2. 调用现有日期过滤逻辑（非法日期 400）；
  3. 查询该作者过滤后的行（复用现有个人分析查询，字段一致）；
  4. 调用 analyzer.analyze_insights 并组装响应；
  5. 作者不存在或无数据时仍返回 200 + insufficient_sample = true（不抛 404，避免前端额外错误分支）。

## 6. 前端实现（PersonalAnalyzer.vue）

- 在 Top 视频区域之后新增「爆款洞察」模块：
  - 两列卡片：潜力爆款 Top N、异常偏低 Bottom N；
  - 每列表格字段：视频标题、发布天数、播放量、互动率、收藏率、综合分、解释；
  - insufficient_sample 或作者未选择时显示空状态文案；
  - 复用现有 authorId / dateRange 响应式依赖，切换作者或日期时重新请求；
  - 模块独立 loading，不阻塞概览区首屏。
- frontend/src/api/index.ts 新增 getAnalyzeInsights(params) 类型定义。
- 不新增 ECharts 依赖，纯表格 + Element Plus 卡片，避免增加包体积。

## 7. 错误处理

| 场景 | 行为 |
| --- | --- |
| author_id 缺失 | 400，错误信息「author_id 不能为空」 |
| 日期非法或起止倒置 | 400，沿用现有日期过滤错误 |
| limit 非法（非正整数或 > 50） | 400 |
| 作者无数据 / 样本不足 | 200，insufficient_sample = true，列表为空 |
| 数据库异常 | 503，沿用现有全局行为 |

## 8. 测试策略（严格 TDD）

tests/test_analyzer.py 新增：

- 清洗：publish_time 为空、全指标为空/0 的记录被排除；
- 分桶边界：0/7/8/30/31/90/91 天；
- 百分位：严格小于、相等值、桶内样本不足回退全量；
- 权重归一化：缺少互动率或收藏率时，播放量权重按比例提高；
- Top/Bottom 排序与 limit 截断；
- 样本不足返回 insufficient_sample = true；
- explanation 高于/低于 50 的文案。

API 层测试：

- 非法参数 400；
- 正常响应结构与字段类型；
- 读接口鉴权与现有测试保持一致。

回归：pytest -q、cd extension && node --test、cd frontend && npm run build。

## 9. 文件结构

| 文件 | 动作 |
| --- | --- |
| analyzer.py | 新增 analyze_insights 纯函数 |
| api.py | 新增 GET /api/analyze/insights |
| frontend/src/api/index.ts | 新增接口与类型 |
| frontend/src/pages/PersonalAnalyzer.vue | 新增「爆款洞察」模块 |
| tests/test_analyzer.py | 新增纯函数测试 |
| tests/test_api_guard.py 或新建 tests/test_analyze_insights_api.py | API 测试 |
| docs/superpowers/specs/2026-08-16-viral-insight-design.md | 本设计稿 |
| docs/superpowers/plans/2026-08-16-viral-insight.md | 实施计划（下一步） |

## 10. 验收标准

1. 选择有足够样本的作者时，个人分析页出现「爆款洞察」模块，Top/Bottom 各最多 10 条；
2. 每条记录展示播放量、互动率、收藏率、综合分与解释文案；
3. 切换作者或日期后模块正确刷新；
4. 样本不足作者显示空状态而非报错；
5. 全量回归测试通过（pytest / node --test / npm run build）。

## 11. 已确认决策

- 检测范围：潜力爆款与异常偏低都要；
- 评分方式：成熟度分桶 + 多指标百分位，桶内样本不足回退全量；
- 默认权重：播放 50%、互动 30%、收藏 20%，缺失指标权重重新归一化；
- 展示位置：个人分析页新增模块，不新增独立路由；
- 不改数据库结构、不做定时采集。
