# 采集完善实施计划（主页全量翻页 + 网络 hook + video_id 保留）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复主页采集不全（58 个视频只采到 39 条），通过多策略滚动 + 被动网络 hook 让 100 条以内视频一次采全（含播放量/互动/发布时间），并把采集到的 video_id 去重写入 `video_ids.txt` 供爬虫后续刷新。

**Architecture:** 三层：`hook.js`（页面世界，观察抖音接口 JSON 响应，CustomEvent + DOM 属性缓冲）→ `collect.js`（isolated world，接收合并、多策略滚动、采集完成上报 ids）→ 后端 `POST /api/extension/ids`（merge_ids 去重 + 文件锁 + 原子替换写 `video_ids.txt`）。纯解析/合并逻辑放 `parse.js` 与 `extension_receiver.py`，全部可单测。

**Tech Stack:** Chrome MV3（world: MAIN hook + isolated content script）/ 原生 JS；Python FastAPI / PyMySQL；Node 24 `node --test` + jsdom；pytest。

---

## 前置约定（本仓库环境）

- 当前分支：`codex/personal-analyzer-extension`；设计已定稿并提交：
  `docs/superpowers/specs/2026-08-11-personal-analyzer-extension-collection-complete.md`
- 后端单测：`.\.venv\Scripts\python.exe -m pytest tests/<file> -q -p no:cacheprovider`
- 插件测试：`cd extension; npm test`（jsdom 已装；`node --test` 默认发现 `tests/*.test.mjs`）
- 前端构建：`cd frontend; npm run build`
- git 加 `-c safe.directory=D:/DjangoProject/PythonProject11`，写操作免提权（当前权限策略为 never）
- 真文件验证 `video_ids.txt`：先用临时前缀 `ext_test_` 的 ID 测试，验证后**恢复原文件内容**
- 严禁提交：`Codex Image ...png`、`local_config.py`、日志、`video_ids.txt`（已 gitignore）

## 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `extension_receiver.py` | 新增 `merge_ids` / `append_ids_file`（锁 + 原子替换） | 修改 |
| `tests/test_extension_receiver.py` | merge_ids / 文件写入测试 | 修改 |
| `api.py` | 新增 `POST /api/extension/ids` + `VIDEO_IDS_PATH` | 修改 |
| `extension/content/hook.js` | 页面世界网络 hook（XHR/fetch 观察 + CustomEvent + DOM 缓冲） | 新建 |
| `extension/content/parse.js` | 新增 `parseAwemeList` / `findScrollContainer` / `mergeCardWithHook` / `drainHookQueue` / `formatLocalTime` | 修改 |
| `extension/content/collect.js` | 滚动容器策略 + hook 接收合并 + 采集完成上报 ids | 修改 |
| `extension/manifest.json` | 增加 hook.js（world: MAIN, document_start） | 修改 |
| `extension/tests/parse.test.mjs` | hook 解析/滚动容器/合并/缓冲测试 | 修改 |
| `extension/README.md` | 全量翻页与 id 保留说明 | 修改 |
| `README.md` | 项目 README 更新 | 修改 |

---

## 阶段 1：后端 video_id 保留

### Task 1: merge_ids 与 append_ids_file（锁 + 原子替换）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_extension_receiver.py` 顶部导入追加：

```python
from extension_receiver import append_ids_file, merge_ids
```

文件末尾追加：

```python
def test_merge_ids_keeps_existing_order_and_appends_new():
    merged = merge_ids(['a', 'b'], ['c', 'a', 'd'])
    assert merged == ['a', 'b', 'c', 'd']


def test_merge_ids_removes_duplicates_in_existing():
    merged = merge_ids(['a', 'a', 'b'], ['b', 'c'])
    assert merged == ['a', 'b', 'c']


def test_merge_ids_empty_inputs():
    assert merge_ids([], []) == []
    assert merge_ids(['a'], []) == ['a']
    assert merge_ids([], ['a', 'b']) == ['a', 'b']


def test_append_ids_file_merges_and_returns_counts(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['b', 'c'])
    assert (added, total) == (1, 3)
    assert path.read_text(encoding='utf-8').splitlines() == ['a', 'b', 'c']


def test_append_ids_file_creates_missing_file(tmp_path):
    path = tmp_path / 'video_ids.txt'
    added, total = append_ids_file(str(path), ['x', 'y'])
    assert (added, total) == (2, 2)
    assert path.read_text(encoding='utf-8').splitlines() == ['x', 'y']


def test_append_ids_file_no_tmp_leftover(tmp_path):
    path = tmp_path / 'video_ids.txt'
    append_ids_file(str(path), ['a'])
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')]
    assert leftovers == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: FAIL（`ImportError: cannot import name 'append_ids_file'`）

- [ ] **Step 3: 最小实现**

在 `extension_receiver.py` 顶部 import 区追加：

```python
import os
import tempfile
import threading
```

文件末尾追加：

```python
_IDS_FILE_LOCK = threading.Lock()


def merge_ids(existing: list[str], new_ids: list[str]) -> list[str]:
    """去重合并：保留已有顺序，新 ID 追加在末尾；返回新列表。"""
    seen: set[str] = set(existing)
    merged = list(existing)
    for vid in new_ids:
        if vid not in seen:
            seen.add(vid)
            merged.append(vid)
    return merged


def _read_ids(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def _write_ids_atomic(path: str, ids: list[str]) -> None:
    """写临时文件 + os.replace 原子替换，避免写一半损坏。"""
    directory = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.video_ids.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ids))
            if ids:
                f.write('\n')
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _lock_ids_file(path: str):
    """跨平台文件锁：fcntl（POSIX）/ msvcrt（Windows）；返回锁句柄。"""
    import hashlib
    lock_name = 'dy_analyzer_ids_' + hashlib.md5(path.encode('utf-8')).hexdigest() + '.lock'
    lock_path = os.path.join(tempfile.gettempdir(), lock_name)
    fh = open(lock_path, 'a+')
    try:
        import fcntl  # type: ignore
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    except ImportError:
        import msvcrt  # type: ignore
        fh.seek(0)
        if fh.read(1) == '':
            fh.write('\0')
            fh.flush()
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    return fh


def _unlock_ids_file(fh) -> None:
    try:
        import fcntl  # type: ignore
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except ImportError:
        import msvcrt  # type: ignore
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    fh.close()


def append_ids_file(path: str, new_ids: list[str]) -> tuple[int, int]:
    """并发安全地把新 ID 合并进文件：进程内锁 + 文件锁 + 原子替换。
    返回 (新增条数, 合并后总条数)。
    """
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            existing = _read_ids(path)
            merged = merge_ids(existing, new_ids)
            _write_ids_atomic(path, merged)
            return len(merged) - len(existing), len(merged)
        finally:
            _unlock_ids_file(fh)
```

- [ ] **Step 4: 运行确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q -p no:cacheprovider`
Expected: PASS（新增 6 个测试全过）

- [ ] **Step 5: 全量回归 + 提交**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: video_ids 去重合并与并发安全文件写入（锁+原子替换）"
```

### Task 2: POST /api/extension/ids + 真文件验证

**Files:**
- Modify: `api.py`

- [ ] **Step 1: api.py 顶部加常量**

```python
VIDEO_IDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'video_ids.txt')
```

- [ ] **Step 2: 追加接口（放在 extension_receive 之后）**

```python
class ExtensionIdsRequest(BaseModel):
    video_ids: list[str]
    author_id: str = ''


@app.post('/api/extension/ids')
def extension_save_ids(req: ExtensionIdsRequest):
    """把插件采集到的 video_id 去重追加到 video_ids.txt，供爬虫后续刷新数据。"""
    if not (1 <= len(req.video_ids) <= extension_receiver.MAX_BATCH):
        raise HTTPException(
            status_code=400,
            detail=f'video_ids 必须是 1-{extension_receiver.MAX_BATCH} 条',
        )
    cleaned: list[str] = []
    rejected: list[str] = []
    for vid in req.video_ids:
        vid = (vid or '').strip()
        if extension_receiver.validate_video_id(vid):
            cleaned.append(vid)
        else:
            rejected.append(vid)
    if not cleaned:
        raise HTTPException(status_code=400, detail='没有合法的 video_id')
    added, total = extension_receiver.append_ids_file(VIDEO_IDS_PATH, cleaned)
    return {'added': added, 'total': total, 'rejected': rejected}
```

- [ ] **Step 3: 真文件验证（后端需最新代码，必要时重启 Task 4 的启动命令）**

先备份现有 `video_ids.txt`，再验证：

```powershell
$bak = "$env:TEMP\video_ids_backup.txt"
Copy-Item 'D:\DjangoProject\PythonProject11\video_ids.txt' $bak -Force -ErrorAction SilentlyContinue
$body = @{ video_ids = @('20260811999910001','20260811999910002','20260811999910001'); author_id = 'ext_test_author' } | ConvertTo-Json
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/ids' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 8
Write-Output ("added=" + $r.added + " total=" + $r.total + " rejected=" + $r.rejected.Count)
Select-String -LiteralPath 'D:\DjangoProject\PythonProject11\video_ids.txt' -Pattern '2026081199991000' | Measure-Object | ForEach-Object { Write-Output ("file_hits=" + $_.Count) }
```

Expected: `added=2 total=<原行数+2> rejected=0`、`file_hits=2`（去重生效）

再验证非法 ID 被拒：

```powershell
$bad = @{ video_ids = @('not-an-id') } | ConvertTo-Json
try { Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/extension/ids' -Method Post -ContentType 'application/json' -Body $bad -TimeoutSec 8 | Out-Null; Write-Output 'bad accepted? NO' } catch { Write-Output ('bad rejected status=' + $_.Exception.Response.StatusCode.value__) }
```

Expected: 400

- [ ] **Step 4: 恢复 video_ids.txt 原内容**

```powershell
Copy-Item $bak 'D:\DjangoProject\PythonProject11\video_ids.txt' -Force
Remove-Item $bak -Force
Select-String -LiteralPath 'D:\DjangoProject\PythonProject11\video_ids.txt' -Pattern '2026081199991000' | Measure-Object | ForEach-Object { Write-Output ("left_hits=" + $_.Count) }
```

Expected: `left_hits=0`（原内容已恢复）

- [ ] **Step 5: 全量回归 + 提交**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: POST /api/extension/ids 保留采集 video_id 供爬虫刷新"
```

---

## 阶段 2：插件纯函数（可单测）

### Task 3: parse.js 新增 parseAwemeList / findScrollContainer / mergeCardWithHook / drainHookQueue / formatLocalTime

**Files:**
- Modify: `extension/tests/parse.test.mjs`
- Modify: `extension/content/parse.js`

- [ ] **Step 1: 写失败测试**

在 `extension/tests/parse.test.mjs` 顶部导入追加：

```js
const {
  parseCount,
  extractSecUidFromHref,
  parseProfileCards,
  parseVideoDetail,
  parseAwemeList,
  findScrollContainer,
  mergeCardWithHook,
  drainHookQueue,
} = require('../content/parse.js')
```

文件末尾追加：

```js
const AWEME_JSON = {
  aweme_list: [
    {
      aweme_id: '7672018085449279859',
      desc: '标题A #话题',
      create_time: 1700000000,
      statistics: {
        digg_count: 40000,
        comment_count: 481,
        share_count: 1150,
        play_count: 236,
      },
      author: { nickname: '黑白阿巴巴', uid: '4358913414407163', sec_uid: 'MS4wLjABAAAA_test' },
      video: { cover: { url_list: ['https://p3.douyinpic.com/coverA.jpeg'] } },
    },
    {
      aweme_id: '7672018085449279860',
      desc: '',
      create_time: null,
      statistics: {},
      author: {},
    },
  ],
}

test('parseAwemeList 提取完整字段', () => {
  const records = parseAwemeList(AWEME_JSON)
  assert.equal(records.length, 2)
  const r0 = records[0]
  assert.equal(r0.video_id, '7672018085449279859')
  assert.equal(r0.video_title, '标题A #话题')
  assert.equal(r0.play_count, 236)
  assert.equal(r0.like_count, 40000)
  assert.equal(r0.comment_count, 481)
  assert.equal(r0.share_count, 1150)
  assert.equal(r0.author_name, '黑白阿巴巴')
  assert.equal(r0.author_id, '4358913414407163')
  assert.equal(r0.cover_url, 'https://p3.douyinpic.com/coverA.jpeg')
  assert.match(r0.publish_time, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  assert.deepEqual(r0.missing_fields, [])
})

test('parseAwemeList 容错与详情结构', () => {
  const r1 = parseAwemeList(AWEME_JSON)[1]
  assert.equal(r1.play_count, 0)
  assert.ok(r1.missing_fields.includes('video_title'))
  assert.ok(r1.missing_fields.includes('play_count'))
  const detail = parseAwemeList({ aweme: { aweme_id: '123456789012345678', statistics: { play_count: 5 } } })
  assert.equal(detail.length, 1)
  assert.equal(detail[0].video_id, '123456789012345678')
  assert.deepEqual(parseAwemeList({}), [])
  assert.deepEqual(parseAwemeList(null), [])
})

test('findScrollContainer 命中 overflow 祖先', () => {
  const html = `
  <div id="outer" style="overflow-y:auto;height:600px;">
    <div id="middle">
      <div id="list"><ul><li>a</li><li>b</li></ul></div>
    </div>
  </div>`
  const { document } = domOf(html).window
  const list = document.querySelector('#list')
  assert.equal(findScrollContainer(list, document), document.querySelector('#outer'))
})

test('findScrollContainer 无滚动祖先返回 null', () => {
  const { document } = domOf('<div id="list"><ul><li>a</li></ul></div>').window
  assert.equal(findScrollContainer(document.querySelector('#list'), document), null)
})

test('mergeCardWithHook 用 hook 数据补全卡片', () => {
  const card = {
    video_id: '1', video_title: 'DOM标题', play_count: 10, cover_url: 'c1',
    author_name: 'a', author_id: 'u', missing_fields: [],
  }
  const hook = {
    video_id: '1', video_title: 'Hook标题', play_count: 236, like_count: 40000,
    comment_count: 481, share_count: 1150, publish_time: '2026-05-12 14:13:52',
    cover_url: 'c2', missing_fields: [],
  }
  const merged = mergeCardWithHook(card, hook)
  assert.equal(merged.video_title, 'Hook标题')
  assert.equal(merged.play_count, 236)
  assert.equal(merged.like_count, 40000)
  assert.equal(merged.publish_time, '2026-05-12 14:13:52')
  assert.equal(merged.cover_url, 'c2')
  assert.deepEqual(mergeCardWithHook(card, null), card)
})

test('drainHookQueue 回放并清空缓冲', () => {
  const { document } = domOf('<div></div>').window
  document.documentElement.__dyAnalyzerQueue = [
    JSON.stringify({ source: 'dy-analyzer-hook', data: { aweme_list: [] } }),
    'not-json',
  ]
  const messages = drainHookQueue(document.documentElement)
  assert.equal(messages.length, 1)
  assert.equal(messages[0].source, 'dy-analyzer-hook')
  assert.equal(document.documentElement.__dyAnalyzerQueue.length, 0)
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd extension; npm test`
Expected: FAIL（`parseAwemeList is not a function`）

- [ ] **Step 3: 最小实现**

在 `extension/content/parse.js` 的 `parseVideoDetail` 之后、`api` 定义之前追加：

```js
  /** 秒级时间戳 → 本地时间 'YYYY-MM-DD HH:MM:SS'。 */
  function formatLocalTime(sec) {
    const d = new Date(Number(sec) * 1000);
    if (Number.isNaN(d.getTime())) return null;
    const pad = (n) => String(n).padStart(2, '0');
    return (
      d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' +
      pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
    );
  }

  /** 解析接口 JSON（aweme_list 或 aweme 详情结构）为记录数组。 */
  function parseAwemeList(json) {
    if (!json) return [];
    let list = [];
    if (Array.isArray(json.aweme_list)) {
      list = json.aweme_list;
    } else if (json.aweme && json.aweme.aweme_id) {
      list = [json.aweme];
    }
    const results = [];
    for (const aweme of list) {
      const video_id = String(aweme.aweme_id || '');
      if (!video_id) continue;
      const stats = aweme.statistics || {};
      const missing = [];
      const title = aweme.desc || '';
      if (!title) missing.push('video_title');

      const playValue = stats.play_count;
      const play_count = typeof playValue === 'number' && playValue >= 0 ? playValue : 0;
      if (typeof playValue !== 'number') missing.push('play_count');

      const numOf = (v, field) => {
        if (typeof v === 'number' && v >= 0) return v;
        missing.push(field);
        return 0;
      };
      const like_count = numOf(stats.digg_count, 'like_count');
      const comment_count = numOf(stats.comment_count, 'comment_count');
      const share_count = numOf(stats.share_count, 'share_count');

      const author = aweme.author || {};
      const cover =
        aweme.video && aweme.video.cover && Array.isArray(aweme.video.cover.url_list)
          ? aweme.video.cover.url_list[0] || ''
          : '';
      if (!cover) missing.push('cover_url');

      results.push({
        video_id: video_id,
        video_title: title,
        video_desc: title,
        play_count: play_count,
        like_count: like_count,
        comment_count: comment_count,
        share_count: share_count,
        publish_time: aweme.create_time ? formatLocalTime(aweme.create_time) : null,
        cover_url: cover,
        author_name: author.nickname || '',
        author_id: author.uid ? String(author.uid) : '',
        sec_uid: author.sec_uid || '',
        missing_fields: missing,
      });
    }
    return results;
  }

  /** 从列表容器向上找可滚动祖先（作品列表懒加载容器）。 */
  function findScrollContainer(root, doc) {
    let el = root && root.parentElement;
    while (el && el !== doc.body && el !== doc.documentElement) {
      if (el.scrollHeight > el.clientHeight + 4) return el;
      const cs = el.ownerDocument.defaultView.getComputedStyle(el);
      if (/auto|scroll|overlay/.test(cs.overflowY)) return el;
      el = el.parentElement;
    }
    return null;
  }

  /** hook 数据优先补全 DOM 卡片：互动/发布时间以 hook 为准，播放量取较大可信值。 */
  function mergeCardWithHook(card, hook) {
    if (!hook) return card;
    return {
      video_id: card.video_id,
      video_title: hook.video_title || card.video_title,
      video_desc: hook.video_desc || card.video_desc || '',
      play_count:
        typeof hook.play_count === 'number' && hook.play_count > 0
          ? hook.play_count
          : card.play_count,
      like_count: hook.like_count,
      comment_count: hook.comment_count,
      share_count: hook.share_count,
      publish_time: hook.publish_time,
      cover_url: hook.cover_url || card.cover_url,
      author_name: hook.author_name || card.author_name,
      author_id: hook.author_id || card.author_id,
      sec_uid: card.sec_uid || hook.sec_uid || '',
      missing_fields: hook.missing_fields && hook.missing_fields.length
        ? hook.missing_fields
        : card.missing_fields,
    };
  }

  /** 回放并清空 hook 缓冲队列（DOM 元素自定义属性，跨 world 共享）。 */
  function drainHookQueue(rootEl) {
    const queue = rootEl && Array.isArray(rootEl.__dyAnalyzerQueue)
      ? rootEl.__dyAnalyzerQueue
      : [];
    if (rootEl) rootEl.__dyAnalyzerQueue = [];
    const messages = [];
    for (const raw of queue) {
      try {
        const msg = JSON.parse(raw);
        if (msg && msg.source === 'dy-analyzer-hook') messages.push(msg);
      } catch (e) { /* 忽略坏消息 */ }
    }
    return messages;
  }
```

并更新 `api` 定义：

```js
  const api = {
    parseCount, extractSecUidFromHref, parseProfileCards, parseVideoDetail,
    parseAwemeList, findScrollContainer, mergeCardWithHook, drainHookQueue,
  };
```

- [ ] **Step 4: 运行确认通过**

Run: `cd extension; npm test`
Expected: PASS（新增 7 个测试全过）

- [ ] **Step 5: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/parse.js extension/tests/parse.test.mjs
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: hook 解析/滚动容器/合并/缓冲回放纯函数与 Node 测试"
```

---

## 阶段 3：插件接线

### Task 4: hook.js（页面世界网络 hook）

**Files:**
- Create: `extension/content/hook.js`

- [ ] **Step 1: 新建 `extension/content/hook.js`**

```js
/* 抖音个人视频数据分析器 —— 页面世界网络 hook（被动观察接口响应）
 * 仅读取已存在的响应，不修改请求、不发送新请求。
 * 数据通道：CustomEvent('dy-analyzer-data') + documentElement.__dyAnalyzerQueue 缓冲。
 */
(function () {
  'use strict';
  const QUEUE_KEY = '__dyAnalyzerQueue';
  const MAX_QUEUE = 500;
  const EVENT_NAME = 'dy-analyzer-data';

  function ensureQueue() {
    if (!document.documentElement[QUEUE_KEY]) {
      document.documentElement[QUEUE_KEY] = [];
    }
    return document.documentElement[QUEUE_KEY];
  }

  /** URL 快速路径：作品列表 / 详情接口。 */
  function matchUrl(url) {
    return /\/aweme\/v\d+\/web\/(aweme\/post|aweme\/detail)/.test(url || '');
  }

  /** 结构兜底：只要响应 JSON 含 aweme_list 或 aweme.aweme_id 即可解析。 */
  function hasStructure(json) {
    if (!json || typeof json !== 'object') return false;
    if (Array.isArray(json.aweme_list) && json.aweme_list.length) return true;
    if (json.aweme && json.aweme.aweme_id) return true;
    return false;
  }

  function emit(json) {
    const msg = { source: 'dy-analyzer-hook', data: json };
    try {
      document.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: JSON.stringify(msg) }));
    } catch (e) { /* 页面可能在关闭 */ }
    const queue = ensureQueue();
    queue.push(JSON.stringify(msg));
    if (queue.length > MAX_QUEUE) queue.shift();
  }

  // XHR 观察
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__dyUrl = String(url || '');
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', function () {
      try {
        const url = this.__dyUrl || '';
        if (!matchUrl(url)) return;
        const json = JSON.parse(this.responseText || '');
        if (hasStructure(json)) emit(json);
      } catch (e) { /* 非 JSON 或解析失败，忽略 */ }
    });
    return origSend.apply(this, arguments);
  };

  // fetch 观察
  const origFetch = window.fetch;
  window.fetch = function () {
    const input = arguments[0];
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    return origFetch.apply(this, arguments).then(function (resp) {
      if (matchUrl(url)) {
        resp.clone().text().then(function (body) {
          try {
            const json = JSON.parse(body);
            if (hasStructure(json)) emit(json);
          } catch (e) { /* 忽略 */ }
        }).catch(function () { /* 忽略 */ });
      }
      return resp;
    });
  };
})();
```

- [ ] **Step 2: 语法检查**

Run: `node --check extension/content/hook.js`
Expected: 退出码 0

- [ ] **Step 3: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/hook.js
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 页面世界网络 hook（XHR/fetch 被动观察 + CustomEvent + 缓冲）"
```

### Task 5: collect.js 接线（滚动容器 / hook 合并 / 上报 ids）

**Files:**
- Modify: `extension/content/collect.js`

- [ ] **Step 1: 常量区与模块状态加 hook 相关定义**

在 `const DETAIL_RETRY_TIMES = 4;` 后追加：

```js
  const HOOK_EVENT = 'dy-analyzer-data';
  const QUEUE_KEY = '__dyAnalyzerQueue';
```

在 `let lastPath = '';` 后追加：

```js
  const hookMap = new Map();
```

- [ ] **Step 2: 新增 hook 接收与 ids 上报函数（放在 `readRenderData` 之后）**

```js
  function handleHookData(json) {
    const records = P.parseAwemeList(json);
    for (const r of records) {
      if (!hookMap.has(r.video_id)) hookMap.set(r.video_id, r);
    }
  }

  function setupHookListener() {
    document.addEventListener(HOOK_EVENT, (e) => {
      try {
        const msg = JSON.parse(e.detail || '');
        if (msg && msg.source === 'dy-analyzer-hook') handleHookData(msg.data);
      } catch (err) { /* 忽略坏消息 */ }
    });
    // 回放缓冲：content script 晚于 hook 注入时补齐第一帧数据
    const buffered = P.drainHookQueue(document.documentElement);
    for (const msg of buffered) handleHookData(msg.data);
  }

  async function reportIds(videoIds, authorId) {
    const cfg = await getConfig();
    const resp = await fetch(cfg.backendBaseUrl + '/api/extension/ids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_ids: videoIds, author_id: authorId }),
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
```

- [ ] **Step 3: collectProfile 改用滚动容器 + hook 合并 + 上报 ids**

把 `collectProfile` 中：

```js
    const root = document.querySelector('[data-e2e="user-post-list"]');
    if (!root) {
      showToast('未找到作品列表（user-post-list），请确认在「作品」tab');
      return;
    }
    const cfg = await getConfig();
    const author = { author_name: cfg.myNickname, author_id: cfg.myUid };
```

改为：

```js
    const root = document.querySelector('[data-e2e="user-post-list"]');
    if (!root) {
      showToast('未找到作品列表（user-post-list），请确认在「作品」tab');
      return;
    }
    const cfg = await getConfig();
    const author = { author_name: cfg.myNickname, author_id: cfg.myUid };
    const scroller = P.findScrollContainer(root, document);
```

把循环内收集逻辑：

```js
        for (const card of cards) {
          // 防页面篡改：卡片链接里的 secUid 必须与当前登录账号一致
          if (card.sec_uid && card.sec_uid !== cfg.mySecUid) continue;
          if (!seen.has(card.video_id)) {
            seen.add(card.video_id);
            collected.push(card);
            added += 1;
          }
        }
```

改为：

```js
        for (const card of cards) {
          // 防页面篡改：卡片链接里的 secUid 必须与当前登录账号一致
          if (card.sec_uid && card.sec_uid !== cfg.mySecUid) continue;
          if (!seen.has(card.video_id)) {
            seen.add(card.video_id);
            // hook 数据优先补全（互动/发布时间），DOM 卡片兜底
            const merged = P.mergeCardWithHook(card, hookMap.get(card.video_id));
            collected.push(merged);
            added += 1;
          }
        }
```

把滚动语句：

```js
        window.scrollTo(0, document.documentElement.scrollHeight);
```

改为：

```js
        if (scroller) {
          scroller.scrollTop = scroller.scrollHeight;
        } else {
          window.scrollTo(0, document.documentElement.scrollHeight);
        }
```

在 `showToast('采集完成' ...)` 之后追加 ids 上报：

```js
      try {
        const idsRes = await reportIds([...seen], cfg.myUid);
        console.log('[dy-analyzer] ids 已保留:', idsRes.added, '新增 /', idsRes.total, '总计');
      } catch (e) {
        console.warn('[dy-analyzer] ids 保留失败:', e && e.message ? e.message : e);
      }
```

- [ ] **Step 4: 启动时注册 hook 监听**

把底部启动代码：

```js
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      init();
      watchDetail();
    });
  } else {
    init();
    watchDetail();
  }
```

改为：

```js
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      init();
      watchDetail();
      setupHookListener();
    });
  } else {
    init();
    watchDetail();
    setupHookListener();
  }
```

- [ ] **Step 5: 语法检查 + 提交**

Run: `node --check extension/content/collect.js`
Expected: 退出码 0

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/collect.js
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件接线（滚动容器/hook 合并/采集完成上报 ids）"
```

### Task 6: manifest.json 注入 hook.js（world: MAIN）

**Files:**
- Modify: `extension/manifest.json`

- [ ] **Step 1: 修改 content_scripts**

把：

```json
  "content_scripts": [
    {
      "matches": ["https://www.douyin.com/*"],
      "js": ["content/parse.js", "content/collect.js"],
      "run_at": "document_idle"
    }
  ],
```

改为：

```json
  "content_scripts": [
    {
      "matches": ["https://www.douyin.com/*"],
      "js": ["content/hook.js"],
      "run_at": "document_start",
      "world": "MAIN"
    },
    {
      "matches": ["https://www.douyin.com/*"],
      "js": ["content/parse.js", "content/collect.js"],
      "run_at": "document_idle"
    }
  ],
```

- [ ] **Step 2: JSON 校验 + 提交**

Run: `node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json','utf8')); console.log('manifest OK')"`
Expected: `manifest OK`

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/manifest.json
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: manifest 注入页面世界 hook.js"
```

---

## 阶段 4：收尾

### Task 7: README 更新（全量翻页 / hook / id 保留）

**Files:**
- Modify: `extension/README.md`
- Modify: `README.md`

- [ ] **Step 1: extension/README.md 追加说明**

在「## 使用」第 2 步后追加：

```markdown
2.5 **全量采集与详情信息**：插件会自动翻页加载全部视频（100 条内），
    并被动观察抖音作品列表接口，一次拿到播放量、点赞、评论、分享、发布时间——
    无需逐个打开视频；采集完成后会把视频 ID 去重保存到项目根 `video_ids.txt`，
    供爬虫后续刷新数据。
```

- [ ] **Step 2: 项目 README.md 更新「已知限制」**

把：

```markdown
- 主页卡片只显示播放量；点赞/评论/分享需浏览详情页后回补，未浏览的视频为空/0；
- 当前抖音页面不展示绝对发布时间，`publish_time` 留空（后续网络 hook 补齐）；
```

改为：

```markdown
- 主页自动翻页采集（100 条内一次采全），并通过被动网络 hook 补全点赞/评论/分享/发布时间；
- 浏览详情页时仍可被动补充（hook 未覆盖场景的兜底）；
```

- [ ] **Step 3: 提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/README.md README.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 更新全量翻页/hook/视频ID保留说明"
```

### Task 8: 全量回归与真机验收清单

**Files:** 无新增

- [ ] **Step 1: 后端全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量通过

- [ ] **Step 2: 插件测试回归**

Run: `cd extension; npm test`
Expected: 全部通过

- [ ] **Step 3: 前端构建回归**

Run: `cd frontend; npm run build`
Expected: 构建成功

- [ ] **Step 4: 交付真机验收清单（写入最终汇报）**

1. `chrome://extensions` 刷新插件（加载含 hook.js 的版本）；
2. 自己主页点「开始采集」：
   - 自动翻页直至全部视频（58 条）采完，结果提示成功条数 ≈ 视频总数；
   - 数据库 `play_count` 全量有值（不再出现空播放量）；
   - 点赞/评论/分享/发布时间经 hook 一并入库（不必逐个浏览详情）；
3. 采集完成后项目根 `video_ids.txt` 追加了本次 video_id（去重，原内容保留）；
4. 看板「个人分析」总播放与互动数字刷新；「视频数据」页「播放」列有值；
5. 重复采集不产生重复入库、`video_ids.txt` 不重复追加。

- [ ] **Step 5: Git 边界检查与汇总**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 status --short
git -c safe.directory=D:/DjangoProject/PythonProject11 log --oneline -12
```

Expected: 无未提交的新改动（未跟踪用户截图除外）；提交历史按阶段清晰。
向用户汇报：实现内容、测试证据、真机验收清单、遗留事项（鉴权/定时采集等）。
