# 爆款洞察 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在个人分析页新增「爆款洞察」模块，用成熟度分桶 + 多指标百分位识别潜力爆款与异常偏低视频。

**Architecture:** 在 analyzer.py 增加纯函数 analyze_insights 完成评分；api.py 新增只读接口 /api/analyze/insights 复用现有作者/日期过滤与鉴权；前端在 PersonalAnalyzer.vue 增加模块并通过 api/index.ts 的 getAnalyzeInsights 请求数据。

**Tech Stack:** Python 3.13 / FastAPI / pytest · Vue 3 / TypeScript / Element Plus

---

## 执行前须知

- 工作目录：D:/DjangoProject/PythonProject11
- 本项目 git 命令必须带 -c safe.directory=D:/DjangoProject/PythonProject11。
- git 写操作（add/commit）需用户确认；如果执行环境没有可用的 shell，先跳过提交步骤并向用户说明。
- 验证命令优先使用项目现有 Python 解释器 .venv/Scripts/python.exe。
- 数据库结构不变，不新增列；本计划只改代码与文档。

---

### Task 1: analyzer.py 增加 analyze_insights 纯函数

**Files:**
- Modify: analyzer.py
- Test: tests/test_analyzer.py

- [ ] **Step 1.1: 在 tests/test_analyzer.py 顶部补充导入与测试数据辅助函数**

在文件顶部把 import 行改为：

```python
from datetime import datetime, timedelta

from analyzer import analyze_insights, build_play_trend, build_trend, summarize_rows, top_videos
```

在 make_row 函数之后追加以下辅助函数：

```python
NOW = datetime(2026, 8, 16, 12, 0, 0)


def rows_with_days(days_list):
    """按发布天数生成可评分行，play/like/collect 成比例，保证互动率、收藏率可计算。"""
    rows = []
    for i, days in enumerate(days_list, start=1):
        play = i * 100
        rows.append(make_row(
            video_id=str(i),
            publish_time=NOW - timedelta(days=days),
            play_count=play,
            like_count=int(play * 0.1),
            collect_count=int(play * 0.05),
        ))
    return rows
```

- [ ] **Step 1.2: 写失败测试（样本不足 / 分桶 / Top-Bottom / 回退 / 权重归一化 / 解释）**

在 tests/test_analyzer.py 末尾追加：

```python
def test_analyze_insights_insufficient_sample():
    rows = [
        make_row(video_id='1', publish_time=NOW - timedelta(days=1), play_count=100),
        make_row(video_id='2', publish_time=NOW - timedelta(days=2), play_count=200),
    ]
    result = analyze_insights(rows, now=NOW)
    assert result['insufficient_sample'] is True
    assert result['sample_size'] == 2
    assert result['top'] == []
    assert result['bottom'] == []


def test_analyze_insights_skips_missing_publish_time_and_empty_metrics():
    rows = [
        make_row(video_id='1', publish_time=None, play_count=100),
        make_row(video_id='2', publish_time=NOW - timedelta(days=1), play_count=0, like_count=0, comment_count=0, share_count=0, collect_count=0),
    ]
    rows += rows_with_days([1, 2, 3, 4, 5])
    result = analyze_insights(rows, now=NOW)
    assert result['sample_size'] == 5


def test_analyze_insights_bucket_boundaries():
    rows = rows_with_days([0, 7, 8, 30, 31, 90, 91])
    result = analyze_insights(rows, now=NOW)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    assert by_id['1']['maturity_bucket'] == '0-7天'
    assert by_id['2']['maturity_bucket'] == '0-7天'
    assert by_id['3']['maturity_bucket'] == '8-30天'
    assert by_id['4']['maturity_bucket'] == '8-30天'
    assert by_id['5']['maturity_bucket'] == '31-90天'
    assert by_id['6']['maturity_bucket'] == '31-90天'
    assert by_id['7']['maturity_bucket'] == '91天以上'


def test_analyze_insights_top_and_bottom_sorted_by_score():
    rows = rows_with_days([5, 5, 5, 5, 5])
    result = analyze_insights(rows, now=NOW, limit=3)
    assert [item['video_id'] for item in result['top']] == ['5', '4', '3']
    assert [item['video_id'] for item in result['bottom']] == ['1', '2', '3']


def test_analyze_insights_falls_back_to_global_when_bucket_too_small():
    rows = rows_with_days([1, 1, 1, 1, 10, 10])
    result = analyze_insights(rows, now=NOW, limit=10)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    assert by_id['6']['percentiles']['play'] == 91.7


def test_analyze_insights_renormalizes_weights_when_engage_missing():
    rows = rows_with_days([5, 5, 5, 5])
    rows.append(make_row(
        video_id='zero-play',
        publish_time=NOW - timedelta(days=5),
        play_count=0,
        like_count=10,
        collect_count=1,
    ))
    result = analyze_insights(rows, now=NOW, limit=10)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    item = by_id['zero-play']
    assert item['percentiles']['engage'] is None
    assert item['score'] is not None


def test_analyze_insights_explanation_uses_most_extreme_metric():
    rows = rows_with_days([5, 5, 5, 5])
    rows.append(make_row(
        video_id='zero-play',
        publish_time=NOW - timedelta(days=5),
        play_count=0,
        like_count=100,
        collect_count=0,
    ))
    result = analyze_insights(rows, now=NOW, limit=10)
    top = result['top'][0]
    bottom = result['bottom'][0]
    assert '超过' in top['explanation']
    assert '低于' in bottom['explanation']
```

- [ ] **Step 1.3: 运行测试确认失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: FAIL，报 ImportError: cannot import name 'analyze_insights'。

- [ ] **Step 1.4: 实现 analyzer.py 中的 analyze_insights**

在 analyzer.py 顶部常量区（TOP_VIDEOS_LIMIT 之后）增加：

```python
INSIGHTS_MIN_SAMPLE_SIZE = 5
INSIGHTS_MIN_BUCKET_SIZE = 3
INSIGHTS_MAX_LIMIT = 50
INSIGHTS_WEIGHTS = {'play': 0.5, 'engage': 0.3, 'collect': 0.2}
INSIGHTS_METRIC_LABELS = {'play': '播放量', 'engage': '互动率', 'collect': '收藏率'}
```

在文件末尾追加：

```python
def _bucket_for_days(days: int) -> str:
    """按发布天数返回成熟度桶名。"""
    if days <= 7:
        return '0-7天'
    if days <= 30:
        return '8-30天'
    if days <= 90:
        return '31-90天'
    return '91天以上'


def _publish_days(value: Any, now: datetime) -> Optional[int]:
    """解析发布时间并返回距 now 的天数；无效时间返回 None。"""
    pt = _as_datetime(value)
    if pt is None:
        return None
    return max((now.date() - pt.date()).days, 0)


def _insight_metrics(row: dict) -> dict:
    """返回 play/engage/collect 三项原始指标，无法计算的为 None。"""
    play = int(row.get('play_count') or 0)
    like = int(row.get('like_count') or 0)
    collect = int(row.get('collect_count') or 0)
    engage = None
    collect_metric = None
    if play > 0:
        engage = like / play
        collect_metric = collect / play
    elif like > 0:
        collect_metric = collect / like
    return {'play': play, 'engage': engage, 'collect': collect_metric}


def _percentile(values: list, value: float) -> Optional[float]:
    """计算 value 在 values 中的百分位（0-100，保留 1 位小数）。"""
    if not values:
        return None
    less = sum(1 for x in values if x < value)
    equal = sum(1 for x in values if x == value)
    return round(100 * (less + 0.5 * equal) / len(values), 1)


def _explain(percentiles: dict) -> str:
    """取偏离 50 最大的指标生成中文解释。"""
    best_key = None
    best_distance = -1.0
    best_value = None
    for key, value in percentiles.items():
        if value is None:
            continue
        distance = abs(value - 50)
        if distance > best_distance:
            best_key = key
            best_distance = distance
            best_value = value
    if best_key is None:
        return '数据不足'
    label = INSIGHTS_METRIC_LABELS[best_key]
    if best_value >= 50:
        return f'{label}超过同发布时长视频中 {best_value}%'
    return f'{label}低于同发布时长视频中 {best_value}%'


def analyze_insights(rows: list[dict], now: Optional[datetime] = None, limit: int = 10) -> dict:
    """按成熟度分桶 + 多指标百分位识别潜力爆款与异常偏低视频。"""
    if now is None:
        now = datetime.now()
    limit = max(1, min(int(limit), INSIGHTS_MAX_LIMIT))

    cleaned = []
    for row in rows:
        days = _publish_days(row.get('publish_time'), now)
        if days is None:
            continue
        count_fields = ('play_count', 'like_count', 'collect_count')
        if all(row.get(field) in (None, 0) for field in count_fields):
            continue
        metrics = _insight_metrics(row)
        cleaned.append({
            'video_id': row.get('video_id'),
            'video_title': row.get('video_title'),
            'publish_time': row.get('publish_time'),
            'days_since_publish': days,
            'maturity_bucket': _bucket_for_days(days),
            'play_count': int(row.get('play_count') or 0),
            'engage_rate': round(metrics['engage'], 4) if metrics['engage'] is not None else None,
            'collect_rate': round(metrics['collect'], 4) if metrics['collect'] is not None else None,
            'metrics': metrics,
        })

    if len(cleaned) < INSIGHTS_MIN_SAMPLE_SIZE:
        return {
            'sample_size': len(cleaned),
            'insufficient_sample': True,
            'top': [],
            'bottom': [],
            'generated_at': now.isoformat(timespec='seconds'),
        }

    bucket_items: dict = {}
    for item in cleaned:
        bucket_items.setdefault(item['maturity_bucket'], []).append(item)

    def pool_values(pool: list, key: str) -> list:
        return [item['metrics'][key] for item in pool if item['metrics'][key] is not None]

    scored = []
    for item in cleaned:
        pool = bucket_items[item['maturity_bucket']]
        if len(pool) < INSIGHTS_MIN_BUCKET_SIZE:
            pool = cleaned
        percentiles = {}
        for key in INSIGHTS_WEIGHTS:
            value = item['metrics'][key]
            percentiles[key] = _percentile(pool_values(pool, key), value) if value is not None else None
        available_weights = {key: INSIGHTS_WEIGHTS[key] for key in percentiles if percentiles[key] is not None}
        total_weight = sum(available_weights.values())
        if total_weight == 0:
            continue
        score = sum(INSIGHTS_WEIGHTS[key] * percentiles[key] for key in available_weights) / total_weight
        scored.append({
            'video_id': item['video_id'],
            'video_title': item['video_title'],
            'publish_time': item['publish_time'],
            'days_since_publish': item['days_since_publish'],
            'maturity_bucket': item['maturity_bucket'],
            'play_count': item['play_count'],
            'engage_rate': item['engage_rate'],
            'collect_rate': item['collect_rate'],
            'score': round(score, 1),
            'percentiles': percentiles,
            'explanation': _explain(percentiles),
        })

    top = sorted(scored, key=lambda x: (-x['score'], x['video_id'] or ''))[:limit]
    bottom = sorted(scored, key=lambda x: (x['score'], x['video_id'] or ''))[:limit]
    return {
        'sample_size': len(cleaned),
        'insufficient_sample': False,
        'top': top,
        'bottom': bottom,
        'generated_at': now.isoformat(timespec='seconds'),
    }
```

- [ ] **Step 1.5: 运行测试确认通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: PASS，全部通过。

- [ ] **Step 1.6: 提交（需用户确认）**

```powershell
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py tests/test_analyzer.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: analyzer 新增爆款洞察评分函数"
```

---

### Task 2: api.py 新增 GET /api/analyze/insights

**Files:**
- Modify: api.py
- Test: tests/test_analyze_insights_api.py（新建）

- [ ] **Step 2.1: 写失败测试 tests/test_analyze_insights_api.py**

新建文件，内容：

```python
"""GET /api/analyze/insights 路由逻辑测试。"""
import pytest
from fastapi import HTTPException

import api


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        pass

    def fetchall(self):
        return [{'author_name': '测试作者', 'video_id': '1'}]


class FakeDb:
    def cursor(self):
        return FakeCursor()

    def close(self):
        pass


def test_limit_0_rejected():
    with pytest.raises(HTTPException) as exc:
        api.analyze_insights_endpoint(author_id='A1', limit=0)
    assert exc.value.status_code == 400


def test_limit_51_rejected():
    with pytest.raises(HTTPException) as exc:
        api.analyze_insights_endpoint(author_id='A1', limit=51)
    assert exc.value.status_code == 400


def test_endpoint_merges_analyzer_result(monkeypatch):
    monkeypatch.setattr(api, 'get_db', lambda: FakeDb())
    monkeypatch.setattr(api, 'db_close', lambda db: None)
    monkeypatch.setattr(api, 'apply_publish_filter', lambda start, end: ('', []))
    monkeypatch.setattr(api.extension_receiver, 'build_author_filter', lambda allowed: ('', []))
    monkeypatch.setattr(api.analyzer, 'analyze_insights', lambda rows, limit=10: {
        'sample_size': 1,
        'insufficient_sample': False,
        'top': [],
        'bottom': [],
        'generated_at': '2026-08-16T12:00:00',
    })

    result = api.analyze_insights_endpoint(author_id='A1', start_date='', end_date='', limit=10)
    assert result['author_id'] == 'A1'
    assert result['author_name'] == '测试作者'
    assert result['sample_size'] == 1
    assert result['top'] == []
    assert result['bottom'] == []
```

- [ ] **Step 2.2: 运行测试确认失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyze_insights_api.py -q
```

Expected: FAIL，报 AttributeError: module 'api' has no attribute 'analyze_insights_endpoint'。

- [ ] **Step 2.3: 在 api.py 增加路由**

在 /api/analyze/personal 路由之后、/api/export 之前插入：

```python
@app.get('/api/analyze/insights', dependencies=[Depends(verify_read_guard)])
def analyze_insights_endpoint(
    author_id: str = Query('', description='作者 uid'),
    start_date: str = Query('', description='发布时间起始（YYYY-MM-DD）'),
    end_date: str = Query('', description='发布时间结束（YYYY-MM-DD）'),
    limit: int = Query(10, description='Top/Bottom 各返回条数'),
):
    """按作者识别潜力爆款与异常偏低视频。"""
    author_id = (author_id or '').strip()
    if not author_id:
        raise HTTPException(status_code=400, detail='author_id 不能为空')
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail='limit 必须是 1-50 之间的整数')
    db = get_db()
    try:
        with db.cursor() as cursor:
            publish_clause, publish_params = apply_publish_filter(start_date, end_date)
            author_clause, author_params = extension_receiver.build_author_filter(ALLOWED_AUTHOR_IDS)
            where_sql = 'author_id = %s'
            where_params = [author_id]
            if publish_clause:
                where_sql += ' AND ' + publish_clause
                where_params.extend(publish_params)
            if author_clause:
                where_sql += ' AND ' + author_clause
                where_params.extend(author_params)
            cursor.execute(f'SELECT * FROM video_info WHERE {where_sql}', tuple(where_params))
            rows = cursor.fetchall()
    finally:
        db_close(db)
    author_name = (rows[0].get('author_name') or '') if rows else ''
    insights = analyzer.analyze_insights(rows, limit=limit)
    return {
        'author_id': author_id,
        'author_name': author_name,
        **insights,
    }
```

- [ ] **Step 2.4: 运行测试确认通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyze_insights_api.py -q
```

Expected: PASS。

- [ ] **Step 2.5: 把新路由加入鉴权覆盖测试**

修改 tests/test_api_guard.py 的 READ_GUARDED_PATHS，在 '/api/analyze/personal' 之后增加：

```python
    '/api/analyze/insights',
```

- [ ] **Step 2.6: 运行鉴权测试确认通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_guard.py -q
```

Expected: PASS。

- [ ] **Step 2.7: 提交（需用户确认）**

```powershell
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py tests/test_analyze_insights_api.py tests/test_api_guard.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 新增爆款洞察只读接口"
```

---

### Task 3: 前端 API 类型与请求函数

**Files:**
- Modify: frontend/src/api/index.ts

- [ ] **Step 3.1: 在 frontend/src/api/index.ts 末尾追加类型与函数**

追加内容：

```typescript
export interface InsightItem {
  video_id: string
  video_title?: string | null
  publish_time?: string | null
  days_since_publish: number
  maturity_bucket: string
  play_count: number
  engage_rate: number | null
  collect_rate: number | null
  score: number
  percentiles: { play: number | null; engage: number | null; collect: number | null }
  explanation: string
}

export interface InsightData {
  author_id: string
  author_name: string
  sample_size: number
  insufficient_sample: boolean
  top: InsightItem[]
  bottom: InsightItem[]
  generated_at: string
}

export function getAnalyzeInsights(params: {
  author_id: string
  start_date?: string
  end_date?: string
  limit?: number
}) {
  return api.get<InsightData>('/analyze/insights', { params })
}
```

- [ ] **Step 3.2: 构建前端确认类型通过**

Run:

```powershell
cd frontend
npm run build
```

Expected: 构建成功（允许既有 chunk 大小警告）。

- [ ] **Step 3.3: 提交（需用户确认）**

```powershell
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/api/index.ts
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 前端新增爆款洞察 API 类型"
```

---

### Task 4: PersonalAnalyzer.vue 新增爆款洞察模块

**Files:**
- Modify: frontend/src/pages/PersonalAnalyzer.vue

- [ ] **Step 4.1: 修改 import 与响应式状态**

把原 import 行：

```typescript
import api from '../api'
```

改为：

```typescript
import api, { getAnalyzeInsights, type InsightData } from '../api'
```

在 data 状态声明之后追加：

```typescript
const insights = ref<InsightData | null>(null)
const insightsLoading = ref(false)
const insightsError = ref('')
```

- [ ] **Step 4.2: 增加 loadInsights 与 watch**

在 loadPersonal 函数之后追加：

```typescript
async function loadInsights() {
  if (!authorId.value) return
  insightsLoading.value = true
  insightsError.value = ''
  try {
    const res = await getAnalyzeInsights({
      author_id: authorId.value,
      start_date: dateRange.value ? dateRange.value[0] : undefined,
      end_date: dateRange.value ? dateRange.value[1] : undefined,
    })
    insights.value = res.data
  } catch (e: any) {
    insightsError.value = e?.response?.data?.detail || e?.message || '加载爆款洞察失败'
  } finally {
    insightsLoading.value = false
  }
}
```

在现有 watch 行之后追加：

```typescript
watch([authorId, dateRange], loadInsights)
```

- [ ] **Step 4.3: 在 Top 10 视频卡片之后插入爆款洞察模板**

在 Top 10 视频的 el-card 结束标签之后、外层 template 结束之前插入：

```html
      <el-card v-if="insights || insightsLoading" shadow="never" class="p-card">
        <template #header>
          <div class="top-header">
            <span>爆款洞察</span>
            <span v-if="insights" class="insight-sample">样本 {{ insights.sample_size }} 条</span>
          </div>
        </template>
        <el-alert
          v-if="insightsError"
          type="error"
          :title="insightsError"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-empty
          v-if="!insightsLoading && insights?.insufficient_sample"
          description="样本不足，至少需要 5 条可评分视频"
        />
        <el-row v-if="insights && !insights.insufficient_sample" :gutter="16">
          <el-col :span="12">
            <div class="insight-title">潜力爆款</div>
            <el-table :data="insights.top" size="small" max-height="420">
              <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
              <el-table-column label="发布天数" width="90">
                <template #default="{ row }">{{ row.days_since_publish }}</template>
              </el-table-column>
              <el-table-column label="播放" width="90">
                <template #default="{ row }">{{ fmtNum(row.play_count) }}</template>
              </el-table-column>
              <el-table-column label="互动率" width="90">
                <template #default="{ row }">{{ fmtRate(row.engage_rate) }}</template>
              </el-table-column>
              <el-table-column label="收藏率" width="90">
                <template #default="{ row }">{{ fmtRate(row.collect_rate) }}</template>
              </el-table-column>
              <el-table-column prop="score" label="综合分" width="80" />
              <el-table-column prop="explanation" label="解释" show-overflow-tooltip />
            </el-table>
          </el-col>
          <el-col :span="12">
            <div class="insight-title">异常偏低</div>
            <el-table :data="insights.bottom" size="small" max-height="420">
              <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
              <el-table-column label="发布天数" width="90">
                <template #default="{ row }">{{ row.days_since_publish }}</template>
              </el-table-column>
              <el-table-column label="播放" width="90">
                <template #default="{ row }">{{ fmtNum(row.play_count) }}</template>
              </el-table-column>
              <el-table-column label="互动率" width="90">
                <template #default="{ row }">{{ fmtRate(row.engage_rate) }}</template>
              </el-table-column>
              <el-table-column label="收藏率" width="90">
                <template #default="{ row }">{{ fmtRate(row.collect_rate) }}</template>
              </el-table-column>
              <el-table-column prop="score" label="综合分" width="80" />
              <el-table-column prop="explanation" label="解释" show-overflow-tooltip />
            </el-table>
          </el-col>
        </el-row>
      </el-card>
```

- [ ] **Step 4.4: 补充样式**

在 style 块中 .c-missing 规则之后追加：

```css
.insight-title {
  margin: 4px 0 8px;
  font-weight: 600;
  color: var(--spider-text);
}
.insight-sample {
  color: var(--spider-text-secondary);
  font-size: 12px;
}
```

- [ ] **Step 4.5: 构建前端确认通过**

Run:

```powershell
cd frontend
npm run build
```

Expected: 构建成功。

- [ ] **Step 4.6: 提交（需用户确认）**

```powershell
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/pages/PersonalAnalyzer.vue
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析页新增爆款洞察模块"
```

---

### Task 5: 更新 README 功能列表

**Files:**
- Modify: README.md

- [ ] **Step 5.1: 在个人视频数据分析器小节补充爆款洞察**

在 README 的「个人视频数据分析器（浏览器插件版）」列表末尾、「看板新增「个人分析」页」条目之后追加：

```markdown
    - 「爆款洞察」：按发布天数分桶 + 播放/互动/收藏百分位评分，自动标记潜力爆款与异常偏低视频；
```

- [ ] **Step 5.2: 提交（需用户确认）**

```powershell
git -c safe.directory=D:/DjangoProject/PythonProject11 add README.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: README 补充爆款洞察功能"
```

---

### Task 6: 全量回归与手工验收

**Files:**
- 无新增

- [ ] **Step 6.1: 后端全量测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全部通过（允许既有 pandas/pyarrow 警告）。

- [ ] **Step 6.2: 扩展单测**

Run:

```powershell
cd extension
node --test
```

Expected: 32 passed（或当前基线）。

- [ ] **Step 6.3: 前端构建**

Run:

```powershell
cd frontend
npm run build
```

Expected: 构建成功。

- [ ] **Step 6.4: 手工验收**

打开 http://127.0.0.1:8001/app/ 的个人分析页：

1. 选择样本数 ≥ 5 的作者，确认出现「爆款洞察」模块；
2. 检查 Top/Bottom 各最多 10 条，展示播放量、互动率、收藏率、综合分与解释；
3. 切换作者与日期，确认模块刷新；
4. 选择样本不足作者，确认显示「样本不足」而非报错。
