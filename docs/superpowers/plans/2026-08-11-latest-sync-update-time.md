# 个人分析「最近同步」语义修正 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `latest_sync` 从 `MAX(crawl_time)` 改为 `MAX(COALESCE(update_time, crawl_time))`，让爬虫刷新也被反映，接口字段与前端展示不变。

**Architecture:** 纯逻辑 owner 为 `analyzer.py` 的 `summarize_rows`；`/api/analyze/personal` 已 `SELECT *` 无需改动；前端字段名不变。

**Tech Stack:** Python 3 + pytest。

**Spec:** `docs/superpowers/specs/2026-08-11-latest-sync-update-time-design.md`

---

### Task 1: latest_sync 取 MAX(update_time)（TDD）

**Files:**
- Modify: `tests/test_analyzer.py`
- Modify: `analyzer.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyzer.py` 的 `make_row` 增加 `update_time` 默认值：
```python
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
        'update_time': datetime(2026, 8, 10, 17, 7, 59),
    }
    row.update(over)
    return row
```

把 `test_summarize_latest_sync_is_max_crawl_time` 替换为：
```python
def test_summarize_latest_sync_uses_max_update_time():
    rows = [
        make_row(video_id='1', crawl_time=datetime(2026, 1, 1), update_time=datetime(2026, 8, 10)),
        make_row(video_id='2', crawl_time=datetime(2026, 8, 9), update_time=datetime(2026, 6, 1)),
    ]
    assert summarize_rows(rows)['latest_sync'] == datetime(2026, 8, 10)


def test_summarize_latest_sync_falls_back_to_crawl_time_when_update_missing():
    rows = [
        make_row(video_id='1', crawl_time=datetime(2026, 3, 1), update_time=None),
        make_row(video_id='2', crawl_time=datetime(2026, 5, 1), update_time=None),
    ]
    assert summarize_rows(rows)['latest_sync'] == datetime(2026, 5, 1)
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q`
Expected: `test_summarize_latest_sync_uses_max_update_time` FAIL（旧实现返回 `2026-08-09` 而非 `2026-08-10`）。

- [ ] **Step 3: 最小实现**

`analyzer.py` 的 `summarize_rows` 中：
```python
    crawl_times = [
        _as_datetime(r.get('crawl_time'))
        for r in rows
        if r.get('crawl_time')
    ]
```
替换为：
```python
    sync_times = [
        _as_datetime(r.get('update_time') or r.get('crawl_time'))
        for r in rows
        if r.get('update_time') or r.get('crawl_time')
    ]
```
并把返回中的 `'latest_sync': max(crawl_times) if crawl_times else None` 改为
`'latest_sync': max(sync_times) if sync_times else None`，docstring 同步改为「最近同步时间（MAX(COALESCE(update_time, crawl_time))）」。

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q`
Expected: 全部 PASS。

---

### Task 2: 全量回归 + 文档

- [ ] **Step 1: 后端全量**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 95 passed。

- [ ] **Step 2: 扩展与前端基线**

Run（`extension/`）: `node --test` → 20 passed；
Run（`frontend/`）: `npm run build` → 构建成功。

- [ ] **Step 3: 提交（需用户确认后执行）**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py tests/test_analyzer.py docs/superpowers/specs/2026-08-11-latest-sync-update-time-design.md docs/superpowers/plans/2026-08-11-latest-sync-update-time.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 个人分析最近同步改为 MAX(update_time)，反映爬虫刷新"
```

- [ ] **Step 4: 真库验证（可选，接口层）**

调用 `GET /api/analyze/personal?author_id=<任一作者>`，确认 `latest_sync` 与库里该作者 `MAX(update_time)` 一致（只读查询）。
