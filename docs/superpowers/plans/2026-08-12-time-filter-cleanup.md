# 时间检索 + 定时清理 + 个人分析标注 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三个接口支持按发布时间自定义范围过滤（三页前端联动）；后端新增每 30 天删除最旧 200 条的定时清理（手动开关、删除前备份）；个人分析新增收藏率与非本人数据标注。

**Architecture:** 时间过滤与清理规则拆成两个纯逻辑模块（`time_filter.py`、`cleanup_service.py`），api.py 做薄层集成（参数解析、端点、后台调度线程）；开关与上次执行时间存 Redis；analyzer 互动率新增 collect_rate；前端四页加日期选择器/开关/标注。

**Tech Stack:** Python 3.13 + FastAPI + pymysql + Redis；Vue3 + Element Plus（el-date-picker / el-switch）。

**前置基线（2026-08-12）**

- pytest 126 passed、`node --test` 32 passed、`npm run build` 成功；
- git 命令一律带 `-c safe.directory=D:/DjangoProject/PythonProject11`；
- 当前分支 `codex/time-filter-cleanup`（spec 已提交 `bbd245c`）；
- 清理规则（已确认）：开关默认关闭；每 30 天一次；`update_time` 升序删最旧 200 条；全库 ≤ 200 条不执行；删除前备份、备份失败不删；参数为后端常量。

---

### Task 1: 时间过滤纯逻辑（time_filter.py，TDD）

**Files:**
- Create: `time_filter.py`
- Test: `tests/test_time_filter.py`

- [ ] **Step 1: 写失败测试（新建 `tests/test_time_filter.py`）**

```python
"""发布时间范围过滤：日期解析与 SQL 条件构建。"""
from datetime import date, datetime

import pytest

from time_filter import build_publish_filter, parse_date_param


def test_parse_date_param_ok():
    assert parse_date_param('2026-08-01') == date(2026, 8, 1)


def test_parse_date_param_empty_returns_none():
    assert parse_date_param('') is None
    assert parse_date_param(None) is None


def test_parse_date_param_invalid_raises():
    with pytest.raises(ValueError):
        parse_date_param('2026-13-01')
    with pytest.raises(ValueError):
        parse_date_param('abc')


def test_build_publish_filter_no_dates():
    clause, params = build_publish_filter(None, None)
    assert clause == ''
    assert params == []


def test_build_publish_filter_start_only():
    clause, params = build_publish_filter('2026-08-01', None)
    assert clause == 'publish_time >= %s'
    assert params == [datetime(2026, 8, 1, 0, 0, 0)]


def test_build_publish_filter_end_only():
    clause, params = build_publish_filter(None, '2026-08-31')
    assert clause == 'publish_time <= %s'
    assert params == [datetime(2026, 8, 31, 23, 59, 59)]


def test_build_publish_filter_both():
    clause, params = build_publish_filter('2026-08-01', '2026-08-31')
    assert 'publish_time >= %s' in clause
    assert 'publish_time <= %s' in clause
    assert params == [datetime(2026, 8, 1, 0, 0, 0), datetime(2026, 8, 31, 23, 59, 59)]


def test_build_publish_filter_inverted_raises():
    with pytest.raises(ValueError):
        build_publish_filter('2026-08-31', '2026-08-01')


def test_build_publish_filter_invalid_raises():
    with pytest.raises(ValueError):
        build_publish_filter('bad', None)
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_time_filter.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'time_filter'`。

- [ ] **Step 3: 实现 `time_filter.py`**

```python
"""发布时间范围过滤：日期参数解析与 SQL 条件构建（纯逻辑）。"""
from datetime import date, datetime
from typing import Optional


def parse_date_param(value: Optional[str]) -> Optional[date]:
    """解析 'YYYY-MM-DD'；None/空串返回 None；格式非法抛 ValueError（中文消息）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f'日期格式无效：{text}（应为 YYYY-MM-DD）') from None


def build_publish_filter(start_date: Optional[str], end_date: Optional[str]) -> tuple[str, list]:
    """构建 publish_time 闭区间过滤条件。

    返回 (clause, params)：无过滤时 clause=''、params=[]；
    非法日期或 start_date > end_date 抛 ValueError（中文消息）。
    """
    s = parse_date_param(start_date) if start_date else None
    e = parse_date_param(end_date) if end_date else None
    if s and e and s > e:
        raise ValueError('start_date 不能晚于 end_date')
    clauses = []
    params = []
    if s:
        clauses.append('publish_time >= %s')
        params.append(datetime.combine(s, datetime.min.time()))
    if e:
        clauses.append('publish_time <= %s')
        params.append(datetime.combine(e, datetime.max.time()))
    return ' AND '.join(clauses), params
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_time_filter.py -q
```

Expected: 9 passed。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add time_filter.py tests/test_time_filter.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 发布时间范围过滤纯逻辑"
```

---

### Task 2: 定时清理纯逻辑（cleanup_service.py，TDD）

**Files:**
- Create: `cleanup_service.py`
- Test: `tests/test_cleanup_service.py`

- [ ] **Step 1: 写失败测试（新建 `tests/test_cleanup_service.py`）**

```python
"""定时清理服务：开关/间隔判断、待删选择、备份生成（纯逻辑）。"""
from datetime import datetime, timedelta

from cleanup_service import (
    CLEANUP_BATCH_SIZE,
    CLEANUP_INTERVAL_DAYS,
    build_backup_csv,
    select_stale_ids,
    should_run_cleanup,
)


def test_constants():
    assert CLEANUP_INTERVAL_DAYS == 30
    assert CLEANUP_BATCH_SIZE == 200


def test_should_run_cleanup_disabled():
    assert should_run_cleanup(False, None, datetime(2026, 8, 12)) is False


def test_should_run_cleanup_first_time_enabled():
    assert should_run_cleanup(True, None, datetime(2026, 8, 12)) is True


def test_should_run_cleanup_not_due():
    now = datetime(2026, 8, 12)
    assert should_run_cleanup(True, now - timedelta(days=29), now) is False


def test_should_run_cleanup_due():
    now = datetime(2026, 8, 12)
    assert should_run_cleanup(True, now - timedelta(days=30), now) is True


def test_select_stale_ids_asc_order():
    rows = [
        {'video_id': 'c', 'update_time': datetime(2026, 8, 12)},
        {'video_id': 'a', 'update_time': datetime(2026, 8, 1)},
        {'video_id': 'b', 'update_time': datetime(2026, 8, 10)},
    ]
    assert select_stale_ids(rows, batch_size=2) == ['a', 'b']


def test_select_stale_ids_less_than_batch():
    rows = [{'video_id': 'x', 'update_time': None}]
    assert select_stale_ids(rows, batch_size=5) == ['x']


def test_select_stale_ids_missing_time_sorted_first():
    rows = [
        {'video_id': 'n', 'update_time': None},
        {'video_id': 'y', 'update_time': datetime(2026, 8, 12)},
    ]
    assert select_stale_ids(rows, batch_size=1) == ['n']


def test_build_backup_csv_header_and_rows():
    rows = [
        {'video_id': '1', 'video_title': '标题', 'like_count': 3, 'collect_count': 5,
         'update_time': datetime(2026, 8, 12)},
    ]
    text = build_backup_csv(rows)
    assert 'video_id' in text
    assert 'collect_count' in text
    assert '1' in text
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'cleanup_service'`。

- [ ] **Step 3: 实现 `cleanup_service.py`**

```python
"""定时清理服务：开关/间隔判断、待删选择、备份 CSV 生成（纯逻辑）。"""
import csv
import io
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

CLEANUP_INTERVAL_DAYS = 30
CLEANUP_BATCH_SIZE = 200
CLEANUP_BACKUP_DIR = os.path.join(tempfile.gettempdir(), 'douyin_cleanup_backup')

BACKUP_FIELDS = (
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'collect_count',
    'play_count', 'video_url', 'cover_url', 'crawl_time', 'update_time',
)


def should_run_cleanup(enabled, last_clean_time: Optional[datetime], now: datetime,
                       interval_days: int = CLEANUP_INTERVAL_DAYS) -> bool:
    """开关开启且距上次执行满 interval_days 才执行；last_clean_time 为 None（首次）时执行。"""
    if not enabled:
        return False
    if last_clean_time is None:
        return True
    return (now - last_clean_time) >= timedelta(days=interval_days)


def select_stale_ids(rows: list[dict], batch_size: int = CLEANUP_BATCH_SIZE) -> list[str]:
    """按 update_time 升序取前 batch_size 个 video_id；update_time 缺失排最前。"""
    ordered = sorted(rows, key=lambda r: r.get('update_time') or datetime.min)
    return [str(r['video_id']) for r in ordered[:batch_size]]


def build_backup_csv(rows: list[dict]) -> str:
    """把待删行转 CSV 文本（含全部业务字段，缺失字段留空）。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=BACKUP_FIELDS, extrasaction='ignore')
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in BACKUP_FIELDS})
    return buf.getvalue()
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: 9 passed。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add cleanup_service.py tests/test_cleanup_service.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 定时清理纯逻辑（间隔判断/待删选择/备份生成）"
```

---

### Task 3: 分析层收藏率（analyzer.py，TDD）

**Files:**
- Modify: `analyzer.py`
- Test: `tests/test_analyzer.py`

- [ ] **Step 1: 更新现有 engagement 断言并新增 collect_rate 测试**

1a. `tests/test_analyzer.py` 的 `test_summarize_engagement_rates` 期望值加 `'collect_rate': 0.05`：

```python
def test_summarize_engagement_rates():
    rows = [
        make_row(video_id='1', play_count=200, like_count=20, comment_count=4, share_count=2, collect_count=10),
        make_row(video_id='2', play_count=0, like_count=10, comment_count=0, share_count=0, collect_count=0),
    ]
    summary = summarize_rows(rows)
    assert summary['engagement'] == {
        'like_rate': 0.15,
        'comment_rate': 0.02,
        'share_rate': 0.01,
        'collect_rate': 0.05,
    }
```

1b. `test_summarize_engagement_none_when_no_play_and_no_like` 期望值加 `'collect_rate': None`：

```python
def test_summarize_engagement_none_when_no_play_and_no_like():
    summary = summarize_rows([make_row(video_id='1', play_count=0, like_count=0, comment_count=0, share_count=0, collect_count=0)])
    assert summary['engagement'] == {
        'like_rate': None,
        'comment_rate': None,
        'share_rate': None,
        'collect_rate': None,
    }
```

1c. `test_summarize_engagement_falls_back_to_like_when_no_play` 期望值加 `'collect_rate': 0.3`：

```python
def test_summarize_engagement_falls_back_to_like_when_no_play():
    rows = [make_row(video_id='1', play_count=0, like_count=10, comment_count=2, share_count=1, collect_count=3)]
    e = summarize_rows(rows)['engagement']
    assert e['like_rate'] is None
    assert e['comment_rate'] == 0.2
    assert e['share_rate'] == 0.1
    assert e['collect_rate'] == 0.3
```

1d. 新增独立用例（追加到文件末尾）：

```python
def test_summarize_collect_rate_uses_play_first():
    rows = [make_row(video_id='1', play_count=200, like_count=20, collect_count=10)]
    e = summarize_rows(rows)['engagement']
    assert e['collect_rate'] == 0.05
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: FAIL（engagement 断言缺 collect_rate）。

- [ ] **Step 3: 实现 `analyzer.py`**

`summarize_rows` 的 engagement dict 在 `'like_rate': _rate(...)` 之后新增：

```python
            'collect_rate': _rate(
                total('collect_count'),
                total('play_count') or total('like_count'),
            ),
```

（放在 share_rate 之后、`},` 之前，与 comment/share 同一退化规则。）

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py tests/test_analyzer.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 互动率新增收藏率（无播放量退化以点赞为分母）"
```

---

### Task 4: API 集成（时间过滤 + 清理端点 + 后台调度）

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 顶部 import 与常量**

`api.py` 现有 import 块（`import json / os / subprocess / pymysql / redis / datetime`）之后新增：

```python
import threading
import time as time_module

import cleanup_service
from time_filter import build_publish_filter
```

- [ ] **Step 2: 新增日期参数解析 helper**

在 `get_db()` 之后新增：

```python
def apply_publish_filter(start_date: str, end_date: str):
    """把 start_date/end_date 转成 SQL 过滤条件；非法参数抛 400。"""
    try:
        return build_publish_filter(start_date or None, end_date or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 3: `/api/videos` 支持时间过滤**

`list_videos` 签名加参数：

```python
    start_date: str = Query('', description='发布时间起始（YYYY-MM-DD）'),
    end_date: str = Query('', description='发布时间结束（YYYY-MM-DD）'),
```

函数体内 `offset = ...` 之后新增：

```python
    publish_clause, publish_params = apply_publish_filter(start_date, end_date)
```

把 `count_sql` / `data_sql` 的构造替换为（search 分支）：

```python
            if search:
                search_param = f'%{search}%'
                where_parts = ['(video_id LIKE %s OR video_title LIKE %s OR author_name LIKE %s)']
                count_params = [search_param, search_param, search_param]
                if publish_clause:
                    where_parts.append(publish_clause)
                    count_params.extend(publish_params)
                where_sql = ' AND '.join(where_parts)
                count_sql = f'SELECT COUNT(*) AS total FROM video_info WHERE {where_sql}'
                cursor.execute(count_sql, tuple(count_params))
                total = cursor.fetchone()['total']

                data_sql = f"""
                    SELECT * FROM video_info
                    WHERE {where_sql}
                    ORDER BY {sort_by} {order_clause}
                    LIMIT %s OFFSET %s
                """
                cursor.execute(data_sql, tuple(count_params + [page_size, offset]))
            else:
                where_parts = []
                count_params = []
                if publish_clause:
                    where_parts.append(publish_clause)
                    count_params.extend(publish_params)
                where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''
                cursor.execute(f'SELECT COUNT(*) AS total FROM video_info {where_sql}', tuple(count_params))
                total = cursor.fetchone()['total']

                data_sql = f"""
                    SELECT * FROM video_info
                    {where_sql}
                    ORDER BY {sort_by} {order_clause}
                    LIMIT %s OFFSET %s
                """
                cursor.execute(data_sql, tuple(count_params + [page_size, offset]))
```

- [ ] **Step 4: `/api/stats` 支持时间过滤**

`get_stats` 签名加参数（与 Step 3 相同两行），函数体内执行统计前新增：

```python
    publish_clause, publish_params = apply_publish_filter(start_date, end_date)
```

SQL 改为：

```python
            where_sql = ('WHERE ' + publish_clause) if publish_clause else ''
            cursor.execute(f"""
                SELECT
                    COUNT(*) AS total_videos,
                    COUNT(DISTINCT author_id) AS total_authors,
                    COALESCE(SUM(like_count), 0) AS total_likes,
                    COALESCE(SUM(comment_count), 0) AS total_comments,
                    COALESCE(SUM(share_count), 0) AS total_shares,
                    COALESCE(SUM(play_count), 0) AS total_plays,
                    MAX(crawl_time) AS latest_crawl
                FROM video_info
                {where_sql}
            """, tuple(publish_params))
```

- [ ] **Step 5: `/api/analyze/personal` 支持时间过滤**

签名加参数，并替换查询：

```python
    publish_clause, publish_params = apply_publish_filter(start_date, end_date)
    where_sql = 'author_id = %s'
    where_params = [author_id]
    if publish_clause:
        where_sql += ' AND ' + publish_clause
        where_params.extend(publish_params)
    ...
            cursor.execute(f'SELECT * FROM video_info WHERE {where_sql}', tuple(where_params))
```

- [ ] **Step 6: 清理端点与后台调度**

在 `analyze_personal` 之后新增：

```python
class CleanupToggleRequest(BaseModel):
    enabled: bool


@app.get('/api/cleanup/status')
def cleanup_status():
    """返回定时清理开关状态与上次执行时间。"""
    try:
        r = get_redis()
        enabled = int(r.get('douyin:cleanup_enabled') or 0) == 1
        last_clean_time = r.get('douyin:cleanup_last_time')
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {'enabled': enabled, 'last_clean_time': last_clean_time}


@app.post('/api/cleanup/toggle', dependencies=[Depends(verify_write_guard)])
def cleanup_toggle(req: CleanupToggleRequest):
    """切换定时清理开关（写接口，走令牌守卫）。"""
    try:
        r = get_redis()
        r.set('douyin:cleanup_enabled', '1' if req.enabled else '0')
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {'enabled': req.enabled}


def _cleanup_once() -> None:
    """执行一次清理检查：满足条件则备份并删除最旧 200 条。"""
    r = get_redis()
    enabled = int(r.get('douyin:cleanup_enabled') or 0) == 1
    last_raw = r.get('douyin:cleanup_last_time')
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
        except ValueError:
            last = None
    if not cleanup_service.should_run_cleanup(enabled, last, datetime.now()):
        return

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM video_info')
            total = cursor.fetchone()['n']
            if total <= cleanup_service.CLEANUP_BATCH_SIZE:
                print(f'定时清理跳过：全库行数 {total} <= {cleanup_service.CLEANUP_BATCH_SIZE}')
                return
            cursor.execute(
                'SELECT * FROM video_info ORDER BY update_time ASC LIMIT %s',
                (cleanup_service.CLEANUP_BATCH_SIZE,),
            )
            rows = cursor.fetchall()
    finally:
        db_close(db)
    if not rows:
        return

    backup_dir = cleanup_service.CLEANUP_BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir,
        'cleanup_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv',
    )
    with open(backup_path, 'w', encoding='utf-8', newline='') as f:
        f.write(cleanup_service.build_backup_csv(rows))

    ids = [str(r['video_id']) for r in rows]
    db = get_db()
    try:
        with db.cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(ids))
            cursor.execute(
                f'DELETE FROM video_info WHERE video_id IN ({placeholders})',
                tuple(ids),
            )
            db.commit()
    finally:
        db_close(db)

    r.set('douyin:cleanup_last_time', datetime.now().isoformat(timespec='seconds'))
    print(f'定时清理完成：删除 {len(ids)} 条，备份 {backup_path}')


def _cleanup_loop() -> None:
    """后台循环：每 24 小时检查一次清理条件。"""
    while True:
        try:
            _cleanup_once()
        except Exception as e:  # noqa: BLE001 - 后台线程兜底，避免循环退出
            print(f'定时清理异常：{e}')
        time_module.sleep(24 * 3600)


@app.on_event('startup')
def start_cleanup_loop() -> None:
    threading.Thread(target=_cleanup_loop, daemon=True).start()
```

- [ ] **Step 7: 回归验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 126 + 本计划新增用例全部通过。

- [ ] **Step 8: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 三接口发布时间过滤 + 定时清理端点与后台调度"
```

---

### Task 5: 前端四页（日期选择器 / 收藏率 / 标注 / 清理开关）

**Files:**
- Modify: `frontend/src/pages/Videos.vue`
- Modify: `frontend/src/pages/Dashboard.vue`
- Modify: `frontend/src/pages/PersonalAnalyzer.vue`
- Modify: `frontend/src/pages/Quality.vue`

- [ ] **Step 1: `Videos.vue` 加日期范围选择器**

script 中 `const order = ref('desc')` 后新增：

```ts
const dateRange = ref<[string, string] | null>(null)

const dateShortcuts = [
  {
    text: '本月',
    value: () => {
      const now = new Date()
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [start, now]
    },
  },
]
```

`load()` 的 params 增加：

```ts
        start_date: dateRange.value ? dateRange.value[0] : undefined,
        end_date: dateRange.value ? dateRange.value[1] : undefined,
```

模板工具栏（搜索框之前）新增：

```html
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        :shortcuts="dateShortcuts"
        style="max-width: 300px"
        clearable
        @change="doSearch"
      />
```

- [ ] **Step 2: `Videos.vue` 加清理开关**

script 新增状态与函数（`onMounted` 改为同时加载开关）：

```ts
const cleanupEnabled = ref(false)
const cleanupLoading = ref(false)

async function loadCleanupStatus() {
  try {
    const res = await api.get<{ enabled: boolean }>('/cleanup/status')
    cleanupEnabled.value = res.data.enabled
  } catch { /* 开关状态加载失败不阻塞页面 */ }
}

async function toggleCleanup(val: boolean) {
  cleanupLoading.value = true
  try {
    await api.post('/cleanup/toggle', { enabled: val })
    ElMessage.success(val ? '定时清理已开启' : '定时清理已关闭')
  } catch (e: any) {
    cleanupEnabled.value = !val
    ElMessage.error(e?.response?.data?.detail || e?.message || '切换失败')
  } finally {
    cleanupLoading.value = false
  }
}
```

`onMounted(load)` 改为：

```ts
onMounted(() => {
  load()
  loadCleanupStatus()
})
```

模板工具栏末尾（刷新按钮之后）新增：

```html
      <span class="cleanup-label">定时清理</span>
      <el-switch
        v-model="cleanupEnabled"
        :loading="cleanupLoading"
        @change="toggleCleanup"
      />
```

style 增加：

```css
.cleanup-label {
  color: var(--spider-text-secondary);
  font-size: 13px;
}
```

- [ ] **Step 3: `Dashboard.vue` 加日期范围选择器**

script 新增：

```ts
const dateRange = ref<[string, string] | null>(null)

const dateShortcuts = [
  {
    text: '本月',
    value: () => {
      const now = new Date()
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [start, now]
    },
  },
]
```

`useApi` 的请求参数改为带日期：

```ts
const { data, loading, error, run } = useApi<Stats>(() =>
  api.get('/stats', {
    params: {
      start_date: dateRange.value ? dateRange.value[0] : undefined,
      end_date: dateRange.value ? dateRange.value[1] : undefined,
    },
  }).then((r) => r.data),
)
```

`dateRange` 变化时刷新（script 末尾新增）：

```ts
watch(dateRange, () => run())
```

`import { computed } from 'vue'` 改为 `import { computed, ref, watch } from 'vue'`。

模板「刷新」按钮旁新增：

```html
    <el-date-picker
      v-model="dateRange"
      type="daterange"
      value-format="YYYY-MM-DD"
      range-separator="至"
      start-placeholder="开始日期"
      end-placeholder="结束日期"
      :shortcuts="dateShortcuts"
      style="max-width: 300px"
      clearable
    />
```

- [ ] **Step 4: `PersonalAnalyzer.vue` 加日期范围、收藏率卡与标注**

4a. script 类型扩展：`engagement` 加 `collect_rate: number | null`；新增：

```ts
const dateRange = ref<[string, string] | null>(null)

const dateShortcuts = [
  {
    text: '本月',
    value: () => {
      const now = new Date()
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [start, now]
    },
  },
]
```

4b. `loadPersonal` 的 params 增加：

```ts
      start_date: dateRange.value ? dateRange.value[0] : undefined,
      end_date: dateRange.value ? dateRange.value[1] : undefined,
```

`watch([authorId, sortBy], loadPersonal)` 改为 `watch([authorId, sortBy, dateRange], loadPersonal)`。

4c. 互动率卡片区：原 3 卡（点赞率/评论率/分享率，各 `span=4`）改为 4 卡（各 `span=6`），新增收藏率卡：

```html
        <el-col :span="6">
          <StatCard title="收藏率" :value="fmtRate(data.summary.engagement.collect_rate)" status="info" />
        </el-col>
```

4d. 互动率区下方新增非本人标注（`completenessNotice` 之后追加 computed）：

```ts
const rateNotice = computed(() => {
  const play = data.value?.summary?.completeness?.play
  if (!play || play.missing_rate < 0.99) return ''
  return '该作者数据非主页采集来源，播放量缺失；分享率、收藏率以点赞数为分母计算'
})
```

模板互动率 el-row 之后新增：

```html
      <el-alert
        v-if="rateNotice"
        type="info"
        :closable="false"
        :title="rateNotice"
        style="margin-top: 12px"
      />
```

4e. 工具栏（作者选择旁）新增日期选择器：

```html
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        :shortcuts="dateShortcuts"
        style="max-width: 300px"
        clearable
      />
```

- [ ] **Step 5: `Quality.vue` 加清理开关**

script 新增：

```ts
const cleanupEnabled = ref(false)
const cleanupLoading = ref(false)

async function loadCleanupStatus() {
  try {
    const res = await api.get<{ enabled: boolean }>('/cleanup/status')
    cleanupEnabled.value = res.data.enabled
  } catch { /* 忽略 */ }
}

async function toggleCleanup(val: boolean) {
  cleanupLoading.value = true
  try {
    await api.post('/cleanup/toggle', { enabled: val })
    ElMessage.success(val ? '定时清理已开启' : '定时清理已关闭')
  } catch (e: any) {
    cleanupEnabled.value = !val
    ElMessage.error(e?.response?.data?.detail || e?.message || '切换失败')
  } finally {
    cleanupLoading.value = false
  }
}
```

`onMounted(load)` 改为：

```ts
onMounted(() => {
  load()
  loadCleanupStatus()
})
```

模板顶部 alert 之后新增卡片：

```html
    <el-card shadow="never" class="q-card">
      <template #header>
        <span>定时清理</span>
      </template>
      <div class="q-cleanup">
        <span>每 30 天按更新时间删除最旧 200 条数据（删除前自动备份，行数不足 200 时不执行）。</span>
        <el-switch
          v-model="cleanupEnabled"
          :loading="cleanupLoading"
          @change="toggleCleanup"
        />
      </div>
    </el-card>
```

style 增加：

```css
.q-cleanup {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--spider-text-secondary);
  font-size: 13px;
}
```

- [ ] **Step 6: 构建验证**

```powershell
cd frontend; npm run build
```

Expected: 构建成功（chunk 大小警告为既有提示）。

- [ ] **Step 7: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/pages/Videos.vue frontend/src/pages/Dashboard.vue frontend/src/pages/PersonalAnalyzer.vue frontend/src/pages/Quality.vue
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 前端日期范围筛选/收藏率标注/清理开关"
```

---

### Task 6: 全量回归

**Files:** 无（验证任务）

- [ ] **Step 1: 后端全量测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 126 + 本计划新增（约 18）全部通过。

- [ ] **Step 2: 插件全量测试**

```powershell
cd extension; node --test
```

Expected: 32 passed（本计划未改插件，保持全绿）。

- [ ] **Step 3: 前端构建**

```powershell
cd frontend; npm run build
```

Expected: 构建成功。

- [ ] **Step 4: 工作树状态**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 status --short
```

Expected: 干净。

---

### Task 7: 真机验收与交接文档

**Files:**
- Modify: `docs/superpowers/handoff/2026-08-12-new-window-handoff.md`

- [ ] **Step 1: 重启后端验证接口**

经用户确认后 `.\stop_backend.ps1` + `.\run_backend.ps1`；验证：

```text
GET  /api/videos?start_date=2026-08-01&end_date=2026-08-31        → 只含本月发布
GET  /api/stats?start_date=2026-08-01&end_date=2026-08-31         → 统计为过滤后
GET  /api/analyze/personal?author_id=xxx&start_date=...            → 过滤后聚合
GET  /api/cleanup/status                                           → {enabled: false, last_clean_time: null}
POST /api/cleanup/toggle {"enabled": true}                         → 开；再次 status 确认 true
```

- [ ] **Step 2: 前端人工验证**

用户浏览器确认：三页日期选择器与「本月」快捷、收藏率卡、非本人标注、两处清理开关状态同步。

- [ ] **Step 3: 更新交接文档**

「本窗口完成」追加时间检索/定时清理/收藏率标注条目；「验证证据」更新 pytest 数量；「下一步」移除已完成项；新增漂移警告（清理开关默认关闭、备份目录、行数 ≤ 200 不执行）。

- [ ] **Step 4: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add docs/superpowers/handoff/2026-08-12-new-window-handoff.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 时间检索与定时清理完成收尾"
```

---

### Task 8: 定时清理升级（按作者多选 + 自定义条数，TDD）

> 说明：Task 1-7 已完成并提交（时间检索 + 全库清理 + 前端）。本任务把清理逻辑从「全库删最旧 200 条」升级为「按作者维度精准清理」：作者多选（空=全部）+ 自定义条数（默认 200，存 Redis）。

**Files:**
- Modify: `cleanup_service.py`
- Modify: `api.py`
- Modify: `frontend/src/pages/Videos.vue`
- Modify: `frontend/src/pages/Quality.vue`
- Test: `tests/test_cleanup_service.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_cleanup_service.py` 末尾）**

```python
def test_select_stale_ids_per_author_all_authors():
    rows = [
        {'video_id': 'a1', 'author_id': 'A', 'update_time': datetime(2026, 1, 1)},
        {'video_id': 'a2', 'author_id': 'A', 'update_time': datetime(2026, 2, 1)},
        {'video_id': 'a3', 'author_id': 'A', 'update_time': datetime(2026, 3, 1)},
        {'video_id': 'b1', 'author_id': 'B', 'update_time': datetime(2026, 1, 1)},
    ]
    assert select_stale_ids_per_author(rows, batch_size=2) == ['a1', 'a2']


def test_select_stale_ids_per_author_filtered():
    rows = [
        {'video_id': 'a1', 'author_id': 'A', 'update_time': datetime(2026, 1, 1)},
        {'video_id': 'a2', 'author_id': 'A', 'update_time': datetime(2026, 2, 1)},
        {'video_id': 'a3', 'author_id': 'A', 'update_time': datetime(2026, 3, 1)},
        {'video_id': 'b1', 'author_id': 'B', 'update_time': datetime(2026, 1, 1)},
        {'video_id': 'b2', 'author_id': 'B', 'update_time': datetime(2026, 2, 1)},
        {'video_id': 'b3', 'author_id': 'B', 'update_time': datetime(2026, 3, 1)},
    ]
    assert select_stale_ids_per_author(rows, batch_size=2, author_ids=['B']) == ['b1', 'b2']


def test_select_stale_ids_per_author_under_limit_skipped():
    rows = [
        {'video_id': 'a1', 'author_id': 'A', 'update_time': datetime(2026, 1, 1)},
        {'video_id': 'a2', 'author_id': 'A', 'update_time': datetime(2026, 2, 1)},
    ]
    assert select_stale_ids_per_author(rows, batch_size=2) == []


def test_select_stale_ids_per_author_empty_rows():
    assert select_stale_ids_per_author([]) == []


def test_select_stale_ids_per_author_empty_author_group():
    rows = [
        {'video_id': 'x1', 'author_id': '', 'update_time': datetime(2026, 1, 1)},
        {'video_id': 'x2', 'author_id': '', 'update_time': datetime(2026, 2, 1)},
        {'video_id': 'x3', 'author_id': '', 'update_time': datetime(2026, 3, 1)},
    ]
    assert select_stale_ids_per_author(rows, batch_size=2) == ['x1', 'x2']
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: FAIL，`ImportError: cannot import name 'select_stale_ids_per_author'`。

- [ ] **Step 3: 实现 `cleanup_service.py`**

导入区 `from cleanup_service import ...` 无关；在 `select_stale_ids` 之后新增：

```python
def select_stale_ids_per_author(rows: list[dict], batch_size: int = CLEANUP_BATCH_SIZE,
                                author_ids: Optional[list] = None) -> list[str]:
    """按作者分组选择待删 video_id。

    只处理 author_ids 中的作者（None/空列表 = 全部作者）；
    每组行数 > batch_size 时按 update_time 升序取最旧 batch_size 条，其余组跳过。
    """
    if not rows:
        return []
    allowed = None
    if author_ids is not None and len(author_ids) > 0:
        allowed = {str(a) for a in author_ids}
    groups = {}
    order = []
    for r in rows:
        aid = str(r.get('author_id') or '')
        if allowed is not None and aid not in allowed:
            continue
        if aid not in groups:
            groups[aid] = []
            order.append(aid)
        groups[aid].append(r)
    stale = []
    for aid in order:
        group = groups[aid]
        if len(group) <= batch_size:
            continue
        ordered = sorted(group, key=lambda r: r.get('update_time') or datetime.min)
        stale.extend(str(r['video_id']) for r in ordered[:batch_size])
    return stale
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: 原 9 个 + 新增 5 个全部通过。

- [ ] **Step 5: 更新 `api.py` 的 status/settings 端点与执行逻辑**

5a. `cleanup_status` 返回扩展为条数+作者：

```python
@app.get('/api/cleanup/status')
def cleanup_status():
    """返回定时清理开关、上次执行时间、条数与指定作者。"""
    try:
        r = get_redis()
        enabled = int(r.get('douyin:cleanup_enabled') or 0) == 1
        last_clean_time = r.get('douyin:cleanup_last_time')
        batch_size = int(r.get('douyin:cleanup_batch_size') or cleanup_service.CLEANUP_BATCH_SIZE)
        authors_raw = r.get('douyin:cleanup_authors')
        authors = json.loads(authors_raw) if authors_raw else []
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {
        'enabled': enabled,
        'last_clean_time': last_clean_time,
        'batch_size': batch_size,
        'authors': authors,
    }
```

5b. 新增 settings 端点（放在 `cleanup_toggle` 之后）：

```python
class CleanupSettingsRequest(BaseModel):
    batch_size: int = 200
    authors: list[str] = []


@app.post('/api/cleanup/settings', dependencies=[Depends(verify_write_guard)])
def cleanup_settings(req: CleanupSettingsRequest):
    """保存清理条数与指定作者（空 authors = 全部作者）。"""
    if not (1 <= req.batch_size <= 1000):
        raise HTTPException(status_code=400, detail='batch_size 必须在 1-1000 之间')
    try:
        r = get_redis()
        r.set('douyin:cleanup_batch_size', str(req.batch_size))
        r.set('douyin:cleanup_authors', json.dumps(req.authors))
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {'batch_size': req.batch_size, 'authors': req.authors}
```

5c. `_cleanup_once` 改为按作者执行（替换「全库行数判断 + ORDER BY LIMIT」段）：

```python
def _cleanup_once() -> None:
    """执行一次清理检查：满足条件则按作者规则备份并删除。"""
    r = get_redis()
    enabled = int(r.get('douyin:cleanup_enabled') or 0) == 1
    last_raw = r.get('douyin:cleanup_last_time')
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
        except ValueError:
            last = None
    if not cleanup_service.should_run_cleanup(enabled, last, datetime.now()):
        return
    batch_size = int(r.get('douyin:cleanup_batch_size') or cleanup_service.CLEANUP_BATCH_SIZE)
    authors_raw = r.get('douyin:cleanup_authors')
    authors = json.loads(authors_raw) if authors_raw else []

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info')
            rows = cursor.fetchall()
    finally:
        db_close(db)
    if not rows:
        return

    ids = cleanup_service.select_stale_ids_per_author(
        rows, batch_size=batch_size, author_ids=authors or None,
    )
    if not ids:
        print('定时清理跳过：没有满足条件的待删数据')
        return

    by_id = {str(r['video_id']): r for r in rows}
    delete_rows = [by_id[i] for i in ids if i in by_id]
    backup_dir = cleanup_service.CLEANUP_BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir,
        'cleanup_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv',
    )
    with open(backup_path, 'w', encoding='utf-8', newline='') as f:
        f.write(cleanup_service.build_backup_csv(delete_rows))

    db = get_db()
    try:
        with db.cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(ids))
            cursor.execute(
                f'DELETE FROM video_info WHERE video_id IN ({placeholders})',
                tuple(ids),
            )
            db.commit()
    finally:
        db_close(db)

    r.set('douyin:cleanup_last_time', datetime.now().isoformat(timespec='seconds'))
    print(f'定时清理完成：删除 {len(ids)} 条，备份 {backup_path}')
```

- [ ] **Step 6: 更新前端 `Videos.vue` 与 `Quality.vue` 清理控件**

6a. 两个页面 script 统一新增（作者列表 + 设置保存）：

```ts
const cleanupAuthors = ref<string[]>([])
const cleanupBatchSize = ref(200)
const authorOptions = ref<Array<{ author_id: string; author_name: string }>>([])

async function loadCleanupStatus() {
  try {
    const res = await api.get<{ enabled: boolean; batch_size: number; authors: string[] }>('/cleanup/status')
    cleanupEnabled.value = res.data.enabled
    cleanupBatchSize.value = res.data.batch_size
    cleanupAuthors.value = res.data.authors
  } catch { /* 忽略 */ }
  try {
    const authorsRes = await api.get<{ authors: Array<{ author_id: string; author_name: string }> }>('/analyze/authors')
    authorOptions.value = authorsRes.data.authors ?? []
  } catch { /* 忽略 */ }
}

async function saveCleanupSettings() {
  try {
    await api.post('/cleanup/settings', {
      batch_size: cleanupBatchSize.value,
      authors: cleanupAuthors.value,
    })
    ElMessage.success('清理设置已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存设置失败')
  }
}
```

6b. 两个页面模板清理区替换为完整控件（开关 + 条数 + 作者多选）：

```html
      <div class="cleanup-panel">
        <div class="cleanup-row">
          <span>定时清理</span>
          <el-switch v-model="cleanupEnabled" :loading="cleanupLoading" @change="toggleCleanup" />
        </div>
        <div class="cleanup-row">
          <span>每次删除条数</span>
          <el-input-number v-model="cleanupBatchSize" :min="1" :max="1000" :step="50" @change="saveCleanupSettings" />
        </div>
        <div class="cleanup-row">
          <span>作者范围（不选=全部作者）</span>
          <el-select
            v-model="cleanupAuthors"
            multiple
            filterable
            clearable
            collapse-tags
            placeholder="全部作者"
            style="width: 320px"
            @change="saveCleanupSettings"
          >
            <el-option
              v-for="a in authorOptions"
              :key="a.author_id"
              :label="`${a.author_name || a.author_id}`"
              :value="a.author_id"
            />
          </el-select>
        </div>
      </div>
```

6c. 两个页面 style 增加：

```css
.cleanup-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cleanup-row {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--spider-text-secondary);
  font-size: 13px;
}
```

（Videos.vue 中该面板放工具栏下方；Quality.vue 中替换原「定时清理」卡片内容。）

- [ ] **Step 7: 回归验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend; npm run build
```

Expected: pytest 全部通过（150 个左右）、构建成功。

- [ ] **Step 8: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add cleanup_service.py tests/test_cleanup_service.py api.py frontend/src/pages/Videos.vue frontend/src/pages/Quality.vue docs/superpowers/specs/2026-08-12-time-filter-cleanup-design.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 定时清理按作者多选+自定义条数"
```
