# 抖音个人视频数据分析器（浏览器插件版）MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让博主在真实浏览器里用 Chrome 插件采集**自己主页**视频的播放量、以及自己视频详情页的点赞/评论/分享，上报到现有 FastAPI 后端并 upsert 进 `video_info` 表，看板新增「个人分析」页做聚合分析。

**Architecture:** 三层：`extension/`（MV3 插件：主页卡片 DOM 解析 + 详情页 DOM 解析 + 白名单校验 + 限速上报）→ `extension_receiver.py` 纯逻辑校验/去重/构建部分更新 SQL → `api.py` 薄接口 upsert；`analyzer.py` 纯逻辑聚合 → `api.py` 查询 → `PersonalAnalyzer.vue` 看板页。全程不改数据库表结构，爬虫链路不参与。

**Tech Stack:** Chrome Manifest V3 / 原生 JS（插件）；Python 3.13 / FastAPI / PyMySQL（后端）；Vue 3 + Element Plus + ECharts（看板）；Node 24 内置 `node --test` + jsdom（插件解析单测）；pytest（后端单测）。

---

## 前置约定（本仓库环境）

- 当前分支：`codex/personal-analyzer-extension`；设计已定稿：
  `docs/superpowers/specs/2026-08-11-personal-analyzer-extension-design.md`
- 后端单测命令：`.\.venv\Scripts\python.exe -m pytest tests/<file> -q -p no:cacheprovider`
- 全量回归基线：当前 `51 passed`（pandas 版本警告可忽略）
- 插件 Node 测试：先 `cd extension; npm install`（需提权联网，装 jsdom），
  再 `node --test tests/`（在 extension 目录下）
- 前端构建：`cd frontend; npm run build`（vue-tsc + vite）
- git 命令一律加 `-c safe.directory=D:/DjangoProject/PythonProject11`，
  `add/commit` 等写操作需在提权 shell 执行；只 add 明确路径，绝不用 `git add .`
- MySQL：`127.0.0.1:3307` / 库 `douyin_spider`（本机运行中）；
  真库验证一律使用 `ext_test_` 前缀的自建测试行，验证后清理，不动用户数据
- `.gitignore` 需先补两条规则（见 Task 5）：
  `extension/node_modules/` 与 `!extension/**/*.html`（当前 `*.html` 全局规则会误伤插件 options 页）
- 严禁提交：`Codex Image 2026年8月10日 14_58_08.png`（用户截图）、`local_config.py`、日志

## 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `extension_receiver.py` | 接收器纯逻辑：字段校验/归一化/批次内去重/部分更新 SQL | 新建 |
| `tests/test_extension_receiver.py` | 接收器单测 | 新建 |
| `analyzer.py` | 个人分析聚合：概览/趋势/Top 视频 | 新建 |
| `tests/test_analyzer.py` | 聚合单测 | 新建 |
| `api.py` | 新增接收接口 + 分析接口（薄层） | 修改 |
| `extension/manifest.json` | MV3 清单 | 新建 |
| `extension/content/parse.js` | 纯 DOM 解析（主页卡片 + 详情页 + parseCount） | 新建 |
| `extension/content/collect.js` | content script：主页模式 + 详情页模式 | 新建 |
| `extension/options/options.html` / `options.js` | 后端地址配置页 | 新建 |
| `extension/package.json` | 插件测试依赖（jsdom） | 新建 |
| `extension/tests/parse.test.mjs` | parse.js Node 单测（两组 fixture） | 新建 |
| `extension/README.md` | 插件安装/配置/合规说明 | 新建 |
| `frontend/src/pages/PersonalAnalyzer.vue` | 个人分析页 | 新建 |
| `frontend/src/router/index.ts` | 新增 `/personal` 路由 | 修改 |
| `frontend/src/layouts/MainLayout.vue` | 侧边栏加「个人分析」 | 修改 |
| `.gitignore` | 补 extension 规则 | 修改 |
| `README.md` | 项目总 README：插件安装/合规/已知限制 | 修改 |

---

## 阶段 1：后端接收器

### Task 1: extension_receiver.py 基础校验函数

**Files:**
- Create: `tests/test_extension_receiver.py`
- Create: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_extension_receiver.py`：

```python
"""浏览器插件接收器：字段校验/归一化/去重/部分更新 SQL。"""
from datetime import datetime

from extension_receiver import (
    MAX_BATCH,
    parse_count,
    parse_datetime,
    validate_source_url,
    validate_video_id,
)


def test_validate_video_id():
    assert validate_video_id('7638884656238410714') is True
    assert validate_video_id(' 7638884656238410714 ') is True
    assert validate_video_id('123') is False
    assert validate_video_id('abc12345678901234') is False
    assert validate_video_id('') is False
    assert validate_video_id(None) is False
    assert validate_video_id(7638884656238410714) is False


def test_validate_source_url():
    assert validate_source_url('https://www.douyin.com/user/MS4wLjABAAAA123') is True
    assert validate_source_url('https://www.douyin.com/user/self') is True
    assert validate_source_url('https://www.douyin.com/video/123') is False
    assert validate_source_url('https://evil.com/user/MS4wLjABAAAA123') is False
    assert validate_source_url('') is False


def test_parse_datetime_accepts_iso_and_space_formats():
    assert isinstance(parse_datetime('2026-05-12T14:13:52'), datetime)
    assert isinstance(parse_datetime('2026-05-12 14:13:52'), datetime)
    assert isinstance(parse_datetime('2026-05-12'), datetime)
    assert parse_datetime('垃圾数据') is None
    assert parse_datetime(None) is None
    assert parse_datetime('') is None


def test_parse_count_accepts_int_and_digit_string():
    assert parse_count(236) == 236
    assert parse_count('236') == 236
    assert parse_count(0) == 0
    assert parse_count('4.0') == 4


def test_parse_count_rejects_negative_and_non_numeric():
    assert parse_count(-1) is None
    assert parse_count('4.0万') is None
    assert parse_count('abc') is None
    assert parse_count(2.5) is None
    assert parse_count(None) is None


def test_max_batch_constant():
    assert MAX_BATCH == 100
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: FAIL（`ModuleNotFoundError: No module named 'extension_receiver'`）

- [ ] **Step 3: 最小实现**

新建 `extension_receiver.py`：

```python
"""浏览器插件数据接收器：字段校验、归一化、批次内去重、部分更新 SQL 构建。

纯逻辑模块（与 quality.py 同模式），api.py 只做薄层调用。
"""
import re
from datetime import datetime
from typing import Any, Optional

MAX_BATCH = 100
VIDEO_ID_RE = re.compile(r'^\d{15,20}$')
SOURCE_URL_RE = re.compile(r'^https://www\.douyin\.com/user/[^/?#]+/?$')
HTTP_URL_RE = re.compile(r'^https?://\S+$')

COUNT_FIELDS = ('like_count', 'comment_count', 'share_count', 'play_count')
TEXT_LIMITS = {
    'video_title': 512,
    'video_desc': 5000,
    'author_name': 128,
    'author_id': 64,
    'video_url': 2048,
    'cover_url': 1024,
}


def validate_video_id(video_id: Any) -> bool:
    """video_id 必须是 15-20 位纯数字字符串。"""
    return isinstance(video_id, str) and bool(VIDEO_ID_RE.match(video_id.strip()))


def validate_source_url(url: Any) -> bool:
    """source_url 必须是抖音用户主页链接。"""
    return isinstance(url, str) and bool(SOURCE_URL_RE.match(url.strip()))


def parse_datetime(value: Any) -> Optional[datetime]:
    """接受 ISO 8601 / 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD'；无效返回 None（不拒绝）。"""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def parse_count(value: Any) -> Optional[int]:
    """接受 int / 数字字符串；负数、小数、非数字返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and re.fullmatch(r'\d+(?:\.\d+)?', value.strip()):
        number = float(value)
    else:
        return None
    if number < 0 or number != int(number):
        return None
    return int(number)
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 接收器基础校验（video_id/source_url/datetime/数字）"
```

### Task 2: normalize_record 与 validate_batch（含 author 一致性/上限）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_extension_receiver.py` 追加：

```python
from extension_receiver import normalize_record, validate_batch


def test_normalize_record_defaults():
    record, reason = normalize_record({'video_id': '7638884656238410714'})
    assert reason is None
    assert record['video_id'] == '7638884656238410714'
    assert record['video_title'] == ''
    assert record['author_name'] == ''
    assert record['publish_time'] is None
    assert record['like_count'] is None
    assert record['play_count'] is None


def test_normalize_record_strips_and_limits_text():
    record, _ = normalize_record({
        'video_id': '7638884656238410714',
        'video_title': '  标题  ',
        'author_name': 'a' * 200,
    })
    assert record is None
    record, _ = normalize_record({
        'video_id': '7638884656238410714',
        'video_title': '  标题  ',
    })
    assert record['video_title'] == '标题'


def test_normalize_record_rejects_bad_counts():
    record, reason = normalize_record({
        'video_id': '7638884656238410714',
        'like_count': -5,
    })
    assert record is None and reason


def test_validate_batch_requires_valid_source_url():
    payload = {'source_url': 'https://www.douyin.com/video/123', 'videos': []}
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert rejected and rejected[0]['reason']


def test_validate_batch_enforces_batch_limit():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [{'video_id': '7638884656238410714'} for _ in range(101)],
    }
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert rejected[0]['reason']


def test_validate_batch_rejects_mixed_authors():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [
            {'video_id': '7638884656238410714', 'author_id': 'A'},
            {'video_id': '7638884656238410715', 'author_id': 'B'},
        ],
    }
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert any('author_id' in r['reason'] for r in rejected)


def test_validate_batch_passes_clean_batch():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [
            {
                'video_id': '7638884656238410714',
                'video_title': '标题A',
                'like_count': 40000,
                'author_id': 'A',
            },
            {
                'video_id': '7638884656238410715',
                'video_title': '标题B',
                'author_id': 'A',
            },
        ],
    }
    valid, rejected = validate_batch(payload)
    assert rejected == []
    assert len(valid) == 2
    assert valid[0]['like_count'] == 40000
    assert valid[1]['like_count'] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'normalize_record'`）

- [ ] **Step 3: 最小实现**

在 `extension_receiver.py` 追加：

```python
def normalize_record(raw: dict) -> tuple[Optional[dict], Optional[str]]:
    """校验并归一化单条记录；返回 (record, None) 或 (None, reason)。

    字段语义：count 字段 None 表示「本批未采集」，upsert 时跳过更新；
    文本字段 None/缺失 → 空串；publish_time 无效值 → None（不拒绝）。
    """
    video_id = raw.get('video_id') or ''
    video_id = video_id.strip() if isinstance(video_id, str) else ''
    if not validate_video_id(video_id):
        return None, 'video_id 必须为 15-20 位数字'

    record: dict[str, Any] = {'video_id': video_id}
    for field in TEXT_LIMITS:
        value = raw.get(field)
        if value is None:
            record[field] = ''
        elif isinstance(value, str):
            cleaned = value.strip()
            if len(cleaned) > TEXT_LIMITS[field]:
                return None, f'{field} 长度超限'
            record[field] = cleaned
        else:
            return None, f'{field} 必须是字符串'

    record['publish_time'] = parse_datetime(raw.get('publish_time'))

    for field in COUNT_FIELDS:
        value = raw.get(field)
        if value is None:
            record[field] = None
            continue
        parsed = parse_count(value)
        if parsed is None:
            return None, f'{field} 必须是非负整数'
        record[field] = parsed

    for field in ('video_url', 'cover_url'):
        url = record[field]
        if url and not HTTP_URL_RE.match(url):
            return None, f'{field} 必须是 http(s) 链接'
    return record, None


def validate_batch(payload: dict) -> tuple[list[dict], list[dict]]:
    """整批校验：source_url、长度上限、author 一致性、逐条校验。
    返回 (valid_records, rejected)；批次级错误以 rejected 单条 reason 表达。
    """
    source_url = payload.get('source_url') or ''
    if not validate_source_url(source_url):
        return [], [{'video_id': '', 'reason': 'source_url 必须是抖音用户主页链接'}]

    videos = payload.get('videos')
    if not isinstance(videos, list) or not (1 <= len(videos) <= MAX_BATCH):
        return [], [{'video_id': '', 'reason': f'videos 必须是 1-{MAX_BATCH} 条'}]

    author_ids = {
        str(v.get('author_id', '')).strip()
        for v in videos
        if isinstance(v, dict) and v.get('author_id')
    }
    if len(author_ids) > 1:
        return [], [{'video_id': '', 'reason': '同一批次所有记录的 author_id 必须一致'}]

    valid: list[dict] = []
    rejected: list[dict] = []
    for v in videos:
        if not isinstance(v, dict):
            rejected.append({'video_id': '', 'reason': '记录必须是对象'})
            continue
        record, reason = normalize_record(v)
        if record is None:
            rejected.append({
                'video_id': str(v.get('video_id', ''))[:64],
                'reason': reason or '记录校验失败',
            })
        else:
            valid.append(record)
    return valid, rejected
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: PASS（14 passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 记录归一化与整批校验（author 一致性/批次上限）"
```

### Task 3: dedupe_records 与 build_upsert（部分更新）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_extension_receiver.py` 追加：

```python
from extension_receiver import build_upsert, dedupe_records


def test_dedupe_records_keeps_first_by_video_id():
    records = [
        {'video_id': '1', 'play_count': 10},
        {'video_id': '2', 'play_count': 20},
        {'video_id': '1', 'play_count': 99},
    ]
    result = dedupe_records(records)
    assert [r['video_id'] for r in result] == ['1', '2']
    assert result[0]['play_count'] == 10


def test_build_upsert_skips_none_fields():
    record = {
        'video_id': '7638884656238410714',
        'video_title': '标题',
        'video_desc': '',
        'author_name': '我',
        'author_id': 'A',
        'publish_time': None,
        'like_count': None,
        'comment_count': None,
        'share_count': None,
        'play_count': 236,
        'video_url': '',
        'cover_url': '',
    }
    sql, params = build_upsert(record)
    assert 'like_count' not in sql
    assert 'play_count=VALUES(play_count)' in sql
    assert 'crawl_time=NOW()' in sql
    assert params[0] == '7638884656238410714'
    assert params[9] == 236


def test_build_upsert_includes_present_count_fields():
    record = {
        'video_id': '7638884656238410714',
        'video_title': '标题',
        'video_desc': '',
        'author_name': '我',
        'author_id': 'A',
        'publish_time': None,
        'like_count': 40000,
        'comment_count': 481,
        'share_count': 1150,
        'play_count': None,
        'video_url': '',
        'cover_url': '',
    }
    sql, _ = build_upsert(record)
    assert 'like_count=VALUES(like_count)' in sql
    assert 'play_count' not in sql
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'dedupe_records'`）

- [ ] **Step 3: 最小实现**

在 `extension_receiver.py` 追加：

```python
INSERT_COLUMNS = (
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'play_count',
    'video_url', 'cover_url',
)


def dedupe_records(records: list[dict]) -> list[dict]:
    """批次内按 video_id 去重，保留第一条。"""
    seen: set[str] = set()
    result: list[dict] = []
    for record in records:
        video_id = record['video_id']
        if video_id in seen:
            continue
        seen.add(video_id)
        result.append(record)
    return result


def build_upsert(record: dict) -> tuple[str, tuple]:
    """构建部分更新 upsert SQL。

    - INSERT 写入全部 12 字段（None → NULL）；
    - ON DUPLICATE KEY UPDATE 只更新非 None 字段 + crawl_time/update_time，
      因此主页层（play_count 有值、互动为 None）不会覆盖详情页已补的互动数据。
    """
    values = [record.get(c) for c in INSERT_COLUMNS]
    placeholders = ', '.join(['%s'] * len(INSERT_COLUMNS))
    update_cols = [c for c in INSERT_COLUMNS[1:] if record.get(c) is not None]
    updates = [f'{c}=VALUES({c})' for c in update_cols]
    updates.append('crawl_time=NOW()')
    updates.append('update_time=NOW()')
    sql = (
        f'INSERT INTO video_info ({", ".join(INSERT_COLUMNS)}, crawl_time) '
        f'VALUES ({placeholders}, NOW()) '
        f'ON DUPLICATE KEY UPDATE {", ".join(updates)}'
    )
    return sql, tuple(values)
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: PASS（17 passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 批次内去重与部分更新 upsert（None 字段不覆盖旧值）"
```

### Task 4: POST /api/extension/videos 接口 + 真库验证

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 在 api.py 顶部加导入**

```python
import extension_receiver
```

- [ ] **Step 2: 追加接收接口（放在 `@app.get('/api/quality/export')` 之后、`FRONTEND_DIR` 之前）**

```python
class ExtensionVideosRequest(BaseModel):
    source_url: str
    videos: list[dict]


@app.post('/api/extension/videos')
def extension_receive(req: ExtensionVideosRequest):
    """浏览器插件数据接收器：校验 → 批次内去重 → 部分更新 upsert。"""
    valid, rejected = extension_receiver.validate_batch(req.model_dump())
    if not valid and not rejected:
        raise HTTPException(status_code=400, detail='没有可处理的记录')
    records = extension_receiver.dedupe_records(valid)
    db = get_db()
    try:
        with db.cursor() as cursor:
            for record in records:
                sql, params = extension_receiver.build_upsert(record)
                cursor.execute(sql, params)
            db.commit()
    finally:
        db_close(db)
    return {
        'source_url': req.source_url,
        'accepted': len(valid),
        'upserted': len(records),
        'rejected': rejected,
    }
```

- [ ] **Step 3: 启动/重启后端并做真库验证（提权 shell）**

后端当前未运行（端口 8001 无监听）。启动：

```powershell
$conn = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($conn) { $conn.OwningProcess | Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
Start-Sleep -Seconds 2
$env:PYTHONUTF8='1'
Start-Process -FilePath 'D:\DjangoProject\PythonProject11\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','api:app','--host','127.0.0.1','--port','8001' -WorkingDirectory 'D:\DjangoProject\PythonProject11' -WindowStyle Hidden -RedirectStandardOutput 'D:\DjangoProject\PythonProject11\backend.out.log' -RedirectStandardError 'D:\DjangoProject\PythonProject11\backend.err.log'
Start-Sleep -Seconds 6
Test-NetConnection 127.0.0.1 -Port 8001 -InformationLevel Quiet
```

Expected: `True`

再验证接口（先插入两条 `ext_test_` 行，再重复提交验证去重与部分更新）：

```powershell
$body1 = @{
  source_url = 'https://www.douyin.com/user/MS4wLjABAAAA_test'
  videos = @(
    @{ video_id = '20260811999900001'; video_title = '主页标题1'; play_count = 236; author_name = '测试作者'; author_id = 'ext_test_author' },
    @{ video_id = '20260811999900002'; video_title = '主页标题2'; play_count = 1200; author_name = '测试作者'; author_id = 'ext_test_author' }
  )
} | ConvertTo-Json -Depth 5
$r1 = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/videos' -Method Post -ContentType 'application/json' -Body $body1
Write-Output ("accepted=" + $r1.accepted + " upserted=" + $r1.upserted + " rejected=" + $r1.rejected.Count)
```

Expected: `accepted=2 upserted=2 rejected=0`

```powershell
$body2 = @{
  source_url = 'https://www.douyin.com/user/MS4wLjABAAAA_test'
  videos = @(
    @{ video_id = '20260811999900001'; video_title = '主页标题1'; play_count = 236; like_count = 40000; comment_count = 481; share_count = 1150; author_name = '测试作者'; author_id = 'ext_test_author' }
  )
} | ConvertTo-Json -Depth 5
$r2 = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/videos' -Method Post -ContentType 'application/json' -Body $body2
Write-Output ("accepted=" + $r2.accepted + " upserted=" + $r2.upserted)
$row = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/videos/20260811999900001' -TimeoutSec 5
Write-Output ("like=" + $row.like_count + " comment=" + $row.comment_count + " play=" + $row.play_count)
```

Expected: `accepted=1 upserted=1`，且 `like=40000 comment=481 play=236`
（play_count 未被详情页批次的 None 覆盖——部分更新生效）

再验证坏数据被拒：

```powershell
$body3 = @{
  source_url = 'https://www.douyin.com/user/MS4wLjABAAAA_test'
  videos = @(
    @{ video_id = 'not-a-video-id'; video_title = 'x' },
    @{ video_id = '20260811999900003'; video_title = 'ok'; like_count = -1 }
  )
} | ConvertTo-Json -Depth 5
$r3 = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/videos' -Method Post -ContentType 'application/json' -Body $body3
Write-Output ("accepted=" + $r3.accepted + " rejected=" + $r3.rejected.Count)
```

Expected: `accepted=0 rejected=2`

- [ ] **Step 4: 清理测试行（只删自建 ext_test_ 数据，提权 shell）**

```powershell
mysql -h 127.0.0.1 -P 3307 -u root -p20061006 douyin_spider -e "DELETE FROM video_info WHERE author_id = 'ext_test_author'; SELECT COUNT(*) AS left_cnt FROM video_info WHERE author_id = 'ext_test_author';"
```

Expected: `left_cnt=0`

- [ ] **Step 5: 全量回归 + 提交**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过（原 51 + 新增 17 = 68 passed）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 浏览器插件数据接收接口 POST /api/extension/videos"
```

---

## 阶段 2：浏览器插件

### Task 5: 工程骨架（.gitignore / manifest / 测试依赖）

**Files:**
- Modify: `.gitignore`
- Create: `extension/manifest.json`
- Create: `extension/package.json`

- [ ] **Step 1: 修改 .gitignore**

在 `.gitignore` 的 `# Frontend build artifacts` 段后追加：

```gitignore
# 浏览器插件
extension/node_modules/
!extension/**/*.html
```

说明：`*.html` 全局规则会忽略插件 `options/options.html`，必须用 `!extension/**/*.html` 取消；
`extension/node_modules/` 不提交。

- [ ] **Step 2: 新建 `extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "抖音个人视频数据分析器",
  "version": "0.1.0",
  "description": "采集自己抖音主页视频的播放量与详情页的点赞/评论/分享数据，上报到本地后端。只能采集自己的数据。",
  "permissions": ["storage"],
  "host_permissions": [
    "https://www.douyin.com/*",
    "http://127.0.0.1:8001/*",
    "http://localhost:8001/*"
  ],
  "content_scripts": [
    {
      "matches": ["https://www.douyin.com/*"],
      "js": ["content/parse.js", "content/collect.js"],
      "run_at": "document_idle"
    }
  ],
  "action": {
    "default_title": "抖音个人视频数据分析器 - 设置",
    "default_popup": "options/options.html"
  },
  "options_ui": {
    "page": "options/options.html",
    "open_in_tab": false
  }
}
```

- [ ] **Step 3: 新建 `extension/package.json`（仅测试依赖）**

```json
{
  "name": "douyin-personal-analyzer-extension",
  "private": true,
  "version": "0.1.0",
  "description": "抖音个人视频数据分析器插件（源码 + Node 测试依赖）",
  "scripts": {
    "test": "node --test tests/"
  },
  "devDependencies": {
    "jsdom": "^25.0.1"
  }
}
```

- [ ] **Step 4: 安装 jsdom（提权 shell，联网）**

```powershell
cd D:\DjangoProject\PythonProject11\extension
npm install
node -e "console.log(require('jsdom/package.json').version)"
```

Expected: 打印 jsdom 版本号（如 `25.0.1`），无报错。

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add .gitignore extension/manifest.json extension/package.json extension/package-lock.json
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件工程骨架（MV3 清单 + 测试依赖 + gitignore 规则）"
```

### Task 6: parse.js —— parseCount / extractSecUidFromHref / parseProfileCards

**Files:**
- Create: `extension/content/parse.js`
- Create: `extension/tests/parse.test.mjs`

- [ ] **Step 1: 写失败测试（Node 内置测试 + jsdom fixture）**

新建 `extension/tests/parse.test.mjs`：

```js
import { createRequire } from 'node:module'
import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const {
  parseCount,
  extractSecUidFromHref,
  parseProfileCards,
} = require('../content/parse.js')

function domOf(html) {
  return new JSDOM(html)
}

const PROFILE_HTML = `
<div data-e2e="user-post-list"><ul>
  <li>
    <div><a href="/video/7672018085449279859?count=10&amp;secUid=MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl">
      <div class="GGxeUe0C">
        <div><img src="https://p3-pc-sign.douyinpic.com/coverA.jpeg?x-signature=abc" alt=""></div>
        <div class="jXmtohcJ"><span class="icon"></span><span class="BP1CQkLg">236</span></div>
        <p class="EB3BkdQ8">标题A</p>
      </div>
      <p class="frUrWD64">标题A</p>
    </a></div>
  </li>
  <li>
    <div><a href="/video/7672018085449279860?secUid=MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl">
      <div><img src="https://p3-pc-sign.douyinpic.com/coverB.jpeg" alt=""></div>
      <div class="jXmtohcJ"><span class="icon"></span><span>1.2万</span></div>
      <p class="frUrWD64">标题B</p>
    </a></div>
  </li>
  <li>
    <div><a href="/note/7647172401004949235">
      <div><img src="https://p3-pc-sign.douyinpic.com/coverC.jpeg" alt=""></div>
      <p class="frUrWD64">这是一篇图文</p>
    </a></div>
  </li>
</ul></div>
`

test('parseCount 支持纯数字/万/亿/千分位', () => {
  assert.equal(parseCount('236'), 236)
  assert.equal(parseCount('4.0万'), 40000)
  assert.equal(parseCount('1.2亿'), 120000000)
  assert.equal(parseCount('4,000'), 4000)
  assert.equal(parseCount('abc'), null)
  assert.equal(parseCount(null), null)
})

test('extractSecUidFromHref 提取作者 secUid', () => {
  assert.equal(
    extractSecUidFromHref('//www.douyin.com/user/MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI'),
    'MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI',
  )
  assert.equal(extractSecUidFromHref('/video/123'), '')
})

test('parseProfileCards 提取视频卡片字段', () => {
  const { document } = domOf(PROFILE_HTML).window
  const root = document.querySelector('[data-e2e="user-post-list"]')
  const cards = parseProfileCards(root, {
    author_name: '黑白阿巴巴',
    author_id: '4358913414407163',
  })
  assert.equal(cards.length, 2)
  assert.equal(cards[0].video_id, '7672018085449279859')
  assert.equal(cards[0].video_title, '标题A')
  assert.equal(cards[0].play_count, 236)
  assert.equal(cards[0].cover_url, 'https://p3-pc-sign.douyinpic.com/coverA.jpeg?x-signature=abc')
  assert.equal(cards[0].author_name, '黑白阿巴巴')
  assert.equal(cards[0].author_id, '4358913414407163')
  assert.equal(cards[0].sec_uid, 'MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl')
  assert.deepEqual(cards[0].missing_fields, [])
})

test('parseProfileCards 支持万格式并跳过图文', () => {
  const { document } = domOf(PROFILE_HTML).window
  const cards = parseProfileCards(document.querySelector('[data-e2e="user-post-list"]'), {})
  assert.equal(cards[1].play_count, 12000)
  assert.ok(!cards.some((c) => c.video_id === '7647172401004949235'))
})

test('parseProfileCards 统计缺失字段', () => {
  const html = `
  <div data-e2e="user-post-list"><ul>
    <li><div><a href="/video/7672018085449279899"><div><div class="jXmtohcJ"><span class="icon"></span><span></span></div></div></a></div></li>
  </ul></div>`
  const { document } = domOf(html).window
  const cards = parseProfileCards(document.querySelector('[data-e2e="user-post-list"]'), {})
  assert.equal(cards.length, 1)
  assert.ok(cards[0].missing_fields.includes('video_title'))
  assert.ok(cards[0].missing_fields.includes('play_count'))
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd extension; node --test tests/`
Expected: FAIL（`Cannot find module '../content/parse.js'`）

- [ ] **Step 3: 最小实现**

新建 `extension/content/parse.js`：

```js
/* 抖音个人视频数据分析器 —— 纯 DOM 解析函数
 * 浏览器 content script 与 Node(jsdom) 测试共用；
 * 解析以 data-e2e + 结构定位为主，哈希 class 只作候选兜底。
 */
(function (root) {
  'use strict';

  /** 解析互动数字：236 / 4.0万 / 1.2亿 / 4,000 → 整数；失败返回 null。 */
  function parseCount(text) {
    if (text === null || text === undefined) return null;
    const t = String(text).trim().replace(/,/g, '');
    const m = t.match(/^(\d+(?:\.\d+)?)(\u4e07|\u4ebf)?$/); // 万|亿
    if (!m) return null;
    const n = parseFloat(m[1]);
    const unit = m[2];
    let value = n;
    if (unit === '\u4ebf') value = n * 1e8;      // 亿
    else if (unit === '\u4e07') value = n * 1e4; // 万
    return Math.round(value);
  }

  /** 从作者主页链接提取 secUid。 */
  function extractSecUidFromHref(href) {
    const m = String(href || '').match(/\/user\/(MS4wLj[^/?#]*)/);
    return m ? m[1] : '';
  }

  /** 在容器内找第一个「纯数字/万/亿」文本元素并解析。 */
  function countIn(el) {
    if (!el) return null;
    const nodes = el.querySelectorAll('div, span');
    for (const node of nodes) {
      const t = (node.textContent || '').trim();
      if (t && /^[\d.,\u4e07\u4ebf]+$/.test(t)) {
        const v = parseCount(t);
        if (v !== null) return v;
      }
    }
    return null;
  }

  /**
   * 解析主页作品列表（div[data-e2e="user-post-list"] > ul > li）。
   * @param {Element} root 列表容器
   * @param {{author_name?: string, author_id?: string}} author 作者信息（来自 RENDER_DATA）
   * @returns {Array<object>} 每条含 video_id/video_title/play_count/cover_url/
   *                          author_name/author_id/missing_fields；图文与无 video_id 卡片跳过。
   */
  function parseProfileCards(root, author) {
    const results = [];
    if (!root) return results;
    for (const li of root.querySelectorAll('li')) {
      const videoLink = li.querySelector('a[href*="/video/"]');
      if (!videoLink) continue; // 图文 /note/ 或其它卡片 → 跳过
      const href = videoLink.getAttribute('href') || '';
      const m = href.match(/\/video\/(\d+)/);
      if (!m) continue; // 连 video_id 都取不到 → 跳过
      const video_id = m[1];
      const missing = [];

      const titleEl = li.querySelector('p.frUrWD64') || li.querySelector('p.EB3BkdQ8');
      const video_title = titleEl ? (titleEl.textContent || '').trim() : '';
      if (!video_title) missing.push('video_title');

      const playValue = countIn(li.querySelector('div.jXmtohcJ'));
      const play_count = playValue === null ? 0 : playValue;
      if (playValue === null) missing.push('play_count');

      const img = li.querySelector('img');
      const cover_url = img ? (img.getAttribute('src') || '') : '';
      if (!cover_url) missing.push('cover_url');

      results.push({
        video_id: video_id,
        video_title: video_title,
        play_count: play_count,
        cover_url: cover_url,
        sec_uid: extractSecUidFromHref(href),
        author_name: (author && author.author_name) || '',
        author_id: (author && author.author_id) || '',
        missing_fields: missing,
      });
    }
    return results;
  }

  const api = { parseCount, extractSecUidFromHref, parseProfileCards };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root && !root.DouyinParse) root.DouyinParse = api;
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: 运行确认通过**

Run: `cd extension; node --test tests/`
Expected: PASS（6 tests passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/parse.js extension/tests/parse.test.mjs
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 主页卡片解析 parseProfileCards 与数字解析 parseCount"
```

### Task 7: parseVideoDetail（详情页解析）

**Files:**
- Modify: `extension/content/parse.js`
- Modify: `extension/tests/parse.test.mjs`

- [ ] **Step 1: 写失败测试**

在 `extension/tests/parse.test.mjs` 顶部导入处追加 `parseVideoDetail`，并在文件末尾追加：

```js
const DETAIL_HTML = `
<div>
  <div data-e2e="feed-video" data-e2e-vid="7671480850864786742">
    <video poster="https://p3-sign.douyinpic.com/poster.jpeg?x-signature=def"></video>
  </div>
  <div data-e2e="video-desc"><span>第262集：标题</span><a href="//www.douyin.com/search/%E5%8E%86%E5%8F%B2?aweme_id=7671480850864786742">#历史</a></div>
  <a href="//www.douyin.com/user/MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI">@作者</a>
  <div data-e2e="video-player-digg"><div></div><div class="n1ekR9OB">4.0万</div></div>
  <div data-e2e="feed-comment-icon"><div></div><div class="cipURsys">481</div></div>
  <div data-e2e="video-player-share"><div></div><div class="mvwEat0w">1150</div></div>
</div>
`

test('parseVideoDetail 提取互动数据与作者 secUid', () => {
  const { document } = domOf(DETAIL_HTML).window
  const detail = parseVideoDetail(document)
  assert.equal(detail.video_id, '7671480850864786742')
  assert.equal(detail.like_count, 40000)
  assert.equal(detail.comment_count, 481)
  assert.equal(detail.share_count, 1150)
  assert.equal(detail.video_desc, '第262集：标题#历史')
  assert.equal(detail.video_url, 'https://www.douyin.com/video/7671480850864786742')
  assert.equal(detail.cover_url, 'https://p3-sign.douyinpic.com/poster.jpeg?x-signature=def')
  assert.equal(detail.author_sec_uid, 'MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI')
  assert.equal(detail.play_count, null)
  assert.equal(detail.publish_time, null)
})

test('parseVideoDetail 无 video_id 返回 null', () => {
  const { document } = domOf('<div></div>').window
  assert.equal(parseVideoDetail(document), null)
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd extension; node --test tests/`
Expected: FAIL（`parseVideoDetail is not a function`）

- [ ] **Step 3: 最小实现**

在 `extension/content/parse.js` 的 `parseProfileCards` 之后、`api` 定义之前追加：

```js
  /**
   * 解析视频详情页互动数据。
   * @param {Element} root document 或详情页容器
   * @returns {object|null} video_id/like_count/comment_count/share_count/video_desc/
   *                        video_url/cover_url/author_sec_uid/play_count(null)/publish_time(null)/
   *                        missing_fields；video_id 缺失返回 null。
   */
  function parseVideoDetail(root) {
    let video_id = '';
    const vidEl = root.querySelector('[data-e2e="feed-video"]');
    if (vidEl && vidEl.getAttribute('data-e2e-vid')) {
      video_id = vidEl.getAttribute('data-e2e-vid').trim();
    }
    if (!video_id) {
      const url = root.URL || (root.defaultView && root.defaultView.location.href) || '';
      const m = String(url).match(/\/video\/(\d+)/);
      if (m) video_id = m[1];
    }
    if (!video_id) return null;
    const missing = [];

    const likeValue = countIn(root.querySelector('[data-e2e="video-player-digg"]'));
    const like_count = likeValue === null ? 0 : likeValue;
    if (likeValue === null) missing.push('like_count');

    const commentValue = countIn(root.querySelector('[data-e2e="feed-comment-icon"]'));
    const comment_count = commentValue === null ? 0 : commentValue;
    if (commentValue === null) missing.push('comment_count');

    const shareValue = countIn(root.querySelector('[data-e2e="video-player-share"]'));
    const share_count = shareValue === null ? 0 : shareValue;
    if (shareValue === null) missing.push('share_count');

    const descEl = root.querySelector('[data-e2e="video-desc"]');
    const video_desc = descEl ? (descEl.textContent || '').trim() : '';
    if (!video_desc) missing.push('video_desc');
    const titleEl = descEl ? descEl.querySelector('span') : null;
    const video_title = titleEl ? (titleEl.textContent || '').trim() : '';

    const authorLink = root.querySelector('a[href*="/user/MS4wLj"]');
    const author_sec_uid = authorLink
      ? extractSecUidFromHref(authorLink.getAttribute('href'))
      : '';

    let cover_url = '';
    const posterEl = root.querySelector('video[poster]');
    if (posterEl) {
      cover_url = posterEl.getAttribute('poster') || '';
    } else {
      const imgEl = root.querySelector('[data-e2e="feed-video"] img');
      if (imgEl) cover_url = imgEl.getAttribute('src') || '';
    }
    if (!cover_url) missing.push('cover_url');

    return {
      video_id: video_id,
      video_title: video_title,
      video_desc: video_desc,
      like_count: like_count,
      comment_count: comment_count,
      share_count: share_count,
      play_count: null,
      publish_time: null,
      video_url: 'https://www.douyin.com/video/' + video_id,
      cover_url: cover_url,
      author_sec_uid: author_sec_uid,
      missing_fields: missing,
    };
  }
```

并更新 `api` 定义：

```js
  const api = { parseCount, extractSecUidFromHref, parseProfileCards, parseVideoDetail };
```

- [ ] **Step 4: 运行确认通过**

Run: `cd extension; node --test tests/`
Expected: PASS（8 tests passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/parse.js extension/tests/parse.test.mjs
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 详情页解析 parseVideoDetail（点赞/评论/分享/描述/作者）"
```

### Task 8: options 配置页（后端地址持久化）

**Files:**
- Create: `extension/options/options.html`
- Create: `extension/options/options.js`

- [ ] **Step 1: 新建 `extension/options/options.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>抖音个人视频数据分析器 - 设置</title>
<style>
  body { font-family: system-ui, -apple-system, 'Microsoft YaHei', sans-serif; padding: 16px; width: 320px; }
  label { display: block; margin-bottom: 6px; font-size: 13px; color: #333; }
  input { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid #ccc; border-radius: 4px; }
  .row { margin-bottom: 12px; }
  button { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; }
  #save { background: #409eff; color: #fff; }
  #reset { background: #eee; color: #333; margin-left: 8px; }
  #status { margin-top: 8px; font-size: 12px; color: #67c23a; min-height: 16px; }
  .hint { font-size: 12px; color: #888; margin-top: 4px; }
</style>
</head>
<body>
  <div class="row">
    <label for="backend">后端地址</label>
    <input id="backend" type="text" placeholder="http://127.0.0.1:8001" />
    <div class="hint">默认本机后端；局域网/远端示例：http://192.168.1.10:8001</div>
  </div>
  <button id="save">保存</button>
  <button id="reset">恢复默认</button>
  <div id="status"></div>
  <script src="options.js"></script>
</body>
</html>
```

- [ ] **Step 2: 新建 `extension/options/options.js`**

```js
const KEY = 'backendBaseUrl'
const DEFAULT = 'http://127.0.0.1:8001'
const input = document.getElementById('backend')
const statusEl = document.getElementById('status')

chrome.storage.local.get(KEY).then((data) => {
  input.value = data[KEY] || DEFAULT
})

function normalize(value) {
  let v = String(value || '').trim().replace(/\/+$/, '')
  if (v && !/^https?:\/\//i.test(v)) v = 'http://' + v
  return v || DEFAULT
}

document.getElementById('save').addEventListener('click', () => {
  const value = normalize(input.value)
  chrome.storage.local.set({ [KEY]: value }).then(() => {
    input.value = value
    statusEl.textContent = '已保存：' + value
    setTimeout(() => { statusEl.textContent = '' }, 2500)
  })
})

document.getElementById('reset').addEventListener('click', () => {
  input.value = DEFAULT
  chrome.storage.local.set({ [KEY]: DEFAULT })
  statusEl.textContent = '已恢复默认'
  setTimeout(() => { statusEl.textContent = '' }, 2500)
})
```

- [ ] **Step 3: 验证（T0 静态 + 浏览器加载）**

在 Chrome `chrome://extensions` 加载 `extension/` 目录（开发者模式），
点击插件图标应打开配置弹窗；输入 `http://192.168.1.10:8001` 保存后
`chrome.storage.local` 应包含该值（控制台 `chrome.storage.local.get(null)` 检查）。
本机无法自动化 Chrome，此步由用户验收（列入 Task 16 清单）。

- [ ] **Step 4: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/options/options.html extension/options/options.js
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件配置页（后端地址存 chrome.storage.local）"
```

### Task 9: collect.js 主页模式（白名单/按钮/滚动/上报/结果）

**Files:**
- Create: `extension/content/collect.js`

collect.js 依赖 chrome API 与真实页面，不做自动化单测（T3 由用户真机验收）。
创建后先做语法检查：`node --check extension/content/collect.js`。

- [ ] **Step 1: 新建 `extension/content/collect.js`**

```js
/* 抖音个人视频数据分析器 —— content script
 * 主页模式：白名单校验 → 悬浮按钮 → 自动滚动采集播放量 → 分批上报
 * 详情页模式：白名单校验（作者是自己）→ 被动提取互动数据 → 防抖上报
 */
(function () {
  'use strict';
  const P = window.DouyinParse;
  const MAX_VIDEOS = 100;
  const BATCH_SIZE = 100;
  const DETAIL_DEBOUNCE_MS = 60 * 1000;
  const KEY_BACKEND = 'backendBaseUrl';
  const KEY_UID = 'myUid';
  const KEY_SEC_UID = 'mySecUid';
  const KEY_NICKNAME = 'myNickname';
  const DEFAULT_BACKEND = 'http://127.0.0.1:8001';

  function normalizeBase(url) {
    let u = String(url || DEFAULT_BACKEND).trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(u)) u = 'http://' + u;
    return u;
  }

  function storageGet(keys) {
    return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
  }

  function storageSet(obj) {
    return new Promise((resolve) => chrome.storage.local.set(obj, resolve));
  }

  async function getConfig() {
    const data = await storageGet([KEY_BACKEND, KEY_UID, KEY_SEC_UID, KEY_NICKNAME]);
    return {
      backendBaseUrl: normalizeBase(data[KEY_BACKEND]),
      myUid: data[KEY_UID] || '',
      mySecUid: data[KEY_SEC_UID] || '',
      myNickname: data[KEY_NICKNAME] || '',
    };
  }

  function readRenderData() {
    const el = document.querySelector('script#RENDER_DATA');
    if (!el) return null;
    try {
      return JSON.parse(decodeURIComponent(el.textContent || ''));
    } catch (e) {
      return null;
    }
  }

  /** 主页模式白名单：URL 是 /user/* 且主页主人 uid === 登录账号 uid。 */
  function isOwnProfile() {
    if (!/^\/user\//.test(location.pathname)) return false;
    const data = readRenderData();
    if (!data || !data.app || !data.app.user || !data.app.odin) return false;
    const user = data.app.user;
    const odin = data.app.odin;
    return (
      user.isLogin === true &&
      user.info &&
      odin.user_id &&
      String(user.info.uid) === String(odin.user_id)
    );
  }

  function showToast(message) {
    let box = document.getElementById('dy-analyzer-toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'dy-analyzer-toast';
      box.style.cssText =
        'position:fixed;right:16px;bottom:72px;z-index:2147483647;background:#1d2128;color:#e5e7eb;' +
        'border:1px solid #2d323a;border-radius:8px;padding:10px 14px;font-size:13px;' +
        'box-shadow:0 2px 8px rgba(0,0,0,.35);max-width:320px;word-break:break-all;';
      document.body.appendChild(box);
    }
    box.textContent = message;
    clearTimeout(box._timer);
    box._timer = setTimeout(() => { if (box.parentNode) box.remove(); }, 6000);
  }

  async function report(videos, sourceUrl) {
    const cfg = await getConfig();
    const resp = await fetch(cfg.backendBaseUrl + '/api/extension/videos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_url: sourceUrl, videos: videos }),
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const err = await resp.json();
        detail = err.detail || detail;
      } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitForGrowth(root, currentCount, timeoutMs) {
    return new Promise((resolve) => {
      const start = Date.now();
      const timer = setInterval(() => {
        if (
          root.querySelectorAll('li').length > currentCount ||
          Date.now() - start > (timeoutMs || 6000)
        ) {
          clearInterval(timer);
          resolve();
        }
      }, 300);
    });
  }

  /* ---------- 主页模式 ---------- */

  function createCollectButton() {
    const btn = document.createElement('div');
    btn.id = 'dy-analyzer-btn';
    btn.textContent = '开始采集';
    btn.style.cssText =
      'position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#409eff;color:#fff;' +
      'border-radius:20px;padding:10px 18px;font-size:14px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.35);user-select:none;font-family:system-ui,sans-serif;';
    btn.addEventListener('click', collectProfile);
    document.body.appendChild(btn);
    return btn;
  }

  async function collectProfile() {
    const btn = document.getElementById('dy-analyzer-btn');
    const root = document.querySelector('[data-e2e="user-post-list"]');
    if (!root) {
      showToast('未找到作品列表（user-post-list），请确认在「作品」tab');
      return;
    }
    const cfg = await getConfig();
    const author = { author_name: cfg.myNickname, author_id: cfg.myUid };
    btn.textContent = '采集中…';
    btn.style.pointerEvents = 'none';

    const seen = new Set();
    const collected = [];
    let roundsWithoutNew = 0;

    try {
      while (seen.size < MAX_VIDEOS && roundsWithoutNew < 3) {
        const cards = P.parseProfileCards(root, author);
        let added = 0;
        for (const card of cards) {
          // 防页面篡改：卡片链接里的 secUid 必须与当前登录账号一致
          if (card.sec_uid && card.sec_uid !== cfg.mySecUid) continue;
          if (!seen.has(card.video_id)) {
            seen.add(card.video_id);
            collected.push(card);
            added += 1;
          }
        }
        roundsWithoutNew = added === 0 ? roundsWithoutNew + 1 : 0;
        if (seen.size >= MAX_VIDEOS) break;
        window.scrollTo(0, document.documentElement.scrollHeight);
        await sleep(1500 + Math.random() * 1500);
        await waitForGrowth(root, seen.size);
      }

      const missingCount = collected.reduce(
        (sum, c) => sum + (c.missing_fields || []).length,
        0,
      );
      const rejected = [];
      for (let i = 0; i < collected.length; i += BATCH_SIZE) {
        const batch = collected.slice(i, i + BATCH_SIZE);
        try {
          const res = await report(batch, 'https://www.douyin.com/user/' + cfg.mySecUid);
          for (const r of res.rejected || []) rejected.push(r);
        } catch (e) {
          rejected.push({ video_id: 'batch' + i, reason: String(e.message || e) });
        }
      }
      const reason = seen.size >= MAX_VIDEOS ? '（已达 100 条上限）' : '';
      showToast(
        '采集完成' + reason + '：成功 ' + collected.length + ' 条，字段缺失 ' +
        missingCount + ' 处，被拒 ' + rejected.length + ' 条',
      );
    } catch (e) {
      showToast('采集出错：' + (e && e.message ? e.message : e));
    } finally {
      btn.textContent = '开始采集';
      btn.style.pointerEvents = 'auto';
    }
  }

  /* ---------- 启动（主页模式） ---------- */

  function init() {
    if (isOwnProfile()) {
      const data = readRenderData();
      const info = data && data.app && data.app.user && data.app.user.info;
      if (info) {
        // 始终以当前自己主页的身份为准，覆盖可能变化的缓存
        chrome.storage.local.set({
          [KEY_UID]: info.uid,
          [KEY_SEC_UID]: info.secUid,
          [KEY_NICKNAME]: info.nickname,
        });
      }
      const addButtonWhenReady = () => {
        if (document.querySelector('[data-e2e="user-post-list"]')) {
          createCollectButton();
          return true;
        }
        return false;
      };
      if (!addButtonWhenReady()) {
        new MutationObserver((_, obs) => {
          if (addButtonWhenReady()) obs.disconnect();
        }).observe(document.body, { childList: true, subtree: true });
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: 语法检查**

Run: `node --check extension/content/collect.js`
Expected: 无输出、退出码 0

- [ ] **Step 3: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/collect.js
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件主页采集模式（白名单/按钮/限速滚动/分批上报/结果展示）"
```

### Task 10: collect.js 详情页模式 + extension/README.md

**Files:**
- Modify: `extension/content/collect.js`
- Create: `extension/README.md`

- [ ] **Step 1: 在 collect.js 的「主页模式」之后追加详情页模式函数**

在 `collectProfile` 之后、`/* ---------- 启动（主页模式） ---------- */` 之前插入：

```js
  /* ---------- 详情页模式 ---------- */

  function authorSecUidOfPage() {
    const link = document.querySelector('a[href*="/user/MS4wLj"]');
    return link ? P.extractSecUidFromHref(link.getAttribute('href')) : '';
  }

  async function maybeCollectDetail() {
    if (!/^\/video\/\d+/.test(location.pathname)) return;
    const cfg = await getConfig();
    if (!cfg.mySecUid) {
      showToast('请先在自己主页点一次「开始采集」，再浏览视频详情页');
      return;
    }
    if (authorSecUidOfPage() !== cfg.mySecUid) return; // 别人的视频，忽略
    if (!document.querySelector('[data-e2e="feed-video"]')) return;
    const detail = P.parseVideoDetail(document);
    if (!detail) return;
    const key = 'detail_last_' + detail.video_id;
    const stored = await storageGet(key);
    if (stored[key] && Date.now() - stored[key] < DETAIL_DEBOUNCE_MS) return;
    await storageSet({ [key]: Date.now() });
    try {
      const payload = Object.assign({}, detail, {
        author_name: cfg.myNickname,
        author_id: cfg.myUid,
      });
      const res = await report([payload], 'https://www.douyin.com/user/' + cfg.mySecUid);
      const missing = (detail.missing_fields || []).length;
      showToast(
        '已同步该视频详情（' + detail.video_id + '）' +
        (missing ? '，字段缺失 ' + missing + ' 处' : ''),
      );
    } catch (e) {
      showToast('同步失败：' + (e && e.message ? e.message : e));
    }
  }
```

并修改 `init()` 末尾（主页模式分支之后追加详情页分支）：

```js
    } else if (/^\/video\/\d+/.test(location.pathname)) {
      let started = false;
      const tryStart = () => {
        if (started) return;
        started = true;
        setTimeout(maybeCollectDetail, 1200);
      };
      if (document.querySelector('[data-e2e="feed-video"]')) {
        tryStart();
      } else {
        new MutationObserver((_, obs) => {
          if (document.querySelector('[data-e2e="feed-video"]')) {
            tryStart();
            obs.disconnect();
          }
        }).observe(document.body, { childList: true, subtree: true });
      }
    }
```

- [ ] **Step 2: 语法检查**

Run: `node --check extension/content/collect.js`
Expected: 无输出、退出码 0

- [ ] **Step 3: 新建 `extension/README.md`**

```markdown
# 抖音个人视频数据分析器 - 浏览器插件

在真实浏览器里采集**自己抖音主页**的视频数据并上报到本地后端：

- 主页（作品 tab）：采集每张视频卡片的 video_id、标题、**播放量**、封面；
- 视频详情页：浏览自己视频时被动补采点赞/评论/分享、描述、封面。

## 安装（开发模式）

1. 打开 Chrome，访问 `chrome://extensions`；
2. 右上角开启「开发者模式」；
3. 点击「加载已解压的扩展程序」，选择本目录（`extension/`）；
4. 点击插件图标配置后端地址（默认 `http://127.0.0.1:8001`）。

## 使用

1. 登录抖音网页版，进入**自己的主页**（作品 tab，卡片左下角显示播放量）；
2. 右下角出现「开始采集」，点击后自动滚动翻页（随机间隔 1.5–3 秒，
   单次上限 100 条），结束后提示成功条数、字段缺失处数、被拒条数；
3. 之后正常浏览自己的视频详情页，插件会自动同步点赞/评论/分享等详情数据。

## 合规与边界

- **只能采集自己的数据**：插件只在自己主页（登录账号 uid 与主页主人 uid 一致）
  显示采集按钮；详情页仅在作者是自己时同步，浏览他人视频一律忽略；
- 插件不发起额外采集请求，只读取已渲染的页面 DOM；
- 请勿用于采集他人主页数据；使用本插件产生的账号/合规风险由使用者自行承担。

## 局域网 / 远端后端

- 在插件配置页把后端地址改为局域网或远端地址，如 `http://192.168.1.10:8001`；
- 首次对非默认地址发请求时，浏览器会弹出 host 权限确认（正常安全机制）；
- 后端需已启动并开放对应端口。

## 已知限制

- 主页卡片只显示播放量；点赞/评论/分享需浏览详情页后回补，未浏览的视频为空/0；
- 当前抖音页面不展示绝对发布时间，`publish_time` 留空（后续网络 hook 补齐）；
- 图文（`/note/`）不采集；收藏数不采集；
- 页面结构改版时，取不到的字段记为缺失并提示，不会中断采集。
```

- [ ] **Step 4: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/collect.js extension/README.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件详情页被动采集模式与插件 README"
```

---

## 阶段 3：看板「个人分析」页

### Task 11: analyzer.py 聚合逻辑

**Files:**
- Create: `tests/test_analyzer.py`
- Create: `analyzer.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_analyzer.py`：

```python
"""个人分析聚合逻辑单测。"""
from datetime import datetime

from analyzer import build_trend, summarize_rows, top_videos


def make_row(**over):
    row = {
        'video_id': '1',
        'video_title': '标题',
        'author_name': '作者',
        'author_id': 'A1',
        'publish_time': datetime(2026, 5, 12, 14, 13, 52),
        'like_count': 100,
        'comment_count': 10,
        'share_count': 5,
        'play_count': 1000,
        'crawl_time': datetime(2026, 8, 10, 17, 7, 59),
    }
    row.update(over)
    return row


def test_summarize_rows_totals():
    rows = [
        make_row(video_id='1', like_count=100, comment_count=10, share_count=5, play_count=1000),
        make_row(video_id='2', like_count=50, comment_count=2, share_count=1, play_count=200),
    ]
    summary = summarize_rows(rows)
    assert summary['total_videos'] == 2
    assert summary['total_likes'] == 150
    assert summary['total_comments'] == 12
    assert summary['total_shares'] == 6
    assert summary['total_plays'] == 1200


def test_summarize_latest_sync_is_max_crawl_time():
    rows = [
        make_row(video_id='1', crawl_time=datetime(2026, 1, 1)),
        make_row(video_id='2', crawl_time=datetime(2026, 8, 10)),
    ]
    assert summarize_rows(rows)['latest_sync'] == datetime(2026, 8, 10)


def test_summarize_empty_rows():
    summary = summarize_rows([])
    assert summary['total_videos'] == 0
    assert summary['total_likes'] == 0
    assert summary['latest_sync'] is None


def test_summarize_handles_null_counts():
    summary = summarize_rows([make_row(like_count=None, comment_count=None)])
    assert summary['total_likes'] == 0
    assert summary['total_comments'] == 0


def test_build_trend_groups_by_month_asc():
    rows = [
        make_row(video_id='1', publish_time=datetime(2026, 5, 1)),
        make_row(video_id='2', publish_time=datetime(2026, 5, 20)),
        make_row(video_id='3', publish_time=datetime(2026, 3, 15)),
        make_row(video_id='4', publish_time=None),
    ]
    trend = build_trend(rows)
    assert trend == [
        {'month': '2026-03', 'count': 1},
        {'month': '2026-05', 'count': 2},
    ]


def test_top_videos_sorted_by_like_desc_limited():
    rows = [make_row(video_id=str(i), like_count=i) for i in range(15)]
    top = top_videos(rows, limit=5)
    assert [r['video_id'] for r in top] == ['14', '13', '12', '11', '10']
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q -p no:cacheprovider`
Expected: FAIL（`ModuleNotFoundError: No module named 'analyzer'`）

- [ ] **Step 3: 最小实现**

新建 `analyzer.py`：

```python
"""个人视频数据分析：概览聚合、发布趋势、Top 视频。"""
from collections import Counter
from datetime import datetime
from typing import Any, Optional

TOP_VIDEOS_LIMIT = 10


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def summarize_rows(rows: list[dict]) -> dict:
    """按作者过滤后的概览：总数、总和、最近同步时间（MAX(crawl_time)）。"""
    def total(field: str) -> int:
        return sum(int(r.get(field) or 0) for r in rows)

    crawl_times = [
        _as_datetime(r.get('crawl_time'))
        for r in rows
        if r.get('crawl_time')
    ]
    return {
        'total_videos': len(rows),
        'total_likes': total('like_count'),
        'total_comments': total('comment_count'),
        'total_shares': total('share_count'),
        'total_plays': total('play_count'),
        'latest_sync': max(crawl_times) if crawl_times else None,
    }


def build_trend(rows: list[dict]) -> list[dict]:
    """按 publish_time 的「年-月」分组计数，升序；publish_time 为空的不计入。"""
    counter: Counter = Counter()
    for r in rows:
        pt = _as_datetime(r.get('publish_time'))
        if pt is None:
            continue
        counter[f'{pt.year:04d}-{pt.month:02d}'] += 1
    return [{'month': m, 'count': c} for m, c in sorted(counter.items())]


def top_videos(rows: list[dict], limit: int = TOP_VIDEOS_LIMIT) -> list[dict]:
    """按 like_count 降序取前 limit 条。"""
    ordered = sorted(
        rows,
        key=lambda r: int(r.get('like_count') or 0),
        reverse=True,
    )
    return ordered[:limit]
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q -p no:cacheprovider`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py tests/test_analyzer.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析聚合逻辑（概览/趋势/Top 视频）"
```

### Task 12: /api/analyze/authors 与 /api/analyze/personal 接口 + 真库验证

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 在 api.py 顶部加导入**

```python
import analyzer
```

- [ ] **Step 2: 追加两个分析接口（放在 extension_receive 之后）**

```python
@app.get('/api/analyze/authors')
def analyze_authors():
    """作者下拉数据源：author_id + author_name + 视频数。"""
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT author_id, author_name, COUNT(*) AS count
                FROM video_info
                WHERE author_id IS NOT NULL AND author_id <> ''
                GROUP BY author_id, author_name
                ORDER BY count DESC
            """)
            rows = cursor.fetchall()
    finally:
        db_close(db)
    return {'authors': rows}


@app.get('/api/analyze/personal')
def analyze_personal(author_id: str = Query(..., description='作者 uid')):
    """按作者聚合个人分析：概览 / 发布趋势 / Top 视频。"""
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
        'top_videos': analyzer.top_videos(rows),
    }
```

- [ ] **Step 3: 真库验证（提权 shell；后端需为最新代码，必要时重启 Task 4 的启动命令）**

先造 2 条 `ext_test_author` 测试数据（走接收接口，含发布/互动字段）：

```powershell
$body = @{
  source_url = 'https://www.douyin.com/user/MS4wLjABAAAA_test'
  videos = @(
    @{ video_id = '20260811999900011'; video_title = '测试视频1'; play_count = 500; like_count = 300; comment_count = 30; share_count = 3; publish_time = '2026-05-12T14:13:52'; author_name = '测试作者'; author_id = 'ext_test_author' },
    @{ video_id = '20260811999900012'; video_title = '测试视频2'; play_count = 800; like_count = 600; comment_count = 60; share_count = 6; publish_time = '2026-06-01T10:00:00'; author_name = '测试作者'; author_id = 'ext_test_author' }
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/videos' -Method Post -ContentType 'application/json' -Body $body | Out-Null
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/analyze/personal?author_id=ext_test_author' -TimeoutSec 5
Write-Output ("total=" + $r.summary.total_videos + " likes=" + $r.summary.total_likes + " trend=" + ($r.trend.Count) + " top=" + ($r.top_videos.Count))
```

Expected: `total=2 likes=900 trend=2 top=2`（latest_sync 非空）

再验证作者列表接口：

```powershell
$a = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/analyze/authors' -TimeoutSec 5
$found = $a.authors | Where-Object { $_.author_id -eq 'ext_test_author' }
Write-Output ("found=" + ($found -ne $null) + " count=" + $found.count)
```

Expected: `found=True count=2`

- [ ] **Step 4: 清理测试行（只删自建 ext_test_ 数据）**

```powershell
mysql -h 127.0.0.1 -P 3307 -u root -p20061006 douyin_spider -e "DELETE FROM video_info WHERE author_id = 'ext_test_author'; SELECT COUNT(*) AS left_cnt FROM video_info WHERE author_id = 'ext_test_author';"
```

Expected: `left_cnt=0`

- [ ] **Step 5: 全量回归 + 提交**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过（原 68 + 新增 7 = 75 passed）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析接口（作者列表/概览/趋势/Top 视频）"
```

### Task 13: PersonalAnalyzer.vue 页面

**Files:**
- Create: `frontend/src/pages/PersonalAnalyzer.vue`

- [ ] **Step 1: 新建页面（复用现有 token/StatCard/echarts 模式）**

```vue
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import api from '../api'
import StatCard from '../components/StatCard.vue'

use([BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

interface AuthorOption {
  author_id: string
  author_name: string
  count: number
}

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
  }
  trend: { month: string; count: number }[]
  top_videos: Array<{
    video_id: string
    video_title?: string | null
    like_count?: number
    comment_count?: number
    share_count?: number
    publish_time?: string | null
    crawl_time?: string | null
  }>
}

const authors = ref<AuthorOption[]>([])
const authorId = ref('')
const loading = ref(false)
const data = ref<PersonalData | null>(null)
const error = ref('')

const interactionData = computed(() => {
  const s = data.value?.summary
  if (!s) return []
  return [
    { name: '点赞', value: s.total_likes },
    { name: '评论', value: s.total_comments },
    { name: '分享', value: s.total_shares },
  ]
})

const trendOption = computed(() => ({
  title: {
    text: '月度发布趋势',
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 16, top: 44, bottom: 28 },
  xAxis: {
    type: 'category',
    data: (data.value?.trend ?? []).map((t) => t.month),
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      name: '视频数',
      type: 'bar',
      barMaxWidth: 28,
      itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
      data: (data.value?.trend ?? []).map((t) => t.count),
    },
  ],
}))

const interactionOption = computed(() => ({
  title: {
    text: '互动总量',
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'axis' },
  grid: { left: 64, right: 16, top: 44, bottom: 28 },
  xAxis: {
    type: 'category',
    data: interactionData.value.map((d) => d.name),
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      name: '总数',
      type: 'bar',
      barMaxWidth: 48,
      itemStyle: { color: '#67c23a', borderRadius: [4, 4, 0, 0] },
      data: interactionData.value.map((d) => d.value),
    },
  ],
}))

async function loadAuthors() {
  try {
    const res = await api.get<{ authors: AuthorOption[] }>('/analyze/authors')
    authors.value = res.data.authors ?? []
    if (authors.value.length) {
      authorId.value = authors.value[0].author_id
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载作者列表失败')
  }
}

async function loadPersonal() {
  if (!authorId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.get<PersonalData>('/analyze/personal', {
      params: { author_id: authorId.value },
    })
    data.value = res.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载分析数据失败'
  } finally {
    loading.value = false
  }
}

watch(authorId, loadPersonal)
onMounted(loadAuthors)

function fmtNum(n?: number) {
  if (!n) return '0'
  if (n >= 100000000) return (n / 100000000).toFixed(1) + '亿'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return String(n)
}

function fmtTime(t?: string | null) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '--'
}
</script>

<template>
  <div class="personal">
    <el-alert v-if="error" type="error" :title="error" :closable="false" style="margin-bottom: 12px" />
    <el-card shadow="never" class="p-card toolbar">
      <span class="label">作者：</span>
      <el-select v-model="authorId" filterable style="width: 280px" :disabled="loading">
        <el-option
          v-for="a in authors"
          :key="a.author_id"
          :label="`${a.author_name || a.author_id}（${a.count} 条）`"
          :value="a.author_id"
        />
      </el-select>
      <el-button :loading="loading" @click="loadPersonal">刷新</el-button>
    </el-card>

    <el-empty
      v-if="!loading && !data && !error"
      description="还没有数据，请先用浏览器插件在自己主页采集"
      style="margin-top: 40px"
    />

    <template v-if="data">
      <el-row :gutter="16">
        <el-col :span="5">
          <StatCard title="视频数" :value="data.summary.total_videos" status="info" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总点赞" :value="fmtNum(data.summary.total_likes)" status="success" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总评论" :value="fmtNum(data.summary.total_comments)" status="warning" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总分享" :value="fmtNum(data.summary.total_shares)" status="info" />
        </el-col>
        <el-col :span="4">
          <StatCard title="最近同步" :value="fmtTime(data.summary.latest_sync)" status="info" />
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="trendOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="interactionOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="p-card">
        <template #header>Top 10 视频（按点赞）</template>
        <el-table :data="data.top_videos" size="small" max-height="460">
          <el-table-column prop="video_id" label="视频ID" width="190" />
          <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
          <el-table-column label="点赞" width="100">
            <template #default="{ row }">{{ fmtNum(row.like_count) }}</template>
          </el-table-column>
          <el-table-column label="评论" width="90">
            <template #default="{ row }">{{ fmtNum(row.comment_count) }}</template>
          </el-table-column>
          <el-table-column label="分享" width="90">
            <template #default="{ row }">{{ fmtNum(row.share_count) }}</template>
          </el-table-column>
          <el-table-column label="发布时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.publish_time) }}</template>
          </el-table-column>
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.crawl_time) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.p-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
.toolbar :deep(.el-card__body) {
  display: flex;
  gap: 12px;
  align-items: center;
}
.label {
  color: var(--spider-text-secondary);
  font-size: 14px;
}
</style>
```

- [ ] **Step 2: 语法与类型检查（此时路由未注册，仅验证文件本身可编译）**

Run: `cd frontend; npx vue-tsc --noEmit --skipLibCheck frontend/src/pages/PersonalAnalyzer.vue`（若 vue-tsc 不支持单文件参数，则以 Task 14 的完整 build 为准）

- [ ] **Step 3: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/pages/PersonalAnalyzer.vue
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析页（作者下拉/概览卡/趋势图/互动图/Top 视频表）"
```

### Task 14: 路由与菜单 + 前端构建验证

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/MainLayout.vue`

- [ ] **Step 1: 注册路由**

在 `frontend/src/router/index.ts` 的 `{ path: 'quality', ... }` 行后追加：

```ts
        { path: 'personal', name: 'personal', component: () => import('../pages/PersonalAnalyzer.vue'), meta: { title: '个人分析' } },
```

- [ ] **Step 2: 加侧边栏菜单**

在 `frontend/src/layouts/MainLayout.vue` 的 `menus` 数组中追加：

```ts
  { index: '/personal', label: '个人分析' },
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend; npm run build`
Expected: `vue-tsc` 无类型错误，vite 构建成功（dist 产物更新）

- [ ] **Step 4: 浏览器接口验证（提权 shell，后端最新代码运行中）**

```powershell
$a = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/analyze/authors' -TimeoutSec 5
Write-Output ("authors=" + $a.authors.Count)
$p = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/app/' -TimeoutSec 5
Write-Output ("app status=" + $p.StatusCode)
```

Expected: `authors>=1`（库内有真实作者）、`app status=200`（构建产物由后端提供）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/router/index.ts frontend/src/layouts/MainLayout.vue
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析页路由与侧边栏入口，前端构建通过"
```

> 注意：`frontend/dist` 已被 `.gitignore` 忽略且从未入库，构建产物仅本地生成、
> 由后端 `/app` 运行时读取，**不提交**。

---

## 阶段 4：收尾

### Task 15: 项目 README 更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 README「功能特性」后追加插件说明段落**

在 README 的「## 功能特性」列表之后追加：

```markdown
- **个人视频数据分析器（浏览器插件版）**：
  - 博主在真实浏览器里用插件采集**自己主页**视频的播放量，浏览自己的视频详情页时
    自动补采点赞/评论/分享；
  - 后端只做「数据接收器」：字段校验 → 按 video_id 去重 → upsert 到 `video_info` 表，
    爬虫/队列/Playwright 不参与此链路；
  - 看板新增「个人分析」页：作者下拉、概览卡（含最近同步时间）、发布趋势、
    互动总量、Top 10 视频。
```

- [ ] **Step 2: 在 README「快速开始」后追加插件安装与合规段落**

```markdown
### 浏览器插件（个人数据采集）

1. 打开 Chrome → `chrome://extensions` → 开启「开发者模式」→「加载已解压的扩展程序」，
   选择 `extension/` 目录；
2. 点击插件图标配置后端地址（默认 `http://127.0.0.1:8001`）；
3. 登录抖音网页版，进入**自己的主页**，点击右下角「开始采集」；
4. 之后正常浏览自己的视频详情页，插件会自动同步点赞/评论/分享。

**合规声明（重要）**：本插件**只能采集当前登录账号自己的主页数据**——
白名单校验确保不在他人主页启用、不在他人视频详情页采集；
请勿用于采集他人主页数据，使用者须自行遵守抖音用户协议与相关法律法规。

**已知限制**：主页卡片只显示播放量；点赞/评论/分享需浏览详情页后回补；
当前页面不展示绝对发布时间（`publish_time` 留空，后续网络 hook 补齐）；
图文（`/note/`）与收藏数不采集。
```

- [ ] **Step 3: 检查 README 无旧「作者主页一键采集不可用」表述冲突**

Run: `Select-String -LiteralPath README.md -Pattern '个人视频数据分析器|浏览器插件|只能采集'`
Expected: 命中新增段落；「已知限制」中旧的作者主页采集限制表述若与新功能冲突，改为
「自动采集受平台风控限制，浏览器插件版仅支持采集自己的主页数据」。

- [ ] **Step 4: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add README.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: README 补充插件安装/合规声明/已知限制"
```

### Task 16: 全量回归与用户验收清单

**Files:** 无新增（视回归结果修复）

- [ ] **Step 1: 后端全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过（75 passed）

- [ ] **Step 2: 插件测试回归**

Run: `cd extension; node --test tests/`
Expected: 8 passed

- [ ] **Step 3: 前端构建回归**

Run: `cd frontend; npm run build`
Expected: 构建成功

- [ ] **Step 4: 交付用户真机验收清单（写入最终汇报）**

用户按以下清单在自己浏览器验收：

1. `chrome://extensions` 加载 `extension/`，插件图标可打开配置页；
2. 登录抖音网页版，进入**自己的主页**（作品 tab）：
   - 右下角出现「开始采集」按钮（他人主页/未登录时不出现）；
   - 点击后自动滚动，结束后提示成功条数/字段缺失/被拒条数；
   - 后端 `video_info` 表出现本主页视频记录（video_id/标题/play_count/封面）。
3. 打开**自己**的视频详情页：右下角出现「已同步该视频详情」，点赞/评论/分享回补；
   （打开别人视频：无任何提示、不产生数据）
4. 看板「个人分析」页：选择自己作者 → 概览卡（视频数/总赞/总评论/总分享/最近同步）、
   发布趋势图、互动总量图、Top 10 视频表；
5. 重复点一次「开始采集」：数据 upsert 不重复，看板「最近同步时间」刷新。

- [ ] **Step 5: Git 边界检查与汇总**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 status --short
git -c safe.directory=D:/DjangoProject/PythonProject11 log --oneline -20
```

Expected: 无未提交的新改动（未跟踪的 `Codex Image ...png` 除外）；提交历史按阶段清晰。
向用户汇报：实现内容、测试证据、真机验收清单、已知限制、下一步（网络 hook / 独立仓库评估）。
