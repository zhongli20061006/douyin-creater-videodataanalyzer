# 收藏字段（collect_count）纳入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `video_info` 表新增 `collect_count` 列，并让爬虫、插件、后端接收器、分析层与前端全部支持收藏数采集/展示。

**Architecture:** 收藏数作为第 5 个计数指标，完全复用现有 like/comment/share/play 的字段语义（NULL=未采集、非 None 才更新；爬虫缺失写 0、兜底不覆盖）。改动沿现有 owner 扩散：`items.py`/`pipelines.py`/`spider`（爬虫写入）、`parse.js`（插件提取）、`extension_receiver.py`（接收器）、`analyzer.py`/`api.py`（分析/API）、两个 Vue 页面（展示）。

**Tech Stack:** Python 3.13 + FastAPI + pymysql + Scrapy；Chrome MV3 扩展（Node 测试 + jsdom）；Vue3 + Element Plus。

**前置授权与基线（2026-08-12 交接）**

- 数据库结构改动（下方 Task 1 的 ALTER TABLE）已经用户明确授权；
- git 命令一律带 `-c safe.directory=D:/DjangoProject/PythonProject11`；
- 基线：extension `node --test` = 27 passed；pytest = 114 passed；`frontend npm run build` 成功；
- 当前分支 `codex/collect-count`（从 `codex/personal-analyzer-extension` 拉出）。

---

### Task 1: 数据库加列（已授权）

**Files:**
- Modify: MySQL `video_info` 表（库 `douyin_spider`，localhost:3307）

- [ ] **Step 1: 执行 ALTER TABLE**

```sql
ALTER TABLE video_info
  ADD COLUMN collect_count bigint DEFAULT '0' COMMENT '收藏数' AFTER share_count,
  MODIFY COLUMN share_count bigint DEFAULT '0' COMMENT '分享数';
```

在 PowerShell 中通过项目 venv 执行（凭据从 `douyin_spider/settings.py` 读取，不落盘）：

```powershell
@'
import os
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')
from scrapy.utils.project import get_project_settings
import pymysql
s = get_project_settings()
conn = pymysql.connect(host=s.get('MYSQL_HOST','localhost'), port=s.getint('MYSQL_PORT',3307), user=s.get('MYSQL_USER','root'), password=s.get('MYSQL_PASSWORD',''), database=s.get('MYSQL_DB','douyin_spider'), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
with conn.cursor() as cur:
    cur.execute("ALTER TABLE video_info ADD COLUMN collect_count bigint DEFAULT '0' COMMENT '收藏数' AFTER share_count, MODIFY COLUMN share_count bigint DEFAULT '0' COMMENT '分享数'")
    conn.commit()
conn.close()
'@ | .\.venv\Scripts\python.exe -
```

- [ ] **Step 2: 验证表结构**

```powershell
@'
import os
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')
from scrapy.utils.project import get_project_settings
import pymysql
s = get_project_settings()
conn = pymysql.connect(host=s.get('MYSQL_HOST','localhost'), port=s.getint('MYSQL_PORT',3307), user=s.get('MYSQL_USER','root'), password=s.get('MYSQL_PASSWORD',''), database=s.get('MYSQL_DB','douyin_spider'), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
with conn.cursor() as cur:
    cur.execute('SHOW CREATE TABLE video_info')
    print(cur.fetchone()['Create Table'])
conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Expected: `Create Table` 中包含 `` `collect_count` bigint DEFAULT '0' COMMENT '收藏数' ``，且 `share_count` 注释为「分享数」。

- [ ] **Step 3: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add docs/superpowers/specs/2026-08-12-collect-count-design.md docs/superpowers/plans/2026-08-12-collect-count.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 收藏字段设计与实施计划"
```

（若这两个文档已提交过，则跳过本步，直接进入 Task 2。）

---

### Task 2: 爬虫写入端（items.py + pipelines.py，TDD）

**Files:**
- Modify: `douyin_spider/items.py`
- Modify: `douyin_spider/pipelines.py`
- Test: `tests/test_pipelines.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_pipelines.py` 末尾）**

```python
def test_build_insert_params_includes_collect_count_default_zero():
    """兜底 item 未携带收藏时默认 0。"""
    item = DouyinVideoItem(video_id='123', video_title='标题')
    params = build_insert_params(item)
    assert params['collect_count'] == 0


def test_build_insert_params_keeps_collect_count():
    """完整 item 的收藏值原样保留。"""
    item = DouyinVideoItem(video_id='1', like_count=3, collect_count=88)
    params = build_insert_params(item)
    assert params['collect_count'] == 88
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipelines.py -q
```

Expected: FAIL，`KeyError: 'collect_count'`。

- [ ] **Step 3: 实现 `douyin_spider/items.py`**

在 `play_count = scrapy.Field()` 之后新增字段，并把 `share_count` 注释改为「分享数」：

```python
    # 分享数
    share_count = scrapy.Field()
    # 播放量
    play_count = scrapy.Field()
    # 收藏数
    collect_count = scrapy.Field()
```

- [ ] **Step 4: 实现 `douyin_spider/pipelines.py`**

`build_insert_params` 在 `'play_count': item.get('play_count', 0),` 后新增一行：

```python
        'collect_count': item.get('collect_count', 0),
```

`upsert_sql` 的 INSERT 列清单与 VALUES 各加 `collect_count`（第 10 列位置，紧跟 play_count）：

```python
        upsert_sql = """
              INSERT INTO video_info
              (video_id, video_title, video_desc, author_name, author_id,
               publish_time, like_count, comment_count, share_count, play_count, collect_count,
               video_url, cover_url, crawl_time)
              VALUES (%(video_id)s, %(video_title)s, %(video_desc)s, %(author_name)s, %(author_id)s, \
                      %(publish_time)s, %(like_count)s, %(comment_count)s, %(share_count)s, %(play_count)s, %(collect_count)s, \
                      %(video_url)s, %(cover_url)s, %(crawl_time)s) ON DUPLICATE KEY \
              UPDATE \
                  video_title = \
              VALUES (video_title), video_desc = \
              VALUES (video_desc), author_name = \
              VALUES (author_name), author_id = \
              VALUES (author_id), publish_time = \
              VALUES (publish_time), like_count = \
              VALUES (like_count), comment_count = \
              VALUES (comment_count), share_count = \
              VALUES (share_count), play_count = \
              VALUES (play_count), collect_count = \
              VALUES (collect_count), video_url = \
              VALUES (video_url), cover_url = \
              VALUES (cover_url), update_time = NOW() \
              """
```

`insert_ignore_sql` 的列清单与 VALUES 同样加 `collect_count`（紧跟 play_count）。

- [ ] **Step 5: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipelines.py -q
```

Expected: PASS（该文件原 13 个测试 + 新增 2 个，全部通过）。

- [ ] **Step 6: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add douyin_spider/items.py douyin_spider/pipelines.py tests/test_pipelines.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 爬虫写入端支持收藏字段 collect_count"
```

---

### Task 3: 爬虫解析端（douyin_video.py，TDD）

**Files:**
- Modify: `douyin_spider/spiders/douyin_video.py`
- Test: `tests/test_spider_fallback.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_spider_fallback.py` 末尾）**

```python
def test_parse_video_data_extracts_collect_count():
    spider = make_spider()
    aweme = {
        'aweme_id': '123456789012345678',
        'desc': '标题',
        'statistics': {
            'digg_count': 100,
            'comment_count': 5,
            'share_count': 2,
            'play_count': 1000,
            'collect_count': 66,
        },
        'author': {'nickname': '作者', 'uid': 'u1'},
        'video': {
            'play_addr': {'url_list': ['https://x/v.mp4']},
            'cover': {'url_list': ['https://x/c.jpeg']},
        },
    }
    item = spider.parse_video_data(aweme)
    assert item['collect_count'] == 66


def test_parse_video_data_defaults_collect_count_zero_when_missing():
    spider = make_spider()
    aweme = {
        'aweme_id': '123456789012345678',
        'desc': '标题',
        'statistics': {},
        'author': {'nickname': '作者', 'uid': 'u1'},
        'video': {},
    }
    item = spider.parse_video_data(aweme)
    assert item['collect_count'] == 0
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_spider_fallback.py -q
```

Expected: FAIL，`item['collect_count']` 抛出 KeyError。

- [ ] **Step 3: 实现 `douyin_spider/spiders/douyin_video.py`**

在 `parse_video_data` 的 statistics 映射处，`item['play_count'] = statistics.get('play_count', 0)` 后新增一行：

```python
            item['collect_count'] = statistics.get('collect_count', 0)
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_spider_fallback.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add douyin_spider/spiders/douyin_video.py tests/test_spider_fallback.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 爬虫解析 statistics.collect_count"
```

---

### Task 4: 插件解析端（parse.js，TDD）

**Files:**
- Modify: `extension/content/parse.js`
- Test: `extension/tests/parse.test.mjs`

- [ ] **Step 1: 写失败测试（修改 `extension/tests/parse.test.mjs`）**

1a. `DETAIL_HTML` 常量在 `video-player-share` 块后新增收藏按钮块：

```js
  <div data-e2e="video-player-collect"><div></div><div class="collect-num">3.2万</div></div>
```

1b. `test('parseVideoDetail 提取互动数据与作者 secUid')` 增加断言：

```js
  assert.equal(detail.collect_count, 32000)
```

1c. `AWEME_JSON` 的 `statistics` 增加 `collect_count: 6666,`；`test('parseAwemeList 提取完整字段')` 增加断言：

```js
  assert.equal(r0.collect_count, 6666)
```

1d. `test('parseAwemeList 容错与详情结构')` 增加断言（statistics 为空的第二条记录）：

```js
  assert.ok(r1.missing_fields.includes('collect_count'))
```

1e. `test('parseVideoDetail 支持主页浮层 modal_id 场景')` 的 HTML 无收藏元素，增加断言：

```js
  assert.ok(detail.missing_fields.includes('collect_count'))
```

1f. `test('mergeCardWithHook 用 hook 数据补全卡片')` 的 `hook` 增加 `collect_count: 888,`，断言增加：

```js
  assert.equal(merged.collect_count, 888)
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd extension; node --test
```

Expected: FAIL（collect_count 断言为 undefined / missing_fields 不含 collect_count）。

- [ ] **Step 3: 实现 `extension/content/parse.js`**

3a. `parseVideoDetail` 在 `share_count` 提取块之后新增：

```js
    const collectValue = countIn(root.querySelector('[data-e2e="video-player-collect"]'));
    const collect_count = collectValue === null ? 0 : collectValue;
    if (collectValue === null) missing.push('collect_count');
```

并在返回对象中 `share_count: share_count,` 后加 `collect_count: collect_count,`。

3b. `parseAwemeList` 在 `const share_count = numOf(stats.share_count, 'share_count');` 后加：

```js
      const collect_count = numOf(stats.collect_count, 'collect_count');
```

并在返回对象中 `share_count: share_count,` 后加 `collect_count: collect_count,`。

3c. `mergeCardWithHook` 返回对象中 `share_count: hook.share_count,` 后加：

```js
      collect_count: hook.collect_count,
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd extension; node --test
```

Expected: 27 + 新增断言全部通过（测试数量不变，断言变多）。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/parse.js extension/tests/parse.test.mjs
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 插件提取收藏数（hook JSON + 详情页 DOM）"
```

---

### Task 5: 后端接收器（extension_receiver.py，TDD）

**Files:**
- Modify: `extension_receiver.py`
- Test: `tests/test_extension_receiver.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_extension_receiver.py` 末尾）**

```python
def test_normalize_record_accepts_collect_count():
    record, reason = normalize_record({
        'video_id': '7638884656238410714',
        'collect_count': 888,
    })
    assert reason is None
    assert record['collect_count'] == 888


def test_normalize_record_collect_count_none_when_missing():
    record, _ = normalize_record({'video_id': '7638884656238410714'})
    assert record['collect_count'] is None


def test_normalize_record_rejects_bad_collect_count():
    record, reason = normalize_record({
        'video_id': '7638884656238410714',
        'collect_count': -1,
    })
    assert record is None and reason


def test_build_upsert_includes_collect_count():
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
        'play_count': None,
        'collect_count': 888,
        'video_url': '',
        'cover_url': '',
    }
    sql, _ = build_upsert(record)
    assert 'collect_count=VALUES(collect_count)' in sql


def test_build_upsert_skips_none_collect_count():
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
        'play_count': None,
        'collect_count': None,
        'video_url': '',
        'cover_url': '',
    }
    sql, _ = build_upsert(record)
    assert 'collect_count=VALUES(collect_count)' not in sql
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q
```

Expected: FAIL（record 无 collect_count 键 / SQL 不含收藏列）。

- [ ] **Step 3: 实现 `extension_receiver.py`**

`COUNT_FIELDS` 改为：

```python
COUNT_FIELDS = ('like_count', 'comment_count', 'share_count', 'play_count', 'collect_count')
```

`INSERT_COLUMNS` 末尾追加 `'collect_count'`：

```python
INSERT_COLUMNS = (
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'play_count',
    'video_url', 'cover_url', 'collect_count',
)
```

（`build_upsert` 按 `INSERT_COLUMNS` 动态取列，无需改结构；`normalize_record` 的 COUNT_FIELDS 循环自动继承校验。）

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q
```

Expected: 原 44 个 + 新增 5 个全部通过。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py tests/test_extension_receiver.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 扩展接收器支持收藏字段 collect_count"
```

---

### Task 6: 分析层（analyzer.py，TDD）

**Files:**
- Modify: `analyzer.py`
- Test: `tests/test_analyzer.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_analyzer.py` 末尾）**

```python
def test_summarize_total_collects():
    rows = [
        make_row(video_id='1', collect_count=300),
        make_row(video_id='2', collect_count=150),
    ]
    summary = summarize_rows(rows)
    assert summary['total_collects'] == 450


def test_summarize_collect_completeness():
    rows = [
        make_row(video_id='1', collect_count=0),
        make_row(video_id='2', collect_count=200),
        make_row(video_id='3', collect_count=None),
    ]
    c = summarize_rows(rows)['completeness']['collect']
    assert c == {'missing': 2, 'total': 3, 'missing_rate': round(2 / 3, 4)}


def test_top_videos_sort_by_collects():
    rows = [make_row(video_id=str(i), collect_count=i * 3) for i in range(1, 12)]
    top = top_videos(rows, limit=3, sort_by='collects')
    assert [r['video_id'] for r in top] == ['11', '10', '9']
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: FAIL（`total_collects` 缺失 / completeness 无 collect / sort_by 报 KeyError）。

- [ ] **Step 3: 实现 `analyzer.py`**

3a. `summarize_rows` 的 completeness 元组加 `'collect_count'`：

```python
    for field in ('play_count', 'like_count', 'comment_count', 'share_count', 'collect_count', 'publish_time'):
```

3b. return 中 `'total_plays': total('play_count'),` 后加：

```python
        'total_collects': total('collect_count'),
```

3c. `SORT_KEYS` 加：

```python
    'collects': 'collect_count',
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analyzer.py -q
```

Expected: 原 14 个 + 新增 3 个全部通过。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add analyzer.py tests/test_analyzer.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 分析层支持收藏汇总/完整度/排序"
```

---

### Task 7: API 层（api.py）

**Files:**
- Modify: `api.py`

- [ ] **Step 1: `VideoItem` 模型加字段**

在 `share_count: Optional[int] = None` 后加：

```python
    collect_count: Optional[int] = None
```

- [ ] **Step 2: `/api/videos` 排序白名单加字段**

`allowed_sort` 集合加 `'collect_count'`：

```python
        'like_count', 'comment_count', 'share_count', 'play_count', 'collect_count',
```

- [ ] **Step 3: 回归验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 114 + 本计划新增用例全部通过（Task 2/3/5/6 新增约 12 个）。

- [ ] **Step 4: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add api.py
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: API 返回与排序支持收藏字段"
```

---

### Task 8: 前端展示（PersonalAnalyzer.vue + Videos.vue）

**Files:**
- Modify: `frontend/src/pages/PersonalAnalyzer.vue`
- Modify: `frontend/src/pages/Videos.vue`

- [ ] **Step 1: `PersonalAnalyzer.vue` 类型扩展**

`PersonalData.summary` 加 `total_collects: number`；`top_videos` 项加 `collect_count?: number`。

- [ ] **Step 2: `PersonalAnalyzer.vue` 互动总量图加收藏**

`interactionData` 数组加一项：

```ts
    { name: '收藏', value: s.total_collects },
```

- [ ] **Step 3: `PersonalAnalyzer.vue` 完整度加收藏行**

`completenessFields` 数组加：

```ts
  { key: 'collect', label: '收藏' },
```

- [ ] **Step 4: `PersonalAnalyzer.vue` StatCard 布局与总收藏卡**

原 6 卡 `el-row`（6 × span=4）改为两行：首行 4 卡（视频数/总播放/总点赞/总评论，`span=6`），次行 3 卡（总分享/总收藏/最近同步，`span=8`）；第二行新增：

```html
        <el-col :span="8">
          <StatCard title="总收藏" :value="fmtNum(data.summary.total_collects)" status="warning" />
        </el-col>
```

- [ ] **Step 5: `PersonalAnalyzer.vue` Top 排序与列**

`el-select` 加：

```html
              <el-option label="按收藏" value="collects" />
```

Top 表格在「分享」列后加：

```html
          <el-table-column label="收藏" width="90">
            <template #default="{ row }">{{ fmtNum(row.collect_count) }}</template>
          </el-table-column>
```

- [ ] **Step 6: `Videos.vue` 类型与表格**

`VideoItem` 接口加 `collect_count?: number`；`sortOptions` 加：

```ts
  { value: 'collect_count', label: '收藏数' },
```

表格「分享」列后加：

```html
        <el-table-column label="收藏" width="90">
          <template #default="{ row }">{{ fmtNum(row.collect_count) }}</template>
        </el-table-column>
```

详情抽屉合并行改为：

```html
          <el-descriptions-item label="点赞/评论/分享/收藏/播放">
            {{ fmtNum(detail.like_count) }} / {{ fmtNum(detail.comment_count) }} / {{ fmtNum(detail.share_count) }} / {{ fmtNum(detail.collect_count) }} / {{ fmtNum(detail.play_count) }}
          </el-descriptions-item>
```

- [ ] **Step 7: 构建验证**

```powershell
cd frontend; npm run build
```

Expected: 构建成功（chunk 大小警告为既有提示）。

- [ ] **Step 8: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add frontend/src/pages/PersonalAnalyzer.vue frontend/src/pages/Videos.vue
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 前端展示收藏统计（个人分析 + 视频数据）"
```

---

### Task 9: 全量回归

**Files:** 无（验证任务）

- [ ] **Step 1: 后端全量测试**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 全部通过（126 左右）。

- [ ] **Step 2: 插件全量测试**

```powershell
cd extension; node --test
```

Expected: 27 个测试全部通过（含新增断言）。

- [ ] **Step 3: 前端构建**

```powershell
cd frontend; npm run build
```

Expected: 构建成功。

- [ ] **Step 4: 确认工作树状态**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 status --short
```

Expected: 仅剩 `?? docs/superpowers/handoff/`（交接目录，保持不动）。

---

### Task 10: 真机验收（用户指定）

**Files:** 无（联网验收任务，执行前需用户再次确认）

- [ ] **Step 1: 确认后端运行**

检查 `http://127.0.0.1:8001` 可用（`backend.pid` 对应进程）；若未运行，经用户确认后执行 `.\run_backend.ps1`。

- [ ] **Step 2: 与用户确认两条测试 video_id**

从 `video_ids.txt` 或 `video_info` 表选取 2 条历史视频，列出 video_id + 标题 + 当前 share_count 快照，请用户确认后再推队列（涉及联网启动爬虫）。

- [ ] **Step 3: 推送并启动爬虫**

调用 `POST /api/crawl`（X-API-Token 从 `local_config.py` 的 `EXTENSION_API_TOKEN` 读取）推送 2 条，再经用户确认调用 `POST /api/spider/start` 启动爬虫，跑完一轮详情采集（`start_spider.py --mode start` 为等价命令行入口）。

- [ ] **Step 4: 验证入库**

查询这 2 条 `video_id` 的 `collect_count`、`update_time`；对比接口实际返回（爬虫日志中的 statistics）：

```sql
SELECT video_id, video_title, like_count, comment_count, share_count, collect_count, crawl_time, update_time
FROM video_info WHERE video_id IN (%s, %s);
```

Expected: `collect_count` 为接口真实值；若被反爬拦截，行数据不被破坏（兜底路径不覆盖）。

- [ ] **Step 5: 向用户提供浏览器手动验证步骤**

1. `chrome://extensions` 重新加载扩展；
2. 刷新抖音页面；
3. 自己主页点「开始采集」或打开自己视频点「同步本页」；
4. 打开视频数据页确认收藏列有值、个人分析页确认总收藏/互动图/完整度/Top 排序生效。

---

### Task 11: 收尾与真源更新

**Files:**
- Modify: `docs/superpowers/handoff/2026-08-12-new-window-handoff.md`

- [ ] **Step 1: 更新交接文档**

在「本窗口完成」追加收藏字段条目（爬虫/插件/接收器/分析/API/前端），把「下一步 1（收藏字段）」标记为已完成或移除，验证基线数字更新（pytest 数量、node --test 数量），并记录真机验收结果。

- [ ] **Step 2: Commit**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add docs/superpowers/handoff/2026-08-12-new-window-handoff.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "docs: 收藏字段完成收尾，更新交接真源"
```
