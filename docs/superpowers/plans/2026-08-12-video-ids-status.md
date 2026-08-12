# video_ids.txt 同步状态管理（P2-A）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `video_ids.txt` 每个 id 加 `pending/done` 状态；插件上报新 id 记 pending、已存在重置 pending；`POST /api/crawl` 只推 pending/新 id，推送后标记 done，避免重复爬取。

**Architecture:** 纯逻辑 owner 为 `extension_receiver.py`（行解析、带状态读写、标记、筛选），`api.py` 薄层接线；`/api/extension/ids` 与 `/api/extension/ids` GET/PUT 签名不变，前端零改动。

**Tech Stack:** Python 3 + pytest。

**Spec:** `docs/superpowers/specs/2026-08-12-video-ids-status-design.md`

---

### Task 1: 纯函数（extension_receiver.py，TDD）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 更新测试（含失败新用例）**

`tests/test_extension_receiver.py` 顶部 import 更新：
```python
from extension_receiver import (
    MAX_BATCH,
    append_ids_file,
    build_upsert,
    dedupe_records,
    evaluate_write_guard,
    filter_pending_ids,
    is_allowed_origin,
    is_valid_token,
    mark_ids_done,
    normalize_record,
    parse_count,
    parse_datetime,
    parse_id_line,
    read_ids_file,
    read_ids_with_status,
    validate_batch,
    validate_source_url,
    validate_video_id,
    write_ids_file,
)
```

删除 `test_merge_ids_*` 三个测试（merge_ids 将被移除）。更新 ids 相关测试并新增：
```python
def test_parse_id_line():
    assert parse_id_line('123') == ('123', 'pending')
    assert parse_id_line('123|done') == ('123', 'done')
    assert parse_id_line('123|bad') == ('123', 'pending')
    assert parse_id_line('') is None
    assert parse_id_line('|x') is None


def test_read_ids_with_status_parses_mixed_lines(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb|done\n\nc|pending\n', encoding='utf-8')
    assert read_ids_with_status(str(path)) == [
        {'video_id': 'a', 'status': 'pending'},
        {'video_id': 'b', 'status': 'done'},
        {'video_id': 'c', 'status': 'pending'},
    ]


def test_append_ids_file_merges_and_returns_counts(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['b', 'c'])
    assert (added, total) == (1, 3)
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending', 'b|pending', 'c|pending']


def test_append_ids_file_creates_missing_file(tmp_path):
    path = tmp_path / 'video_ids.txt'
    added, total = append_ids_file(str(path), ['x', 'y'])
    assert (added, total) == (2, 2)
    assert path.read_text(encoding='utf-8').splitlines() == ['x|pending', 'y|pending']


def test_append_ids_file_no_tmp_leftover(tmp_path):
    path = tmp_path / 'video_ids.txt'
    append_ids_file(str(path), ['a'])
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')]
    assert leftovers == []


def test_append_ids_file_resets_existing_to_pending(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|done\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['a'])
    assert (added, total) == (0, 1)
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending']


def test_read_ids_file_reads_lines_and_skips_blanks(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\n\nb\n', encoding='utf-8')
    assert read_ids_file(str(path)) == ['a', 'b']


def test_read_ids_file_missing_returns_empty(tmp_path):
    assert read_ids_file(str(tmp_path / 'missing.txt')) == []


def test_mark_ids_done_existing_and_new(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending\nb|done\n', encoding='utf-8')
    changed = mark_ids_done(str(path), ['a', 'b', 'c'])
    assert changed == 2
    assert path.read_text(encoding='utf-8').splitlines() == ['a|done', 'b|done', 'c|done']


def test_write_ids_file_preserves_status(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|done\nb|pending\n', encoding='utf-8')
    assert write_ids_file(str(path), ['b', 'c']) == 2
    assert path.read_text(encoding='utf-8').splitlines() == ['b|pending', 'c|pending']


def test_write_ids_file_empty_clears(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending\nb|done\n', encoding='utf-8')
    assert write_ids_file(str(path), []) == 0
    assert path.read_text(encoding='utf-8') == ''


def test_filter_pending_ids():
    records = [
        {'video_id': 'a', 'status': 'pending'},
        {'video_id': 'b', 'status': 'done'},
    ]
    assert filter_pending_ids(records, ['b', 'c', 'a', 'c']) == ['c', 'a']
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: FAIL（`ImportError: cannot import name 'filter_pending_ids' ...` 等新函数缺失；旧 append/write 断言不匹配）。

- [ ] **Step 3: 实现 extension_receiver.py**

3.1 删除 `merge_ids` 函数。

3.2 在 `read_ids_file` 附近替换实现：
```python
def parse_id_line(line: str):
    """解析一行：纯 id → pending；'id|status' 保留状态；非法返回 None。"""
    text = (line or '').strip()
    if not text:
        return None
    if '|' in text:
        video_id, _, status = text.partition('|')
        video_id = video_id.strip()
        if not video_id:
            return None
        if status.strip() not in ('pending', 'done'):
            status = 'pending'
        return video_id, status
    return text, 'pending'


def read_ids_with_status(path: str) -> list[dict]:
    """读取并解析每行状态，返回 [{video_id, status}]，保序。"""
    records = []
    for line in _read_ids(path):
        parsed = parse_id_line(line)
        if parsed:
            records.append({'video_id': parsed[0], 'status': parsed[1]})
    return records


def read_ids_file(path: str) -> list[str]:
    """读取 video_ids.txt 全部 ID（纯 id 列表，兼容旧调用）。"""
    return [r['video_id'] for r in read_ids_with_status(path)]
```

3.3 新增写记录内部函数（放在 `_write_ids_atomic` 之后）：
```python
def _write_ids_records(path: str, records: list[dict]) -> None:
    """按 'id|status' 原子写入。"""
    _write_ids_atomic(path, [f"{r['video_id']}|{r['status']}" for r in records])
```

3.4 替换 `append_ids_file` / `write_ids_file` 实现并新增 `mark_ids_done`、`filter_pending_ids`：
```python
def append_ids_file(path: str, new_ids: list[str]) -> tuple[int, int]:
    """合并插件采集 id：新 id 追加 pending，已存在重置 pending。返回 (新增数, 总行数)。"""
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            records = read_ids_with_status(path)
            existing = {r['video_id'] for r in records}
            added = 0
            for vid in new_ids:
                vid = (vid or '').strip()
                if not vid:
                    continue
                if vid not in existing:
                    records.append({'video_id': vid, 'status': 'pending'})
                    existing.add(vid)
                    added += 1
                else:
                    for r in records:
                        if r['video_id'] == vid:
                            r['status'] = 'pending'
                            break
            _write_ids_records(path, records)
            return added, len(records)
        finally:
            _unlock_ids_file(fh)


def mark_ids_done(path: str, ids: list[str]) -> int:
    """把 id 标记为 done（不在文件的追加为 done）。返回实际变化行数。"""
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            records = read_ids_with_status(path)
            by_id = {r['video_id']: r for r in records}
            changed = 0
            for vid in ids:
                vid = (vid or '').strip()
                if not vid:
                    continue
                record = by_id.get(vid)
                if record is None:
                    records.append({'video_id': vid, 'status': 'done'})
                    by_id[vid] = records[-1]
                    changed += 1
                elif record['status'] != 'done':
                    record['status'] = 'done'
                    changed += 1
            if changed:
                _write_ids_records(path, records)
            return changed
        finally:
            _unlock_ids_file(fh)


def write_ids_file(path: str, ids: list[str]) -> int:
    """前端纯 id 全量覆盖：保留已有状态，新 id 记 pending，删除的移除。返回写入条数。"""
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            old = {r['video_id']: r['status'] for r in read_ids_with_status(path)}
            records = []
            seen = set()
            for vid in ids:
                vid = (vid or '').strip()
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                records.append({'video_id': vid, 'status': old.get(vid, 'pending')})
            _write_ids_records(path, records)
            return len(records)
        finally:
            _unlock_ids_file(fh)


def filter_pending_ids(records: list[dict], requested_ids: list[str]) -> list[str]:
    """筛出可推队列的 id：状态 pending 或不在文件中的（视为新 id）。保序去重。"""
    known = {r['video_id']: r['status'] for r in records}
    pushable = []
    seen = set()
    for vid in requested_ids:
        vid = (vid or '').strip()
        if not vid or vid in seen:
            continue
        seen.add(vid)
        status = known.get(vid)
        if status is None or status == 'pending':
            pushable.append(vid)
    return pushable
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: 全部 PASS。

---

### Task 2: api.py `/api/crawl` 接线

**Files:**
- Modify: `api.py`

- [ ] **Step 1: CrawlResponse 加 skipped**

```python
class CrawlResponse(BaseModel):
    pushed: int
    queue_length: int
    video_ids: list[str]
    skipped: int = 0
```

- [ ] **Step 2: push_crawl 改造**

```python
@app.post('/api/crawl', response_model=CrawlResponse, dependencies=[Depends(verify_write_guard)])
def push_crawl(req: CrawlRequest):
    """只推 pending/新 id，推送成功后标记 done；Redis 不可用返回 503 且不标记。"""
    cleaned = [vid.strip() for vid in req.video_ids if vid and vid.strip()]
    records = extension_receiver.read_ids_with_status(VIDEO_IDS_PATH)
    pushable = extension_receiver.filter_pending_ids(records, cleaned)
    try:
        r = get_redis()
        count = 0
        for vid in pushable:
            task = json.dumps({
                'url': f'https://www.douyin.com/video/{vid}',
                'type': req.task_type,
            })
            r.lpush(REDIS_START_URLS_KEY, task)
            count += 1
        queue_length = r.llen(REDIS_START_URLS_KEY)
        extension_receiver.mark_ids_done(VIDEO_IDS_PATH, pushable)
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return CrawlResponse(
        pushed=count,
        queue_length=queue_length,
        video_ids=pushable,
        skipped=len(cleaned) - count,
    )
```

- [ ] **Step 3: 运行回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS。

---

### Task 3: README + 全量回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README 补充**

在「收集任务/队列」相关说明附近追加：
```markdown
### video_ids.txt 同步状态
- 每行格式 `video_id|pending` 或 `video_id|done`（纯 id 行视为 pending，向后兼容）；
- 插件采集上报的新 id 记 pending，已存在的 id 重置 pending；前端编辑保存保留已有状态；
- 「导入爬虫队列」只推 pending 与文件外的新 id，推送成功后标记 done，避免重复爬取；
- 强制重爬某条：编辑文件删除该行后重新导入（视为新 id）。
```

- [ ] **Step 2: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 全部 PASS；
Run（`extension/`）: `node --test` → 20 passed；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 4: 提交（需用户确认）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py api.py tests/test_extension_receiver.py README.md docs/superpowers/specs/2026-08-12-video-ids-status-design.md docs/superpowers/plans/2026-08-12-video-ids-status.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: video_ids.txt 增加 pending/done 状态，爬虫只推待采集 id"
```
