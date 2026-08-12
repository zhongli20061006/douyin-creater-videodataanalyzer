# video_ids 作者归属以 hook 真实作者为准 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ids 上报作者改为网络 hook 真实作者（`aweme.author.uid`），并修正文件里已写错的 133 条作者。

**Architecture:** `parse.js` 新增纯函数 `resolveAuthorId`（hook 首个非空作者，无则回退）；`collect.js` 上报时用它替代 `cfg.myUid`；已错数据以库反查覆盖（备份后执行）。

**Tech Stack:** Chrome MV3 vanilla JS + Node test runner + jsdom；Python 一次性修正脚本。

**Spec:** `docs/superpowers/specs/2026-08-12-ids-author-from-hook-design.md`

---

### Task 1: resolveAuthorId 纯函数（TDD）

**Files:**
- Modify: `extension/content/parse.js`
- Modify: `extension/tests/parse.test.mjs`

- [ ] **Step 1: 写失败测试**

`extension/tests/parse.test.mjs` 顶部解构追加 `resolveAuthorId`，文件末尾追加：
```js
test('resolveAuthorId 优先取 hook 真实作者', () => {
  const hooks = [
    { video_id: '1', author_id: '' },
    { video_id: '2', author_id: 'realAuthorUid' },
    { video_id: '3', author_id: 'anotherUid' },
  ]
  assert.equal(resolveAuthorId(hooks, 'fallbackUid'), 'realAuthorUid')
})

test('resolveAuthorId 无 hook 作者时回退 fallback', () => {
  assert.equal(resolveAuthorId([], 'myUid'), 'myUid')
  assert.equal(resolveAuthorId([{ video_id: '1', author_id: '' }], ''), '')
  assert.equal(resolveAuthorId(undefined, 'x'), 'x')
})
```

- [ ] **Step 2: 运行确认 RED**

Run（`extension/`）: `node --test tests/parse.test.mjs`
Expected: FAIL（`resolveAuthorId is not a function`）。

- [ ] **Step 3: 实现 parse.js**

在 `progressLabel` 之后、`const api = {` 之前追加：
```js
  /** 从 hook 记录中取第一个非空 author_id（真实作者）；无则回退 fallback。 */
  function resolveAuthorId(hookRecords, fallback) {
    for (const r of hookRecords || []) {
      if (r && r.author_id) return String(r.author_id);
    }
    return fallback || '';
  }
```

导出列表改为：
```js
  const api = {
    parseCount, extractSecUidFromHref, parseProfileCards, parseVideoDetail,
    parseAwemeList, findScrollContainer, mergeCardWithHook, drainHookQueue,
    idsFromBatch, progressLabel, resolveAuthorId,
  };
```

- [ ] **Step 4: 运行确认 GREEN**

Run（`extension/`）: `node --test tests/parse.test.mjs`
Expected: 全部 PASS。

---

### Task 2: collect.js 接线 + smoke 测试（TDD）

**Files:**
- Modify: `extension/content/collect.js`
- Modify: `extension/tests/collect.smoke.test.mjs`

- [ ] **Step 1: 写失败测试**

`extension/tests/collect.smoke.test.mjs` 末尾追加：
```js
test('主页采集上报 ids 使用 hook 真实作者', async () => {
  const { dom, window, messages } = createPage()
  try {
    assert.ok(await waitFor(() => window.document.getElementById('dy-analyzer-start')))
    const hookJson = {
      aweme_list: [
        {
          aweme_id: '7672018085449279859',
          desc: '标题A',
          create_time: 1700000000,
          statistics: { play_count: 236, digg_count: 40000, comment_count: 481, share_count: 1150 },
          author: { uid: 'realAuthorUid', sec_uid: 'MS4wLjABAAAA_test', nickname: '真实作者' },
          video: { cover: { url_list: ['https://p3.douyinpic.com/coverA.jpeg'] } },
        },
      ],
    }
    window.document.dispatchEvent(new window.CustomEvent('dy-analyzer-data', {
      detail: JSON.stringify({ source: 'dy-analyzer-hook', data: hookJson }),
    }))
    window.document.getElementById('dy-analyzer-start').click()
    assert.ok(await waitFor(() => messages.some((m) => m.url.includes('/api/extension/ids'))))
    const idsMsg = messages.find((m) => m.url.includes('/api/extension/ids'))
    const body = JSON.parse(idsMsg.body)
    assert.equal(body.author_id, 'realAuthorUid')
  } finally {
    dom.window.close()
  }
})
```

- [ ] **Step 2: 运行确认 RED**

Run（`extension/`）: `node --test tests/collect.smoke.test.mjs`
Expected: 新用例 FAIL（上报 author_id 为 `u1` 而非 `realAuthorUid`）。

- [ ] **Step 3: 实现 collect.js**

`collectProfile` 中 `const missingCount = ...` 之后追加：
```js
      const batchAuthorId = P.resolveAuthorId([...hookMap.values()], complianceLimited ? cfg.myUid : '');
```

把 `const idsRes = await reportIds(P.idsFromBatch(batch), cfg.myUid);` 改为：
```js
          const idsRes = await reportIds(P.idsFromBatch(batch), batchAuthorId);
```

- [ ] **Step 4: 运行确认 GREEN**

Run（`extension/`）: `node --test tests/collect.smoke.test.mjs`
Expected: 全部 PASS。

---

### Task 3: 修正已错数据（备份后执行）

**Files:**
- Modify: `video_ids.txt`（一次性数据修正）

- [ ] **Step 1: 备份**

复制 `video_ids.txt` 到 `%TEMP%\dy_ids_backup_20260812\video_ids.txt`。

- [ ] **Step 2: 反查修正（here-string Python）**

```python
import os, shutil, tempfile
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')
from scrapy.utils.project import get_project_settings
import pymysql
import extension_receiver

PATH = 'video_ids.txt'
WRONG = '4358913414407163'
backup_dir = os.path.join(tempfile.gettempdir(), 'dy_ids_backup_20260812')
os.makedirs(backup_dir, exist_ok=True)
shutil.copy2(PATH, os.path.join(backup_dir, 'video_ids.txt'))

records = extension_receiver.read_ids_with_status(PATH)
s = get_project_settings()
conn = pymysql.connect(host=s.get('MYSQL_HOST','localhost'), port=s.getint('MYSQL_PORT',3307),
    user=s.get('MYSQL_USER','root'), password=s.get('MYSQL_PASSWORD',''),
    database=s.get('MYSQL_DB','douyin_spider'), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
changed = 0
for r in records:
    if r['author_id'] == WRONG:
        cur.execute('SELECT author_id FROM video_info WHERE video_id = %s', (r['video_id'],))
        row = cur.fetchone()
        if row and row['author_id'] and row['author_id'] != WRONG:
            r['author_id'] = row['author_id']
            changed += 1
conn.close()
extension_receiver._write_ids_records(PATH, records)
print('修正行数:', changed, '| 总行数:', len(records))
```

Expected: 输出修正行数与总行数；`video_ids.txt` 中错误作者行被库真实作者覆盖。

- [ ] **Step 3: 验证**

读取文件统计作者分布，确认错误 uid 行减少、出现真实作者。

---

### Task 4: 全量回归

Run（`extension/`）: `node --test` → 全部 PASS；
Run: `.\.venv\Scripts\python.exe -m pytest -q` → 104 passed；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）+ 真机验证

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/content/parse.js extension/content/collect.js extension/tests/parse.test.mjs extension/tests/collect.smoke.test.mjs docs/superpowers/specs/2026-08-12-ids-author-from-hook-design.md docs/superpowers/plans/2026-08-12-ids-author-from-hook.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "fix: video_ids 作者归属改为 hook 真实作者，修正误标数据"
```

真机：重载插件 → 采集别人主页 → 收集页作者显示真实作者昵称。
