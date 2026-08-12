# 个人分析功能增强 + 分析页 UI 优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分析页新增互动率、播放量月度趋势、Top 多维排序、数据完整度标注（含非主页来源提示），并做轻量 UI 优化。

**Architecture:** 聚合逻辑放 `analyzer.py` 纯函数（engagement / play_trend / completeness / top_videos sort_by），`api.py` 加 sort_by 参数，`PersonalAnalyzer.vue` 扩展展示。

**Tech Stack:** Python 3 + pytest；Vue3 + Element Plus + ECharts。

**Spec:** `docs/superpowers/specs/2026-08-12-analyzer-enhancement-design.md`

---

### Task 1: analyzer.py 纯函数（TDD）

**Files:**
- Modify: `tests/test_analyzer.py`
- Modify: `analyzer.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyzer.py` 追加：
```python
def test_summarize_engagement_rates():
    rows = [
        make_row(video_id='1', play_count=200, like_count=20, comment_count=4, share_count=2),
        make_row(video_id='2', play_count=0, like_count=10),
    ]
    summary = summarize_rows(rows)
    assert summary['engagement'] == {
        'like_rate': 0.15,     # 30 / 200
        'comment_rate': 0.02,  # 4 / 200
        'share_rate': 0.01,    # 2 / 200
    }


def test_summarize_engagement_none_when_no_play():
    summary = summarize_rows([make_row(video_id='1', play_count=0)])
    assert summary['engagement'] == {
        'like_rate': None,
        'comment_rate': None,
        'share_rate': None,
    }


def test_summarize_completeness_counts_missing():
    rows = [
        make_row(video_id='1', play_count=0, like_count=10, comment_count=None, share_count=0, publish_time=None),
        make_row(video_id='2', play_count=100, like_count=10, comment_count=1, share_count=1, publish_time=None),
    ]
    c = summarize_rows(rows)['completeness']
    assert c['play'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['like'] == {'missing': 0, 'total': 2, 'missing_rate': 0.0}
    assert c['comment'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['share'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['publish_time'] == {'missing': 2, 'total': 2, 'missing_rate': 1.0}


def test_build_play_trend():
    rows = [
        make_row(video_id='1', publish_time=datetime(2026, 5, 1), play_count=100),
        make_row(video_id='2', publish_time=datetime(2026, 5, 20), play_count=50),
        make_row(video_id='3', publish_time=datetime(2026, 3, 15), play_count=200),
        make_row(video_id='4', publish_time=datetime(2026, 3, 16), play_count=0),
        make_row(video_id='5', publish_time=None, play_count=999),
    ]
    assert build_play_trend(rows) == [
        {'month': '2026-03', 'plays': 200},
        {'month': '2026-05', 'plays': 150},
    ]


def test_top_videos_sort_by_plays():
    rows = [make_row(video_id=str(i), play_count=i * 10, like_count=100 - i) for i in range(1, 12)]
    top = top_videos(rows, limit=3, sort_by='plays')
    assert [r['video_id'] for r in top] == ['11', '10', '9']


def test_top_videos_sort_by_engagement_puts_zero_play_last():
    rows = [
        make_row(video_id='a', play_count=100, like_count=50),
        make_row(video_id='b', play_count=0, like_count=999),
        make_row(video_id='c', play_count=200, like_count=50),
    ]
    top = top_videos(rows, limit=3, sort_by='engagement')
    assert [r['video_id'] for r in top] == ['a', 'c', 'b']
```

`tests/test_analyzer.py` 顶部 import 追加 `build_play_trend`。

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q`
Expected: FAIL（新函数缺失 / 断言不匹配）。

- [ ] **Step 3: 实现 analyzer.py**

3.1 追加 `_rate` 辅助与 `build_play_trend`，扩展 `summarize_rows`，扩展 `top_videos`：
```python
def _rate(numerator: int, denominator: int):
    """比率，分母为 0 返回 None。"""
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def summarize_rows(rows: list[dict]) -> dict:
    """按作者过滤后的概览：总数、总和、最近同步、互动率、数据完整度。"""
    def total(field: str) -> int:
        return sum(int(r.get(field) or 0) for r in rows)

    sync_times = [
        _as_datetime(r.get('update_time') or r.get('crawl_time'))
        for r in rows
        if r.get('update_time') or r.get('crawl_time')
    ]

    completeness: dict = {}
    for field in ('play_count', 'like_count', 'comment_count', 'share_count', 'publish_time'):
        if field == 'publish_time':
            missing = sum(1 for r in rows if not r.get(field))
        else:
            missing = sum(1 for r in rows if r.get(field) in (None, 0))
        key = field.replace('_count', '')
        completeness[key] = {
            'missing': missing,
            'total': len(rows),
            'missing_rate': round(missing / len(rows), 4) if rows else 0,
        }

    return {
        'total_videos': len(rows),
        'total_likes': total('like_count'),
        'total_comments': total('comment_count'),
        'total_shares': total('share_count'),
        'total_plays': total('play_count'),
        'latest_sync': max(sync_times) if sync_times else None,
        'engagement': {
            'like_rate': _rate(total('like_count'), total('play_count')),
            'comment_rate': _rate(total('comment_count'), total('play_count')),
            'share_rate': _rate(total('share_count'), total('play_count')),
        },
        'completeness': completeness,
    }


def build_play_trend(rows: list[dict]) -> list[dict]:
    """按 publish_time 的「年-月」汇总播放量，升序；无发布时间或无播放量不计入。"""
    totals: dict[str, int] = {}
    for r in rows:
        pt = _as_datetime(r.get('publish_time'))
        play = r.get('play_count')
        if pt is None or not play:
            continue
        month = f'{pt.year:04d}-{pt.month:02d}'
        totals[month] = totals.get(month, 0) + int(play)
    return [{'month': m, 'plays': totals[m]} for m in sorted(totals)]
```

3.2 `top_videos` 增加 `sort_by`：
```python
SORT_KEYS = {
    'likes': 'like_count',
    'plays': 'play_count',
    'comments': 'comment_count',
    'shares': 'share_count',
}


def _sort_value(r: dict, sort_by: str):
    if sort_by == 'engagement':
        play = int(r.get('play_count') or 0)
        if not play:
            return -1
        return int(r.get('like_count') or 0) / play
    return int(r.get(SORT_KEYS.get(sort_by, 'like_count')) or 0)


def top_videos(rows: list[dict], limit: int = TOP_VIDEOS_LIMIT, sort_by: str = 'likes') -> list[dict]:
    """按指定维度降序取前 limit 条；互动率分母为 0 排后。"""
    ordered = sorted(rows, key=lambda r: _sort_value(r, sort_by), reverse=True)
    return ordered[:limit]
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q`
Expected: 全部 PASS。

---

### Task 2: api.py sort_by 参数

**Files:**
- Modify: `api.py`

- [ ] **Step 1: analyze_personal 扩展**

```python
@app.get('/api/analyze/personal')
def analyze_personal(
    author_id: str = Query(..., description='作者 uid'),
    sort_by: str = Query('likes', description='Top 视频排序维度'),
):
    """按作者聚合个人分析：概览 / 发布趋势 / 播放趋势 / Top 视频。"""
    if sort_by not in ('likes', 'plays', 'comments', 'shares', 'engagement'):
        raise HTTPException(status_code=400, detail='sort_by 必须是 likes/plays/comments/shares/engagement')
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info WHERE author_id = %s', (author_id,))
            rows = cursor.fetchall()
    finally:
        db_close(db)
    author_name = (rows[0].get('author_name') or '') if rows else ''
    return {
        'author_id': author_id,
        'author_name': author_name,
        'summary': analyzer.summarize_rows(rows),
        'trend': analyzer.build_trend(rows),
        'play_trend': analyzer.build_play_trend(rows),
        'top_videos': analyzer.top_videos(rows, sort_by=sort_by),
    }
```

- [ ] **Step 2: 运行回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS。

---

### Task 3: 前端 PersonalAnalyzer.vue

**Files:**
- Modify: `frontend/src/pages/PersonalAnalyzer.vue`

- [ ] **Step 1: script 类型与状态**

`PersonalData` 接口扩展：
```ts
interface PersonalData {
  author_id: string
  author_name: string
  summary: {
    total_videos: number
    total_likes: number
    total_comments: number
    total_shares: number
    total_plays: number
    latest_sync: string | null
    engagement: {
      like_rate: number | null
      comment_rate: number | null
      share_rate: number | null
    }
    completeness: Record<string, { missing: number; total: number; missing_rate: number }>
  }
  trend: { month: string; count: number }[]
  play_trend: { month: string; plays: number }[]
  top_videos: Array<{
    video_id: string
    video_title?: string | null
    like_count?: number
    comment_count?: number
    share_count?: number
    play_count?: number
    publish_time?: string | null
    crawl_time?: string | null
  }>
}
```

`const sortBy = ref('likes')`（在 `data` 定义附近），`watch(authorId, loadPersonal)` 改为：
```ts
const sortBy = ref('likes')
watch([authorId, sortBy], loadPersonal)
```

`loadPersonal` 请求参数改为：
```ts
    const res = await api.get<PersonalData>('/analyze/personal', {
      params: { author_id: authorId.value, sort_by: sortBy.value },
    })
```

新增 computed 与工具函数（`interactionOption` 之后）：
```ts
const playTrendOption = computed(() => ({
  title: {
    text: '每月播放量',
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'axis' },
  grid: { left: 64, right: 16, top: 44, bottom: 28 },
  xAxis: {
    type: 'category',
    data: (data.value?.play_trend ?? []).map((t) => t.month),
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      name: '播放量',
      type: 'bar',
      barMaxWidth: 28,
      itemStyle: { color: '#e6a23c', borderRadius: [4, 4, 0, 0] },
      data: (data.value?.play_trend ?? []).map((t) => t.plays),
    },
  ],
}))

const completenessFields = [
  { key: 'play', label: '播放量' },
  { key: 'like', label: '点赞' },
  { key: 'comment', label: '评论' },
  { key: 'share', label: '分享' },
  { key: 'publish_time', label: '发布时间' },
]

const completenessNotice = computed(() => {
  const play = data.value?.summary?.completeness?.play
  if (!play) return ''
  if (play.missing_rate >= 0.99) {
    return '该作者数据非主页采集来源（详情/爬虫），播放量无值属预期，完整度仅供参考'
  }
  return '播放量缺失表示该视频尚未被主页采集覆盖，可重新采集补齐'
})
```

`fmtNum` 之后新增：
```ts
function fmtRate(v?: number | null) {
  if (v === null || v === undefined) return '--'
  return (v * 100).toFixed(2) + '%'
}
```

- [ ] **Step 2: 模板**

2.1 StatCard 行后追加互动率行：
```html
      <el-row :gutter="16" style="margin-top: 12px">
        <el-col :span="4">
          <StatCard title="点赞率" :value="fmtRate(data.summary.engagement.like_rate)" status="success" />
        </el-col>
        <el-col :span="4">
          <StatCard title="评论率" :value="fmtRate(data.summary.engagement.comment_rate)" status="warning" />
        </el-col>
        <el-col :span="4">
          <StatCard title="分享率" :value="fmtRate(data.summary.engagement.share_rate)" status="info" />
        </el-col>
      </el-row>
```

2.2 图表行改为「发布趋势 + 播放趋势」：
```html
      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="trendOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="playTrendOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="interactionOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <template #header>数据完整度</template>
            <div v-for="f in completenessFields" :key="f.key" class="c-row">
              <span class="c-label">{{ f.label }}</span>
              <el-progress
                :percentage="Math.round((1 - (data.summary.completeness[f.key]?.missing_rate ?? 0)) * 100)"
                :stroke-width="10"
                style="flex: 1"
              />
              <span class="c-missing">{{ data.summary.completeness[f.key]?.missing ?? 0 }} 条缺失</span>
            </div>
            <el-alert
              v-if="completenessNotice"
              type="info"
              :closable="false"
              :title="completenessNotice"
              style="margin-top: 12px"
            />
          </el-card>
        </el-col>
      </el-row>
```

2.3 Top 卡片 header 加排序下拉，表格加播放列：
```html
      <el-card shadow="never" class="p-card">
        <template #header>
          <div class="top-header">
            <span>Top 10 视频</span>
            <el-select v-model="sortBy" size="small" style="width: 140px">
              <el-option label="按点赞" value="likes" />
              <el-option label="按播放" value="plays" />
              <el-option label="按评论" value="comments" />
              <el-option label="按分享" value="shares" />
              <el-option label="按互动率" value="engagement" />
            </el-select>
          </div>
        </template>
        <el-table :data="data.top_videos" size="small" max-height="460">
          <el-table-column prop="video_id" label="视频ID" width="190" />
          <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
          <el-table-column label="播放" width="100">
            <template #default="{ row }">{{ fmtNum(row.play_count) }}</template>
          </el-table-column>
          <el-table-column label="点赞" width="100">
            <template #default="{ row }">{{ fmtNum(row.like_count) }}</template>
          </el-table-column>
```

2.4 style 追加：
```css
.top-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.c-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}
.c-label {
  width: 64px;
  color: var(--spider-text-secondary);
  font-size: 13px;
}
.c-missing {
  width: 76px;
  text-align: right;
  color: var(--spider-text-secondary);
  font-size: 12px;
}
```

- [ ] **Step 3: build 验证**

Run（`frontend/`）: `npm run build`
Expected: 构建成功。

---

### Task 4: 重启后端 + 真库验证 + 全量回归

- [ ] **Step 1: 重启后端**

Run: `.\stop_backend.ps1` 后 `.\run_backend.ps1`。

- [ ] **Step 2: 真库验证**

`GET /api/analyze/personal?author_id=<自己 uid>&sort_by=plays`：确认 `engagement`、`completeness`、`play_trend` 返回且与库一致；`sort_by` 非法值返回 400。

- [ ] **Step 3: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 全部 PASS；
Run（`extension/`）: `node --test` → 全部 PASS；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py api.py frontend/src/pages/PersonalAnalyzer.vue tests/test_analyzer.py docs/superpowers/specs/2026-08-12-analyzer-enhancement-design.md docs/superpowers/plans/2026-08-12-analyzer-enhancement.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析增强——互动率/播放趋势/多维排序/数据完整度标注"
```
