# 开源版发布准备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在主仓库补齐服务端作者白名单、导出能力、清理配置 JSON 化，并提供发布脚本生成合规开源包（默认仅自己、去爬虫/Redis、含构建产物与新手引导）。

**Architecture:** 主仓库保持完整本地版；开源包由发布脚本白名单复制 + 裁剪 + 替换默认模式生成。导出/清理 JSON/作者白名单同时服务本地版与开源版；开源包特有裁剪由脚本完成。

**Tech Stack:** Python 3.13 + FastAPI + pymysql + pandas/openpyxl + Vue3。

**前置（2026-08-13）:** pytest 148 passed、`node --test` 32 passed、`npm run build` 成功；git 命令带 `-c safe.directory=D:/DjangoProject/PythonProject11`；当前分支 `codex/open-source-release`（spec 已提交 `9b553da`）。

---

### Task 1: 导出服务（export_service.py，TDD）

**Files:**
- Create: `export_service.py`
- Test: `tests/test_export_service.py`

- [ ] **Step 1: 写失败测试（新建 `tests/test_export_service.py`）**

```python
"""导出服务：列定义、CSV、xlsx 生成。"""
from datetime import datetime

from export_service import EXPORT_COLUMNS, EXPORT_MAX_ROWS, build_csv, build_xlsx


def make_row(**over):
    row = {
        'video_id': '1', 'video_title': '标题', 'video_desc': '描述',
        'author_name': '作者', 'author_id': 'A1',
        'publish_time': datetime(2026, 1, 1),
        'like_count': 1, 'comment_count': 1, 'share_count': 1,
        'collect_count': 66, 'play_count': 0,
        'video_url': 'u', 'cover_url': 'c',
        'crawl_time': datetime(2026, 5, 20), 'update_time': datetime(2026, 8, 10),
    }
    row.update(over)
    return row


def test_export_columns_include_collect_count():
    assert 'collect_count' in EXPORT_COLUMNS


def test_export_max_rows_constant():
    assert EXPORT_MAX_ROWS == 10000


def test_build_csv_bom_header_and_row():
    text = build_csv([make_row(video_title='标题,带逗号\n换行')])
    assert text.startswith('\ufeff')
    assert 'collect_count' in text.splitlines()[0]
    assert '"标题,带逗号\n换行"' in text


def test_build_xlsx_valid_workbook():
    import io
    import openpyxl
    content = build_xlsx([make_row()])
    assert content[:2] == b'PK'
    wb = openpyxl.load_workbook(io.BytesIO(content))
    assert wb.active.cell(1, 1).value == 'video_id'
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_export_service.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'export_service'`。

- [ ] **Step 3: 实现 `export_service.py`**

```python
"""数据导出：列定义、CSV 与 xlsx 生成。"""
import csv
import io

import pandas as pd

EXPORT_MAX_ROWS = 10000

EXPORT_COLUMNS = [
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'collect_count',
    'play_count', 'video_url', 'cover_url', 'crawl_time', 'update_time',
]


def _plain(value):
    return '' if value is None else value


def build_csv(rows):
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({c: _plain(row.get(c)) for c in EXPORT_COLUMNS})
    return output.getvalue()


def build_xlsx(rows):
    data = [{c: _plain(row.get(c)) for c in EXPORT_COLUMNS} for row in rows]
    df = pd.DataFrame(data, columns=EXPORT_COLUMNS)
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    return output.getvalue()
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_export_service.py -q
```

Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add export_service.py tests/test_export_service.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 导出服务（列定义/CSV/xlsx）"
```

---

### Task 2: 清理配置 JSON 读写（cleanup_service.py，TDD）

**Files:**
- Modify: `cleanup_service.py`
- Test: `tests/test_cleanup_service.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_cleanup_service.py`）**

```python
from cleanup_service import read_cleanup_config, write_cleanup_config


def test_cleanup_config_read_missing_returns_default(tmp_path):
    cfg = read_cleanup_config(str(tmp_path / 'missing.json'))
    assert cfg['enabled'] is False
    assert cfg['batch_size'] == 200
    assert cfg['authors'] == []


def test_cleanup_config_write_and_read_roundtrip(tmp_path):
    path = str(tmp_path / 'cleanup_config.json')
    write_cleanup_config(path, {'enabled': True, 'last_clean_time': '2026-08-13', 'batch_size': 300, 'authors': ['A']})
    cfg = read_cleanup_config(path)
    assert cfg == {'enabled': True, 'last_clean_time': '2026-08-13', 'batch_size': 300, 'authors': ['A']}


def test_cleanup_config_atomic_write_no_tmp_leftover(tmp_path):
    path = str(tmp_path / 'cleanup_config.json')
    write_cleanup_config(path, {'enabled': True})
    assert [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')] == []
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: FAIL（read/write_cleanup_config 不存在）。

- [ ] **Step 3: 实现 `cleanup_service.py`**

import 区加 `import json`，模块末尾加：

```python
DEFAULT_CLEANUP_CONFIG = {
    'enabled': False,
    'last_clean_time': None,
    'batch_size': CLEANUP_BATCH_SIZE,
    'authors': [],
}


def read_cleanup_config(path: str) -> dict:
    if not os.path.exists(path):
        return dict(DEFAULT_CLEANUP_CONFIG)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return dict(DEFAULT_CLEANUP_CONFIG)
    cfg = dict(DEFAULT_CLEANUP_CONFIG)
    cfg.update({k: data[k] for k in cfg if k in data})
    return cfg


def write_cleanup_config(path: str, config: dict) -> None:
    directory = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.cleanup_config.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_service.py -q
```

Expected: 原测试 + 新增 3 个全部通过。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add cleanup_service.py tests/test_cleanup_service.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 清理配置 JSON 读写（原子写）"
```

---

### Task 3: 清理配置 JSON 化到 api.py（回归验证）

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 常量**

顶部加：

```python
CLEANUP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cleanup_config.json')
```

- [ ] **Step 2: `cleanup_status` 改用 JSON**

```python
@app.get('/api/cleanup/status')
def cleanup_status():
    cfg = cleanup_service.read_cleanup_config(CLEANUP_CONFIG_PATH)
    return {
        'enabled': bool(cfg['enabled']),
        'last_clean_time': cfg['last_clean_time'],
        'batch_size': int(cfg['batch_size']),
        'authors': list(cfg['authors']),
    }
```

- [ ] **Step 3: `cleanup_toggle` / `cleanup_settings` 改用 JSON**

```python
@app.post('/api/cleanup/toggle', dependencies=[Depends(verify_write_guard)])
def cleanup_toggle(req: CleanupToggleRequest):
    cfg = cleanup_service.read_cleanup_config(CLEANUP_CONFIG_PATH)
    cfg['enabled'] = req.enabled
    cleanup_service.write_cleanup_config(CLEANUP_CONFIG_PATH, cfg)
    return {'enabled': req.enabled}


@app.post('/api/cleanup/settings', dependencies=[Depends(verify_write_guard)])
def cleanup_settings(req: CleanupSettingsRequest):
    if not (1 <= req.batch_size <= 1000):
        raise HTTPException(status_code=400, detail='batch_size 必须在 1-1000 之间')
    cfg = cleanup_service.read_cleanup_config(CLEANUP_CONFIG_PATH)
    cfg['batch_size'] = req.batch_size
    cfg['authors'] = list(req.authors)
    cleanup_service.write_cleanup_config(CLEANUP_CONFIG_PATH, cfg)
    return {'batch_size': req.batch_size, 'authors': req.authors}
```

- [ ] **Step 4: `_cleanup_once` 改用 JSON**

把 Redis 配置读取改为：

```python
    cfg = cleanup_service.read_cleanup_config(CLEANUP_CONFIG_PATH)
    enabled = bool(cfg['enabled'])
    last_raw = cfg['last_clean_time']
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
        except ValueError:
            last = None
    if not cleanup_service.should_run_cleanup(enabled, last, datetime.now()):
        return
    batch_size = int(cfg['batch_size'])
    authors = list(cfg['authors'])
```

末尾替换为：

```python
    cfg['last_clean_time'] = datetime.now().isoformat(timespec='seconds')
    cleanup_service.write_cleanup_config(CLEANUP_CONFIG_PATH, cfg)
    print(f'定时清理完成：删除 {len(ids)} 条，备份 {backup_path}')
```

- [ ] **Step 5: 回归验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 清理配置改存本地 JSON，去掉 Redis 依赖"
```

---

### Task 4: 服务端作者白名单（extension_receiver.py + api.py，TDD）

**Files:**
- Modify: `extension_receiver.py`
- Modify: `api.py`
- Test: `tests/test_extension_receiver.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_extension_receiver.py`）**

```python
from extension_receiver import filter_by_author_whitelist


def test_filter_by_author_whitelist_empty_returns_all():
    records = [{'video_id': '1', 'author_id': 'A'}]
    kept, rejected = filter_by_author_whitelist(records, [])
    assert kept == records and rejected == []


def test_filter_by_author_whitelist_rejects_other_and_empty():
    records = [
        {'video_id': '1', 'author_id': 'A'},
        {'video_id': '2', 'author_id': 'B'},
        {'video_id': '3', 'author_id': ''},
    ]
    kept, rejected = filter_by_author_whitelist(records, ['A'])
    assert [r['video_id'] for r in kept] == ['1']
    assert {r['video_id'] for r in rejected} == {'2', '3'}
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q
```

Expected: FAIL（filter_by_author_whitelist 不存在）。

- [ ] **Step 3: 实现 `extension_receiver.py`**

```python
def filter_by_author_whitelist(records: list[dict], allowed_author_ids: list) -> tuple[list[dict], list[dict]]:
    if not allowed_author_ids:
        return records, []
    allowed = {str(a) for a in allowed_author_ids}
    kept = []
    rejected = []
    for r in records:
        aid = str(r.get('author_id') or '')
        if aid in allowed:
            kept.append(r)
        else:
            rejected.append({'video_id': r.get('video_id', ''), 'reason': '作者不在允许列表内'})
    return kept, rejected
```

- [ ] **Step 4: api.py 接入**

顶部加：

```python
try:
    from local_config import ALLOWED_AUTHOR_IDS
except Exception:
    ALLOWED_AUTHOR_IDS = []
```

`extension_receive` 里 `records = extension_receiver.dedupe_records(valid)` 之后加：

```python
    records, author_rejected = extension_receiver.filter_by_author_whitelist(records, ALLOWED_AUTHOR_IDS)
    rejected.extend(author_rejected)
```

- [ ] **Step 5: 跑测试确认通过 + 回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 扩展接收服务端作者白名单校验（ALLOWED_AUTHOR_IDS）"
```

---

### Task 5: `/api/export` 接口（上限 + 流式 CSV + xlsx 临时文件）

**Files:**
- Modify: `api.py`

- [ ] **Step 1: import 与常量**

顶部加：

```python
import csv
import io
import tempfile
from fastapi.responses import StreamingResponse, FileResponse
import export_service
```

新增：

```python
def _check_export_total(total: int) -> None:
    if total > export_service.EXPORT_MAX_ROWS:
        raise HTTPException(status_code=400, detail=f'数据量过大（{total} 条），请缩小筛选范围后导出')
```

- [ ] **Step 2: `/api/export` 端点**

在 `/api/analyze/personal` 之后新增（完整代码见设计稿 4.2，此处按 plan 逐段实现）：

```python
@app.get('/api/export')
def export_data(
    search: str = Query('', description='搜索视频标题/作者/ID'),
    sort_by: str = Query('crawl_time', description='排序字段'),
    order: str = Query('desc', pattern='^(asc|desc)$'),
    start_date: str = Query('', description='发布时间起始（YYYY-MM-DD）'),
    end_date: str = Query('', description='发布时间结束（YYYY-MM-DD）'),
    format: str = Query('csv', pattern='^(csv|xlsx)$'),
):
    allowed_sort = {
        'video_id', 'video_title', 'author_name', 'publish_time',
        'like_count', 'comment_count', 'share_count', 'play_count', 'collect_count',
        'crawl_time', 'update_time',
    }
    if sort_by not in allowed_sort:
        sort_by = 'crawl_time'
    order_clause = 'DESC' if order == 'desc' else 'ASC'
    publish_clause, publish_params = apply_publish_filter(start_date, end_date)
    where_parts = []
    params = []
    if search:
        where_parts.append('(video_id LIKE %s OR video_title LIKE %s OR author_name LIKE %s)')
        params.extend([f'%{search}%'] * 3)
    if publish_clause:
        where_parts.append(publish_clause)
        params.extend(publish_params)
    where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) AS n FROM video_info {where_sql}', tuple(params))
            total = cursor.fetchone()['n']
        _check_export_total(total)
        if format == 'csv':
            def gen():
                conn = get_db()
                try:
                    with conn.cursor(pymysql.cursors.SSCursor) as cursor:
                        cursor.execute(
                            f'SELECT * FROM video_info {where_sql} ORDER BY {sort_by} {order_clause}',
                            tuple(params),
                        )
                        buf = io.StringIO()
                        buf.write('\ufeff')
                        writer = csv.DictWriter(buf, fieldnames=export_service.EXPORT_COLUMNS, extrasaction='ignore')
                        writer.writeheader()
                        yield buf.getvalue()
                        while True:
                            batch = cursor.fetchmany(1000)
                            if not batch:
                                break
                            buf = io.StringIO()
                            writer = csv.DictWriter(buf, fieldnames=export_service.EXPORT_COLUMNS, extrasaction='ignore')
                            for row in batch:
                                writer.writerow({c: ('' if row.get(c) is None else row.get(c)) for c in export_service.EXPORT_COLUMNS})
                            yield buf.getvalue()
                finally:
                    db_close(conn)
            return StreamingResponse(
                gen(), media_type='text/csv; charset=utf-8',
                headers={'Content-Disposition': 'attachment; filename="douyin_data.csv"'},
            )
        tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        tmp.close()
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet()
        ws.append(list(export_service.EXPORT_COLUMNS))
        conn = get_db()
        try:
            with conn.cursor(pymysql.cursors.SSCursor) as cursor:
                cursor.execute(
                    f'SELECT * FROM video_info {where_sql} ORDER BY {sort_by} {order_clause}',
                    tuple(params),
                )
                while True:
                    batch = cursor.fetchmany(1000)
                    if not batch:
                        break
                    for row in batch:
                        ws.append([('' if row.get(c) is None else row.get(c)) for c in export_service.EXPORT_COLUMNS])
        finally:
            db_close(conn)
        wb.save(tmp.name)
        return FileResponse(
            tmp.name,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename='douyin_data.xlsx',
        )
    finally:
        db_close(db)
```

- [ ] **Step 3: 回归验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全部通过。

- [ ] **Step 4: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 导出接口（上限+流式 CSV+xlsx 临时文件）"
```

---

### Task 6: 前端导出按钮 + manifest 描述 + example 配置

**Files:**
- Modify: `frontend/src/pages/Videos.vue`
- Modify: `extension/manifest.json`
- Modify: `local_config.example.py`

- [ ] **Step 1: `Videos.vue` 加导出按钮**

工具栏加：

```html
      <el-button @click="exportCsv">导出 CSV</el-button>
      <el-button @click="exportXlsx">导出 Excel</el-button>
```

script 加：

```ts
function buildExportUrl(format: string) {
  const params = new URLSearchParams()
  if (search.value) params.set('search', search.value)
  if (sortBy.value) params.set('sort_by', sortBy.value)
  if (order.value) params.set('order', order.value)
  if (dateRange.value) {
    params.set('start_date', dateRange.value[0])
    params.set('end_date', dateRange.value[1])
  }
  params.set('format', format)
  return `/api/export?${params.toString()}`
}

function exportCsv() {
  window.location.href = buildExportUrl('csv')
}

function exportXlsx() {
  window.location.href = buildExportUrl('xlsx')
}
```

- [ ] **Step 2: `manifest.json` description 更新**

```json
  "description": "采集自己抖音主页视频的播放量与详情页互动（点赞/评论/分享/收藏）数据，上报到自己的后端。只能采集自己的数据。"
```

- [ ] **Step 3: `local_config.example.py` 加白名单**

```python
# 服务端作者白名单：填写「自己的抖音作者 uid」后，后端只接受该作者的数据，
# 即使插件被改为无限制也无法采集他人数据（合规双保险）。
# 留空 = 不启用服务端白名单（本地开发版默认）。
ALLOWED_AUTHOR_IDS = ['你的抖音作者 uid']
```

- [ ] **Step 4: 构建验证**

```powershell
cd frontend; npm run build
```

Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/pages/Videos.vue extension/manifest.json local_config.example.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 视频数据页导出按钮 + 插件描述 + 作者白名单示例"
```

---

### Task 7: 发布脚本（scripts/build_open_source_release.py，TDD）

**Files:**
- Create: `scripts/build_open_source_release.py`
- Test: `tests/test_release_script.py`

- [ ] **Step 1: 写失败测试（新建 `tests/test_release_script.py`）**

```python
"""发布脚本：白名单复制与默认模式替换。"""
import importlib.util


def _load_script():
    spec = importlib.util.spec_from_file_location('build_release', 'scripts/build_open_source_release.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_release_keep_list_has_core_files():
    keep = _load_script().KEEP_FILES
    assert any('api.py' in p for p in keep)
    assert any('extension_receiver.py' in p for p in keep)
    assert any('frontend/src/pages/Videos.vue' in p for p in keep)


def test_release_keep_list_excludes_crawler():
    keep = _load_script().KEEP_FILES
    assert not any('douyin_spider' in p for p in keep)
    assert not any('collector.py' in p for p in keep)


def test_replace_default_mode_limited():
    mod = _load_script()
    src = "modeSel.value = data[MODE_KEY] || 'unlimited'"
    assert mod.replace_default_mode(src) == "modeSel.value = data[MODE_KEY] || 'limited'"
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_script.py -q
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 `scripts/build_open_source_release.py`**

```python
"""从主仓库生成开源发布包（白名单复制 + 默认模式替换 + 构建前端）。

运行：python scripts/build_open_source_release.py
输出：release/open-source/（git 初始化，不自动 push）
"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'release', 'open-source')

KEEP_FILES = [
    'api.py', 'analyzer.py', 'cleanup_service.py', 'export_service.py',
    'extension_receiver.py', 'time_filter.py', 'run_backend.ps1', 'stop_backend.ps1',
    'local_config.example.py', 'LICENSE', '.gitignore',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.ts',
    'frontend/tsconfig.json', 'frontend/index.html', 'frontend/src/',
    'extension/', 'tests/', 'requirements.txt',
]

EXCLUDE_FILES = [
    'frontend/src/pages/Dashboard.vue',
    'frontend/src/pages/Collect.vue',
    'frontend/src/pages/Quality.vue',
    'frontend/src/pages/Queue.vue',
    'frontend/src/components/PieChart.vue',
]


def replace_default_mode(text: str) -> str:
    return text.replace("'unlimited'", "'limited'").replace('"unlimited"', '"limited"')


def _copy(path):
    src = os.path.join(ROOT, path)
    dst = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for path in KEEP_FILES:
        if os.path.exists(os.path.join(ROOT, path)):
            _copy(path)
    for rel in EXCLUDE_FILES:
        p = os.path.join(OUT, rel)
        if os.path.exists(p):
            os.remove(p)
    _trim_frontend()
    for rel in ('extension/options/options.js', 'extension/content/collect.js'):
        p = os.path.join(OUT, rel)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                text = f.read()
            with open(p, 'w', encoding='utf-8') as f:
                f.write(replace_default_mode(text))
    frontend = os.path.join(OUT, 'frontend')
    subprocess.run(['npm', 'install'], cwd=frontend, check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=frontend, check=True)
    subprocess.run(['git', 'init'], cwd=OUT, check=True)
    print(f'开源包已生成：{OUT}')
    print('请 review 后自行推送到开源仓库（脚本不自动 push）。')


def _trim_frontend():
    """开源版前端只保留「视频数据」「个人分析」两个路由与菜单。"""
    router = os.path.join(OUT, 'frontend', 'src', 'router', 'index.ts')
    with open(router, 'w', encoding='utf-8') as f:
        f.write("""import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'

export default createRouter({
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', name: 'videos', component: () => import('../pages/Videos.vue'), meta: { title: '视频数据' } },
        { path: 'personal', name: 'personal', component: () => import('../pages/PersonalAnalyzer.vue'), meta: { title: '个人分析' } },
      ],
    },
  ],
})
""")
    layout = os.path.join(OUT, 'frontend', 'src', 'layouts', 'MainLayout.vue')
    with open(layout, 'r', encoding='utf-8') as f:
        text = f.read()
    text = text.replace(
        "  { index: '/', label: '数据总览' },\n"
        "  { index: '/queue', label: '爬虫复核' },\n"
        "  { index: '/videos', label: '视频数据' },\n"
        "  { index: '/collect', label: '爬虫任务导入' },\n"
        "  { index: '/quality', label: '数据质量' },\n"
        "  { index: '/personal', label: '个人分析' },\n",
        "  { index: '/', label: '视频数据' },\n"
        "  { index: '/personal', label: '个人分析' },\n",
    )
    with open(layout, 'w', encoding='utf-8') as f:
        f.write(text)


if __name__ == '__main__':
    build()
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_script.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add scripts/build_open_source_release.py tests/test_release_script.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 开源发布脚本（白名单复制+默认模式替换+构建前端）"
```

---

### Task 8: 开源版 README 与 requirements 模板

**Files:**
- Create: `scripts/open_source_README.md`
- Create: `scripts/open_source_requirements.txt`

- [ ] **Step 1: 写开源版 README**

新建 `scripts/open_source_README.md`：

```markdown
# 抖音创作者数据分析器

个人自采集 + 自分析工具：浏览器插件只采集登录账号自己的抖音主页/详情数据，本地后端接收并分析（播放量/点赞/评论/分享/收藏、互动率、收藏率、完整度、时间检索、导出）。

## 快速开始

```bash
pip install -r requirements.txt
cp local_config.example.py local_config.py
# 编辑 local_config.py：填 MySQL 密码、你的抖音作者 uid（ALLOWED_AUTHOR_IDS）、随机令牌 EXTENSION_API_TOKEN
python -m uvicorn api:app --host 127.0.0.1 --port 8001
```

1. Chrome 打开 `chrome://extensions`，开启开发者模式，点「加载已解压的扩展程序」，选择 `extension/`；
2. 点插件图标，填后端地址 `http://127.0.0.1:8001`、令牌（与 local_config.py 一致），采集模式保持「仅自己」；
3. 登录抖音，进入自己的主页点「开始采集」，浏览自己视频详情页自动补全互动与收藏。

## 合规声明

本项目仅供学习与研究，默认仅采集登录账号自己的数据。请遵守抖音用户协议与相关法律法规，勿用于采集他人数据或商业用途。
```

- [ ] **Step 2: 写精简 requirements 模板**

新建 `scripts/open_source_requirements.txt`：

```text
fastapi
uvicorn
pymysql
pandas
openpyxl
pydantic
```

- [ ] **Step 3: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add scripts/open_source_README.md scripts/open_source_requirements.txt
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 开源版 README 与精简 requirements 模板"
```

---

### Task 9: 全量回归

**Files:** 无

- [ ] **Step 1: 后端全量测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 148 + 本计划新增用例全部通过。

- [ ] **Step 2: 插件全量测试**

```powershell
cd extension; node --test
```

Expected: 32 passed。

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

### Task 10: 真机验证与交接

**Files:**
- Modify: `docs/superpowers/handoff/2026-08-12-new-window-handoff.md`

- [ ] **Step 1: 重启后端验证**

经用户确认 `.\stop_backend.ps1` + `.\run_backend.ps1` 后验证：

```text
GET  /api/export?format=csv&start_date=...    → 下载 CSV（含 collect_count 列）
GET  /api/export?format=xlsx                  → 下载 xlsx
GET  /api/cleanup/status                      → 读取 JSON 配置（默认 enabled=false）
POST /api/cleanup/settings {"batch_size":300,"authors":[]} → 写入 JSON 后 status 一致
POST /api/extension/videos（白名单外 author_id）→ rejected 含「作者不在允许列表内」
```

- [ ] **Step 2: 运行发布脚本（联网/构建，需用户确认）**

```powershell
.\.venv\Scripts\python.exe scripts/build_open_source_release.py
```

检查 `release/open-source/` 含 `frontend/dist`、无 `douyin_spider/`、插件默认值为 limited。

- [ ] **Step 3: 更新交接文档**

追加开源版发布准备条目、验证基线数字、下一步（云部署）。

- [ ] **Step 4: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add docs/superpowers/handoff/2026-08-12-new-window-handoff.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 开源发布准备完成收尾"
```
