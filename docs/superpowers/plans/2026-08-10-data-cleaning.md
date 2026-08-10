# 数据清洗功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让抖音爬虫管理系统的数据质量可见、可清理、可导出，并在入库时自动过滤垃圾。

**Architecture:** 纯逻辑集中在新的 `quality.py` 模块（扫描分类、修正、删除校验、CSV 生成），FastAPI 的 `api.py` 只做薄接口层；入库过滤规则放进 `douyin_spider/pipelines.py` 的纯函数中；前端新增独立 `quality.html`/`quality.js` 页面，复用现有暗色样式。所有判定规则都有单元测试，删除类操作按「当前库内最新数据」二次校验。

**Tech Stack:** Python 3.13 / Scrapy / FastAPI / MySQL（pymysql）/ 标准库 csv / 原生 HTML+JS（无构建）。

**前置约定（本仓库环境）：**
- 测试命令一律用：`.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
- git 命令在本环境需加 `-c safe.directory=D:/DjangoProject/PythonProject11`，且写操作需在提权 shell 中执行。

---

## 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `douyin_spider/pipelines.py` | 入库过滤规则：标题规范化、空记录/占位页判断 | 修改 |
| `tests/test_pipelines.py` | 管道规则单元测试 | 修改 |
| `quality.py`（项目根） | 数据质量纯逻辑：分类、统计、修正、删除判定、CSV | 新建 |
| `tests/test_quality.py` | quality.py 单元测试 | 新建 |
| `api.py` | 新增 4 个质量接口（薄层） | 修改 |
| `frontend/quality.html` | 数据质量页面 | 新建 |
| `frontend/quality.js` | 页面逻辑（报告渲染、勾选、操作） | 新建 |
| `frontend/index.html` | 增加「数据质量」导航入口 | 修改 |

---

## 阶段 1：入库自动过滤

### Task 1: 标题规范化与跳过判定规则

**Files:**
- Test: `tests/test_pipelines.py`
- Modify: `douyin_spider/pipelines.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_pipelines.py` 顶部导入追加：

```python
from douyin_spider.pipelines import (
    build_insert_params,
    is_placeholder_title,
    normalize_title,
    should_insert_ignore,
    should_skip_item,
)
```

在文件末尾追加：

```python
def test_normalize_title_strips_whitespace_and_newlines():
    assert normalize_title('  标题  \n 第二行  ') == '标题 第二行'
    assert normalize_title(None) == ''


def test_is_placeholder_title_detects_placeholder_marker():
    assert is_placeholder_title('在抖音记录美好生活20260810 - 抖音') is True
    assert is_placeholder_title('正常视频标题') is False


def test_should_skip_empty_record():
    item = DouyinVideoItem(video_id='x', video_title='', video_desc='')
    assert should_skip_item(item) is True


def test_should_skip_placeholder_title():
    item = DouyinVideoItem(video_id='x', video_title='在抖音记录美好生活 - 抖音', author_name='作者')
    assert should_skip_item(item) is True


def test_should_not_skip_normal_record():
    item = DouyinVideoItem(video_id='x', video_title='标题', author_name='作者')
    assert should_skip_item(item) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipelines.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'normalize_title' ...`）

- [ ] **Step 3: 最小实现**

在 `douyin_spider/pipelines.py` 的 `should_insert_ignore` 之前加入：

```python
PLACEHOLDER_MARKERS = ('在抖音记录美好生活',)


def normalize_title(title):
    """标题规范化：去首尾空白、合并连续空白/换行。"""
    if title is None:
        return ''
    return ' '.join(str(title).split())


def is_placeholder_title(title):
    """占位页标题（无效视频页特征）判断。"""
    if not title:
        return False
    return any(marker in title for marker in PLACEHOLDER_MARKERS)


def should_skip_item(item):
    """标题与作者均为空，或标题为占位页 → 跳过不建行。"""
    title = (item.get('video_title') or '').strip()
    author = (item.get('author_name') or '').strip()
    return (not title and not author) or is_placeholder_title(item.get('video_title'))
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipelines.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add tests/test_pipelines.py douyin_spider/pipelines.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 入库过滤规则（标题规范化/空记录/占位页判断）"
```

### Task 2: 管道接入过滤与标题规范化

**Files:**
- Test: `tests/test_pipelines.py`
- Modify: `douyin_spider/pipelines.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_pipelines.py` 追加：

```python
def test_build_insert_params_normalizes_title():
    item = DouyinVideoItem(video_id='1', video_title='  标题 \n第二行 ', video_desc='描述')
    params = build_insert_params(item)
    assert params['video_title'] == '标题 第二行'
    assert params['video_desc'] == '描述'
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipelines.py::test_build_insert_params_normalizes_title -q -p no:cacheprovider`
Expected: FAIL（`'  标题 \n第二行 ' != '标题 第二行'`）

- [ ] **Step 3: 最小实现**

修改 `douyin_spider/pipelines.py`：

1. `build_insert_params` 中 `video_title` 与 `video_desc` 改为经过 `normalize_title`：

```python
        'video_title': normalize_title(item.get('video_title')),
        'video_desc': normalize_title(item.get('video_desc')),
```

2. `process_item` 最顶部（`if not self.connection` 之前）加入跳过逻辑：

```python
    def process_item(self, item, spider):
        if should_skip_item(item):
            raise DropItem(f"跳过无效记录（空记录或占位页）: {item.get('video_id', '')}")
        if not self.connection:
            raise DropItem("数据库连接不可用，丢弃 Item")
```

- [ ] **Step 4: 全量测试通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 20 passed

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add tests/test_pipelines.py douyin_spider/pipelines.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 入库前规范化标题并跳过无效记录"
```

---

## 阶段 2：后端质量接口 + 导出

### Task 3: 行分类与概览统计

**Files:**
- Create: `tests/test_quality.py`
- Create: `quality.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_quality.py`：

```python
"""数据质量模块单元测试。"""
from datetime import datetime, timedelta

from quality import (
    STALE_DAYS,
    classify_row,
    summarize,
)


def make_row(**over):
    row = {
        'video_id': '1',
        'video_title': '标题',
        'video_desc': '描述',
        'author_name': '作者',
        'author_id': 'A1',
        'publish_time': datetime(2026, 1, 1),
        'like_count': 1,
        'comment_count': 1,
        'share_count': 1,
        'play_count': 0,
        'video_url': 'u',
        'cover_url': 'c',
        'crawl_time': datetime(2026, 5, 20),
        'update_time': datetime(2026, 8, 10),
    }
    row.update(over)
    return row


def test_classify_empty_record():
    row = make_row(video_title='', author_name='')
    assert 'empty' in classify_row(row)


def test_classify_placeholder():
    row = make_row(video_title='在抖音记录美好生活 - 抖音')
    assert 'placeholder' in classify_row(row)


def test_classify_stale():
    row = make_row(update_time=datetime.now() - timedelta(days=STALE_DAYS + 1))
    assert 'stale' in classify_row(row)


def test_classify_missing_author_only():
    row = make_row(author_name='')
    issues = classify_row(row)
    assert 'missing_author' in issues
    assert 'empty' not in issues


def test_classify_clean_row_has_no_issues():
    assert classify_row(make_row()) == []


def test_summarize_counts():
    rows = [
        make_row(video_id='1'),
        make_row(video_id='2', video_title='', author_name=''),
    ]
    summary = summarize(rows)
    assert summary['total'] == 2
    assert summary['distinct_video_ids'] == 2
    assert summary['authors'] == 1
    assert summary['issue_counts']['empty'] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -p no:cacheprovider`
Expected: FAIL（`ModuleNotFoundError: No module named 'quality'`）

- [ ] **Step 3: 最小实现**

新建 `quality.py`（第一阶段内容）：

```python
"""数据质量：扫描分类、概览统计、修正、删除校验与 CSV 导出。"""
import csv
import io
from datetime import datetime, timedelta

STALE_DAYS = 90
MAX_DELETE_IDS = 200
PLACEHOLDER_MARKERS = ('在抖音记录美好生活',)
DELETABLE_ISSUES = ('empty', 'placeholder', 'stale')

ISSUE_LABELS = {
    'empty': '疑似无效（标题与作者均为空）',
    'placeholder': '占位页标题',
    'stale': '陈旧未更新',
    'missing_author': '作者缺失（保留）',
}

EXPORT_COLUMNS = [
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'play_count',
    'video_url', 'cover_url', 'crawl_time', 'update_time',
]

ISSUE_FIELDS = [
    'video_id', 'video_title', 'author_name', 'author_id',
    'like_count', 'comment_count', 'share_count', 'play_count',
    'publish_time', 'crawl_time', 'update_time',
]


def normalize_title(title):
    if title is None:
        return ''
    return ' '.join(str(title).split())


def is_placeholder_title(title):
    if not title:
        return False
    return any(marker in title for marker in PLACEHOLDER_MARKERS)


def is_empty_record(row):
    title = (row.get('video_title') or '').strip()
    author = (row.get('author_name') or '').strip()
    return not title and not author


def is_stale(row, now=None):
    now = now or datetime.now()
    update_time = row.get('update_time')
    if not update_time:
        return False
    if isinstance(update_time, str):
        try:
            update_time = datetime.fromisoformat(update_time)
        except ValueError:
            return False
    return (now - update_time) > timedelta(days=STALE_DAYS)


def classify_row(row):
    issues = []
    if is_empty_record(row):
        issues.append('empty')
    if is_placeholder_title(row.get('video_title')):
        issues.append('placeholder')
    if is_stale(row):
        issues.append('stale')
    title_ok = (row.get('video_title') or '').strip()
    author_missing = not (row.get('author_name') or '').strip()
    if title_ok and author_missing:
        issues.append('missing_author')
    return issues


def summarize(rows):
    return {
        'total': len(rows),
        'distinct_video_ids': len({r.get('video_id') for r in rows}),
        'authors': len({r.get('author_id') for r in rows if r.get('author_id')}),
        'latest_update': max((r.get('update_time') for r in rows), default=None),
        'issue_counts': {
            label: sum(1 for r in rows if label in classify_row(r))
            for label in ISSUE_LABELS
        },
    }


def issue_view(row):
    view = {f: row.get(f) for f in ISSUE_FIELDS}
    view['issue_types'] = classify_row(row)
    return view
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add quality.py tests/test_quality.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 数据质量行分类与概览统计"
```

### Task 4: 修正与删除校验（含时间窗口场景）

**Files:**
- Test: `tests/test_quality.py`
- Modify: `quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_quality.py` 顶部导入追加：

```python
from quality import (
    STALE_DAYS,
    classify_row,
    collect_title_fixes,
    is_deletable,
    summarize,
)
```

文件末尾追加：

```python
def test_collect_title_fixes_only_whitespace_changes():
    rows = [
        make_row(video_id='1', video_title='  标题 \n第二行 '),
        make_row(video_id='2'),
    ]
    fixes = collect_title_fixes(rows)
    assert fixes == [('1', '标题 第二行')]


def test_is_deletable_uses_current_row_not_report_snapshot():
    row_empty = make_row(video_title='', author_name='')
    assert is_deletable(row_empty) is True
    # 报告生成后该行被补全，删除时应拒绝
    row_fixed = make_row(video_title='已补全', author_name='作者', like_count=5)
    assert is_deletable(row_fixed) is False


def test_is_deletable_true_for_stale_row():
    row = make_row(update_time=datetime.now() - timedelta(days=STALE_DAYS + 1))
    assert is_deletable(row) is True
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'collect_title_fixes' ...`）

- [ ] **Step 3: 最小实现**

在 `quality.py` 末尾追加：

```python
def collect_title_fixes(rows):
    """返回需要修正标题的行：[(video_id, 规范化后标题)]。"""
    fixes = []
    for row in rows:
        raw = row.get('video_title') or ''
        cleaned = normalize_title(raw)
        if cleaned != raw:
            fixes.append((row['video_id'], cleaned))
    return fixes


def is_deletable(row):
    """删除前按当前库内最新数据重新判定（不依赖报告快照）。"""
    return any(issue in DELETABLE_ISSUES for issue in classify_row(row))
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add quality.py tests/test_quality.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 标题修正收集与删除二次校验"
```

### Task 5: CSV 导出（标准转义 + UTF-8 BOM）

**Files:**
- Test: `tests/test_quality.py`
- Modify: `quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_quality.py` 顶部导入追加：

```python
from quality import build_csv
```

文件末尾追加：

```python
def test_build_csv_escapes_special_characters_and_adds_bom():
    row = make_row(video_title='标题,带逗号\n换行"引号"')
    text = build_csv([row])
    assert text.startswith('\ufeff')
    assert '"标题,带逗号\n换行""引号"""' in text


def test_build_csv_includes_header():
    text = build_csv([make_row()])
    header = text.splitlines()[0]
    assert 'video_id' in header
    assert 'video_title' in header
    assert 'update_time' in header
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'build_csv' ...`）

- [ ] **Step 3: 最小实现**

在 `quality.py` 末尾追加：

```python
def build_csv(rows):
    """生成带 UTF-8 BOM 的 CSV（标准转义，Excel 直接打开）。"""
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({c: ('' if row.get(c) is None else row.get(c)) for c in EXPORT_COLUMNS})
    return output.getvalue()
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全部通过（阶段 1 的 20 个 + 本阶段新增全部 PASS）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add quality.py tests/test_quality.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 数据质量 CSV 导出（标准转义 + BOM）"
```

### Task 6: FastAPI 质量接口

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 在 `api.py` 顶部加导入**

```python
from fastapi.responses import Response
import quality as quality_service
```

- [ ] **Step 2: 追加 4 个接口（放在 `app.mount('/', StaticFiles...)` 之前）**

```python
class QualityDeleteRequest(BaseModel):
    video_ids: list[str]


@app.get('/api/quality/report')
def quality_report():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info')
            rows = cursor.fetchall()
    finally:
        db_close(db)
    issues = [quality_service.issue_view(r) for r in rows if quality_service.classify_row(r)]
    return {'summary': quality_service.summarize(rows), 'issues': issues}


@app.post('/api/quality/fix')
def quality_fix():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT video_id, video_title FROM video_info')
            rows = cursor.fetchall()
            fixes = quality_service.collect_title_fixes(rows)
            for video_id, title in fixes:
                cursor.execute('UPDATE video_info SET video_title = %s WHERE video_id = %s', (title, video_id))
            db.commit()
    finally:
        db_close(db)
    return {
        'fixed': len(fixes),
        'details': [{'video_id': v, 'video_title': t} for v, t in fixes[:20]],
    }


@app.post('/api/quality/delete')
def quality_delete(req: QualityDeleteRequest):
    if len(req.video_ids) > quality_service.MAX_DELETE_IDS:
        raise HTTPException(status_code=400, detail=f'单次最多删除 {quality_service.MAX_DELETE_IDS} 条，请分批操作')
    db = get_db()
    try:
        deleted = 0
        rejected = []
        with db.cursor() as cursor:
            for video_id in req.video_ids:
                cursor.execute('SELECT * FROM video_info WHERE video_id = %s', (video_id,))
                row = cursor.fetchone()
                if not row:
                    rejected.append({'video_id': video_id, 'reason': '不存在'})
                    continue
                if not quality_service.is_deletable(row):
                    rejected.append({'video_id': video_id, 'reason': '当前数据已不再满足可删规则'})
                    continue
                cursor.execute('DELETE FROM video_info WHERE video_id = %s', (video_id,))
                deleted += 1
            db.commit()
    finally:
        db_close(db)
    return {'deleted': deleted, 'rejected': rejected}


@app.get('/api/quality/export')
def quality_export(scope: str = Query('all', pattern='^(all|issues)$')):
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info')
            rows = cursor.fetchall()
    finally:
        db_close(db)
    if scope == 'issues':
        rows = [r for r in rows if quality_service.classify_row(r)]
    return Response(
        content=quality_service.build_csv(rows).encode('utf-8'),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="douyin_data.csv"'},
    )
```

- [ ] **Step 3: 验证接口**

先确认后端进程为修复后的版本（如未运行，用 `run_backend.ps1` 启动；如已在运行且代码有更新，需重启）。随后在提权 shell 执行：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/quality/report' -TimeoutSec 10 | ConvertTo-Json -Depth 5
```

Expected: 返回 `summary`（total=182、distinct_video_ids=182）和 `issues` 数组。

再插入一条测试行验证删除校验（完成后删除测试行）：

```powershell
mysql -h 127.0.0.1 -P 3307 -u root -p20061006 douyin_spider -e "INSERT INTO video_info (video_id, video_title, video_desc, author_name, author_id, like_count, comment_count, share_count, play_count, video_url, cover_url, crawl_time, update_time) VALUES ('quality_test_1','','','','',0,0,0,0,'','',NOW(),NOW());"
```

调用删除接口删除 `quality_test_1`（应成功，deleted=1），再调用一次（应 rejected=1、reason=不存在），确认无残留：

```powershell
$b = @{ video_ids = @('quality_test_1') } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/quality/delete' -Method Post -ContentType 'application/json' -Body $b
mysql -h 127.0.0.1 -P 3307 -u root -p20061006 douyin_spider -e "SELECT COUNT(*) FROM video_info WHERE video_id='quality_test_1';"
```

Expected: 第一次 `deleted=1`，第二次 `deleted=0` 且 rejected 含「不存在」，最后查询为 0。

验证导出：

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/quality/export?scope=all' -OutFile "$env:TEMP\quality_export.csv"
Get-Content "$env:TEMP\quality_export.csv" -TotalCount 3 -Encoding UTF8
```

Expected: 首行是表头，第二行起为数据，无乱码。

- [ ] **Step 4: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 数据质量接口（报告/修正/删除/导出）"
```

---

## 阶段 3：前端数据质量页

### Task 7: quality.html + quality.js + 导航入口

**Files:**
- Create: `frontend/quality.html`
- Create: `frontend/quality.js`
- Modify: `frontend/index.html`

- [ ] **Step 1: 新建 `frontend/quality.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据质量 - 抖音爬虫管理面板</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="header">
  <div class="header-left">
    <h1>数据质量</h1>
    <a class="btn btn-outline" href="/">返回面板</a>
  </div>
  <div class="header-right">
    <button class="btn btn-outline" id="btn-refresh">刷新</button>
    <button class="btn btn-primary" id="btn-fix">一键修正</button>
    <button class="btn btn-danger" id="btn-delete">删除选中</button>
    <button class="btn btn-outline" id="btn-export">导出 CSV</button>
  </div>
</header>

<section class="stats-grid" id="stats-grid">
  <div class="stat-card"><div class="stat-info"><div class="stat-value" id="stat-total">--</div><div class="stat-label">视频总数</div></div></div>
  <div class="stat-card"><div class="stat-info"><div class="stat-value" id="stat-authors">--</div><div class="stat-label">作者数</div></div></div>
  <div class="stat-card"><div class="stat-info"><div class="stat-value" id="stat-issues">--</div><div class="stat-label">问题总数</div></div></div>
  <div class="stat-card"><div class="stat-info"><div class="stat-value" id="stat-latest">--</div><div class="stat-label">最近更新</div></div></div>
</section>

<section class="table-container">
  <table class="data-table" id="issue-table">
    <thead>
      <tr>
        <th><input type="checkbox" id="check-all"></th>
        <th>视频ID</th>
        <th>标题</th>
        <th>作者</th>
        <th>问题类型</th>
        <th>更新时间</th>
      </tr>
    </thead>
    <tbody id="table-body"><tr class="empty-row"><td colspan="6">加载中...</td></tr></tbody>
  </table>
</section>

<div class="modal-overlay" id="modal-overlay" style="display:none;">
  <div class="modal" id="confirm-modal">
    <div class="modal-header"><h2 id="modal-title">确认删除</h2><button class="modal-close" id="modal-close">&times;</button></div>
    <div class="modal-body" id="modal-body"></div>
    <div class="modal-footer" style="padding:12px;text-align:right;">
      <button class="btn btn-outline" id="btn-cancel">取消</button>
      <button class="btn btn-danger" id="btn-confirm-delete">确认删除</button>
    </div>
  </div>
</div>

<script src="/quality.js"></script>
</body>
</html>
```

- [ ] **Step 2: 新建 `frontend/quality.js`**

```javascript
// 数据质量页面逻辑
const MAX_SELECT = 200;
let currentIssues = [];

function fmtTime(t) {
  if (!t) return '--';
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

async function api(path, opts) {
  opts = opts || {};
  const headers = { 'Content-Type': 'application/json' };
  if (opts.body) opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

const LABELS = {
  empty: '疑似无效',
  placeholder: '占位页标题',
  stale: '陈旧未更新',
  missing_author: '作者缺失',
};

async function loadReport() {
  document.getElementById('table-body').innerHTML = '<tr class="empty-row"><td colspan="6">加载中...</td></tr>';
  try {
    const data = await api('/api/quality/report');
    currentIssues = data.issues;
    document.getElementById('stat-total').textContent = data.summary.total;
    document.getElementById('stat-authors').textContent = data.summary.authors;
    document.getElementById('stat-issues').textContent = data.issues.length;
    document.getElementById('stat-latest').textContent = fmtTime(data.summary.latest_update);
    renderTable(data.issues);
  } catch (e) {
    document.getElementById('table-body').innerHTML = '<tr class="empty-row"><td colspan="6">加载失败: ' + e.message + '</td></tr>';
  }
}

function renderTable(issues) {
  const tbody = document.getElementById('table-body');
  if (!issues || issues.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">暂无问题数据</td></tr>';
    return;
  }
  tbody.innerHTML = issues.map(function (r) {
    const tags = r.issue_types.map(function (t) { return LABELS[t] || t; }).join('、');
    return '<tr>' +
      '<td><input type="checkbox" class="row-check" value="' + r.video_id + '"></td>' +
      '<td>' + r.video_id + '</td>' +
      '<td>' + escHtml(r.video_title || '--') + '</td>' +
      '<td>' + escHtml(r.author_name || '--') + '</td>' +
      '<td>' + escHtml(tags) + '</td>' +
      '<td>' + fmtTime(r.update_time) + '</td>' +
    '</tr>';
  }).join('');
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function selectedIds() {
  return Array.prototype.map.call(document.querySelectorAll('.row-check:checked'), function (c) { return c.value; });
}

document.getElementById('btn-refresh').addEventListener('click', loadReport);

document.getElementById('check-all').addEventListener('change', function () {
  const checked = this.checked;
  document.querySelectorAll('.row-check').forEach(function (c) { c.checked = checked; });
});

document.getElementById('btn-fix').addEventListener('click', async function () {
  if (!confirm('确认执行安全修正（标题去空白/换行）？')) return;
  try {
    const res = await api('/api/quality/fix', { method: 'POST', body: {} });
    alert('已修正 ' + res.fixed + ' 条');
    loadReport();
  } catch (e) {
    alert('修正失败: ' + e.message);
  }
});

document.getElementById('btn-delete').addEventListener('click', function () {
  const ids = selectedIds();
  if (ids.length === 0) {
    alert('请先勾选要删除的问题数据');
    return;
  }
  if (ids.length > MAX_SELECT) {
    alert('单次最多勾选 ' + MAX_SELECT + ' 条，请分批操作');
    return;
  }
  document.getElementById('modal-body').textContent = '确认删除 ' + ids.length + ' 条问题数据？此操作不可恢复。';
  document.getElementById('modal-overlay').style.display = 'flex';
  document.getElementById('btn-confirm-delete').onclick = async function () {
    try {
      const res = await api('/api/quality/delete', { method: 'POST', body: { video_ids: ids } });
      alert('已删除 ' + res.deleted + ' 条' + (res.rejected.length ? '，拒绝 ' + res.rejected.length + ' 条' : ''));
      document.getElementById('modal-overlay').style.display = 'none';
      loadReport();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  };
});

document.getElementById('btn-export').addEventListener('click', function () {
  window.location.href = '/api/quality/export?scope=all';
});

document.getElementById('modal-close').addEventListener('click', function () {
  document.getElementById('modal-overlay').style.display = 'none';
});
document.getElementById('btn-cancel').addEventListener('click', function () {
  document.getElementById('modal-overlay').style.display = 'none';
});
document.getElementById('modal-overlay').addEventListener('click', function (e) {
  if (e.target === this) document.getElementById('modal-overlay').style.display = 'none';
});

document.addEventListener('DOMContentLoaded', loadReport);
```

- [ ] **Step 3: 在 `frontend/index.html` 的 `.header-right` 中加导航入口**

```html
    <a class="btn btn-outline" href="/quality.html">数据质量</a>
```

- [ ] **Step 4: HTTP 验证页面与接口**

在提权 shell 执行：

```powershell
$p = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/quality.html' -UseBasicParsing -TimeoutSec 10
Write-Output ("quality.html status=" + $p.StatusCode)
$j = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/quality.js' -UseBasicParsing -TimeoutSec 10
Write-Output ("quality.js status=" + $j.StatusCode)
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/quality/report' -TimeoutSec 10 | Out-Null
Write-Output 'report ok'
```

Expected: 两个页面 status=200，report 无异常。最后请用户在浏览器打开 `http://localhost:8001/quality.html` 做一次视觉与操作验收（刷新报告、勾选、修正、删除确认弹窗、导出下载）。

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/quality.html frontend/quality.js frontend/index.html
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 数据质量页面（报告/修正/删除/导出）"
```

### Task 8: 全量回归与收尾

**Files:** 无新增

- [ ] **Step 1: 全量测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全部通过（阶段 1 的 20 个 + 阶段 2 新增全部 PASS）

- [ ] **Step 2: 真实数据验收（只读 + 非破坏）**

在提权 shell 执行：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/quality/report' -TimeoutSec 10 | ConvertTo-Json -Depth 5
```

Expected: summary.total 与数据库总数一致；issues 列表符合清洗规则（空记录/占位页/陈旧/作者缺失）。

- [ ] **Step 3: 汇总提交（如 Task 6/7 已提交则跳过）并告知用户推送**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 log --oneline -6
```

向用户汇报：实现内容、测试与真实验证结果、剩余可调项（90 天阈值、xlsx 导出），并询问是否推送远程。
