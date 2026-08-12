# 采集计数/手动停止 + id 链路修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 插件主页采集支持实时计数与手动停止（停止后已采数据照常入库、id 照常保留），并将 id 上报改为每批 ≤100 增量，修复大主页 id 整批被拒的问题。

**Architecture:** 纯逻辑（id 批量提取、进度文案）放入 `extension/content/parse.js` 供 Node 测试；DOM/状态接线在 `extension/content/collect.js`（按钮组、可中断 sleep/wait、每批上报 ids），用 jsdom 冒烟测试覆盖；后端接口与文件格式不变。

**Tech Stack:** Chrome MV3（vanilla JS）、Node test runner + jsdom、pytest（回归）。

**Spec:** `docs/superpowers/specs/2026-08-11-extension-stop-counter-ids-fix-design.md`

---

### Task 1: 纯函数 idsFromBatch / progressLabel（TDD）

**Files:**
- Modify: `extension/tests/parse.test.mjs`
- Modify: `extension/content/parse.js`

- [ ] **Step 1: 写失败测试**

在 `extension/tests/parse.test.mjs` 顶部 require 解构中追加 `idsFromBatch` 与 `progressLabel`：

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
  idsFromBatch,
  progressLabel,
} = require('../content/parse.js')
```

在文件末尾追加：

```js
test('idsFromBatch 提取并去重 video_id', () => {
  const batch = [
    { video_id: '7672018085449279859', video_title: 'a' },
    { video_id: '7672018085449279860', video_title: 'b' },
    { video_id: '7672018085449279859', video_title: 'a-dup' },
  ]
  assert.deepEqual(idsFromBatch(batch), ['7672018085449279859', '7672018085449279860'])
})

test('idsFromBatch 空批与缺 id 记录返回空数组', () => {
  assert.deepEqual(idsFromBatch([]), [])
  assert.deepEqual(idsFromBatch([{ video_id: '' }, { video_title: 'x' }]), [])
})

test('progressLabel 生成采集进度文案', () => {
  assert.equal(progressLabel(0), '采集中 0 条')
  assert.equal(progressLabel(39), '采集中 39 条')
  assert.equal(progressLabel(100), '采集中 100 条')
})
```

- [ ] **Step 2: 运行测试确认 RED**

Run（在 `extension/` 目录）: `node --test tests/parse.test.mjs`
Expected: FAIL，`idsFromBatch is not a function`（函数未定义）。

- [ ] **Step 3: 最小实现**

在 `extension/content/parse.js` 的 `drainHookQueue` 之后追加：

```js
  /** 从一批记录中提取去重后的 video_id 列表（每批 ≤ 100，天然满足后端上限）。*/
  function idsFromBatch(records) {
    const seen = new Set();
    const ids = [];
    for (const r of records || []) {
      const vid = r && r.video_id ? String(r.video_id) : '';
      if (vid && !seen.has(vid)) {
        seen.add(vid);
        ids.push(vid);
      }
    }
    return ids;
  }

  /** 采集进度文案：采集中 N 条。*/
  function progressLabel(count) {
    return '采集中 ' + Number(count || 0) + ' 条';
  }
```

并把 `const api = { ... }` 导出列表追加 `idsFromBatch, progressLabel`：

```js
  const api = {
    parseCount, extractSecUidFromHref, parseProfileCards, parseVideoDetail,
    parseAwemeList, findScrollContainer, mergeCardWithHook, drainHookQueue,
    idsFromBatch, progressLabel,
  };
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run（在 `extension/` 目录）: `node --test tests/parse.test.mjs`
Expected: PASS（全部用例通过，无报错）。

- [ ] **Step 5: 提交**

```bash
git add extension/content/parse.js extension/tests/parse.test.mjs
git commit -m "feat: idsFromBatch/progressLabel 纯函数与测试"
```

---

### Task 2: collect.js 计数/停止/每批 ids 接线（jsdom 冒烟 TDD）

**Files:**
- Create: `extension/tests/collect.smoke.test.mjs`
- Modify: `extension/content/collect.js`

- [ ] **Step 1: 写失败冒烟测试**

新建 `extension/tests/collect.smoke.test.mjs`：

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'

const parseSrc = readFileSync(new URL('../content/parse.js', import.meta.url), 'utf-8')
const collectSrc = readFileSync(new URL('../content/collect.js', import.meta.url), 'utf-8')

const PROFILE = `
<div data-e2e="user-post-list"><ul>
  <li><div><a href="/video/7672018085449279859?secUid=MS4wLjABAAAA_test"><div class="jXmtohcJ"><span></span><span>236</span></div><p class="frUrWD64">标题A</p></a></div></li>
  <li><div><a href="/video/7672018085449279860?secUid=MS4wLjABAAAA_test"><div class="jXmtohcJ"><span></span><span>481</span></div><p class="frUrWD64">标题B</p></a></div></li>
</ul></div>`

function createPage() {
  const dom = new JSDOM(PROFILE, {
    url: 'https://www.douyin.com/user/self?from_tab_name=main',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  })
  const { window } = dom
  window.chrome = {
    storage: {
      local: {
        get: (_keys, cb) => cb({
          backendBaseUrl: 'http://127.0.0.1:8001',
          myUid: 'u1',
          mySecUid: 's1',
          myNickname: '测试',
          complianceMode: 'unlimited',
        }),
        set: (_obj, cb) => { if (cb) cb() },
      },
    },
  }
  const calls = []
  window.fetch = async (url) => {
    calls.push(String(url))
    if (String(url).includes('/api/extension/ids')) {
      return { ok: true, json: async () => ({ added: 0, total: 2 }) }
    }
    return { ok: true, json: async () => ({ accepted: 1, upserted: 1, rejected: [] }) }
  }
  window.scrollTo = () => {}
  window.eval(parseSrc)
  window.eval(collectSrc)
  return { dom, window, calls }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitFor(fn, timeoutMs = 5000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (fn()) return true
    await sleep(50)
  }
  return false
}

test('主页采集显示实时计数并可手动停止，数据与 id 照常上报', async () => {
  const { dom, window, calls } = createPage()
  try {
    assert.ok(await waitFor(() => window.document.getElementById('dy-analyzer-start')))
    const mainBtn = window.document.getElementById('dy-analyzer-start')
    mainBtn.click()

    // 采集开始：停止按钮出现，主按钮显示「采集中 N 条」并递增到 2
    assert.ok(await waitFor(() => window.document.getElementById('dy-analyzer-stop')))
    assert.ok(await waitFor(() => (mainBtn.textContent || '').includes('采集中')))
    assert.ok(await waitFor(() => (mainBtn.textContent || '').includes('2 条')))

    // 手动停止
    window.document.getElementById('dy-analyzer-stop').click()
    assert.ok(await waitFor(() => {
      const t = window.document.getElementById('dy-analyzer-toast')
      return t && t.textContent.includes('已手动停止')
    }))

    // 已采数据照常入库、id 按批上报
    assert.ok(calls.some((u) => u.includes('/api/extension/videos')))
    assert.ok(calls.some((u) => u.includes('/api/extension/ids')))

    // 采集结束按钮复位
    assert.ok(await waitFor(() => mainBtn.textContent === '开始采集'))
  } finally {
    dom.window.close()
  }
})
```

- [ ] **Step 2: 运行确认 RED**

Run（在 `extension/` 目录）: `node --test tests/collect.smoke.test.mjs`
Expected: FAIL（`dy-analyzer-start` 不存在 / 无停止按钮 / 无计数与 toast）。

- [ ] **Step 3: 实现 collect.js**

`extension/content/collect.js` 改动点（按顺序）：

3.1 模块级新增状态标志：

```js
  let homeButtonAdded = false;
  let detailStarted = false;
  let lastPath = '';
  const hookMap = new Map();
  let complianceLimited = false;
  let stopRequested = false;
```

3.2 `sleep` 改为可中断（100ms 轮询检查停止标志）：

```js
  function sleep(ms) {
    return new Promise((resolve) => {
      const start = Date.now();
      const timer = setInterval(() => {
        if (stopRequested || Date.now() - start >= ms) {
          clearInterval(timer);
          resolve();
        }
      }, 100);
    });
  }
```

3.3 `waitForGrowth` 定时器回调同时检查停止标志：

```js
  function waitForGrowth(root, currentCount, timeoutMs) {
    return new Promise((resolve) => {
      const start = Date.now();
      const timer = setInterval(() => {
        if (
          stopRequested ||
          root.querySelectorAll('li').length > currentCount ||
          Date.now() - start > (timeoutMs || 6000)
        ) {
          clearInterval(timer);
          resolve();
        }
      }, 300);
    });
  }
```

3.4 `createCollectButton` 升级为「主按钮 + 停止按钮」容器：

```js
  function createCollectButton() {
    const old = document.getElementById('dy-analyzer-btn');
    if (old) old.remove();
    const wrap = document.createElement('div');
    wrap.id = 'dy-analyzer-btn';
    wrap.style.cssText =
      'position:fixed;right:16px;bottom:16px;z-index:2147483647;display:flex;gap:8px;align-items:center;' +
      'font-family:system-ui,sans-serif;';
    const btn = document.createElement('div');
    btn.id = 'dy-analyzer-start';
    btn.textContent = '开始采集';
    btn.style.cssText =
      'background:#409eff;color:#fff;border-radius:20px;padding:10px 18px;font-size:14px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.35);user-select:none;white-space:nowrap;';
    btn.addEventListener('click', collectProfile);
    const stop = document.createElement('div');
    stop.id = 'dy-analyzer-stop';
    stop.textContent = '停止';
    stop.style.cssText =
      'display:none;background:#f56c6c;color:#fff;border-radius:20px;padding:10px 18px;font-size:14px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.35);user-select:none;white-space:nowrap;';
    stop.addEventListener('click', requestStop);
    wrap.appendChild(btn);
    wrap.appendChild(stop);
    document.body.appendChild(wrap);
    return wrap;
  }
```

3.5 新增 `requestStop`（防重复点击）：

```js
  function requestStop() {
    if (stopRequested) return;
    stopRequested = true;
    const stop = document.getElementById('dy-analyzer-stop');
    if (stop) {
      stop.textContent = '已请求停止';
      stop.style.pointerEvents = 'none';
    }
  }
```

3.6 `collectProfile` 改造（计数、停止、每批上报 ids）：

```js
  async function collectProfile() {
    const startBtn = document.getElementById('dy-analyzer-start');
    const stopBtn = document.getElementById('dy-analyzer-stop');
    const root = document.querySelector('[data-e2e="user-post-list"]');
    if (!root) {
      showToast('未找到作品列表（user-post-list），请确认在「作品」tab');
      return;
    }
    const cfg = await getConfig();
    const author = { author_name: cfg.myNickname, author_id: cfg.myUid };
    const scroller = P.findScrollContainer(root, document);
    console.log(
      '[dy-analyzer] 采集开始: scroller=',
      scroller ? scroller.tagName + '.' + String(scroller.className || '').slice(0, 40) : 'none(window)',
      '初始li=', root.querySelectorAll('li').length,
      'hook已缓存=', hookMap.size,
    );
    stopRequested = false;
    startBtn.textContent = P.progressLabel(0);
    startBtn.style.pointerEvents = 'none';
    if (stopBtn) {
      stopBtn.textContent = '停止';
      stopBtn.style.pointerEvents = 'auto';
      stopBtn.style.display = 'block';
    }

    const seen = new Set();
    const collected = [];
    let roundsWithoutNew = 0;
    let lastScrollHeight = -1;
    let noGrowRounds = 0;

    try {
      while (!stopRequested && seen.size < MAX_VIDEOS && roundsWithoutNew < 3 && noGrowRounds < 3) {
        const cards = P.parseProfileCards(root, author);
        let added = 0;
        for (const card of cards) {
          if (complianceLimited && card.sec_uid && card.sec_uid !== cfg.mySecUid) continue;
          if (!seen.has(card.video_id)) {
            seen.add(card.video_id);
            const merged = P.mergeCardWithHook(card, hookMap.get(card.video_id));
            collected.push(merged);
            added += 1;
          }
        }
        roundsWithoutNew = added === 0 ? roundsWithoutNew + 1 : 0;
        startBtn.textContent = P.progressLabel(seen.size);
        const scrollHeight = scroller ? scroller.scrollHeight : document.documentElement.scrollHeight;
        const scrollTop = scroller ? scroller.scrollTop : window.scrollY;
        const clientHeight = scroller ? scroller.clientHeight : window.innerHeight;
        if (scrollHeight === lastScrollHeight) {
          noGrowRounds += 1;
        } else {
          noGrowRounds = 0;
          lastScrollHeight = scrollHeight;
        }
        console.log(
          '[dy-analyzer] 一轮: li=', root.querySelectorAll('li').length,
          'seen=', seen.size, '本轮新增=', added,
          'scroll=', scrollTop, '/', scrollHeight, '/', clientHeight,
          '无新增轮=', roundsWithoutNew, '高度不变轮=', noGrowRounds,
        );
        if (seen.size >= MAX_VIDEOS) break;
        if (scroller) {
          scroller.scrollTop = scroller.scrollHeight;
        } else {
          window.scrollTo(0, document.documentElement.scrollHeight);
        }
        await sleep(1500 + Math.random() * 1500);
        await waitForGrowth(root, seen.size);
      }

      if (stopRequested && seen.size === 0) {
        showToast('已取消，未采集到数据');
        return;
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
          console.log(
            '[dy-analyzer] 批次上报: batch=', batch.length,
            'accepted=', res.accepted, 'upserted=', res.upserted,
            'rejected=', (res.rejected || []).length,
          );
          for (const r of res.rejected || []) {
            rejected.push(r);
            if (rejected.length <= 3) console.log('[dy-analyzer] 拒绝原因:', r);
          }
        } catch (e) {
          console.warn('[dy-analyzer] 批次上报异常:', e && e.message ? e.message : e);
          rejected.push({ video_id: 'batch' + i, reason: String(e.message || e) });
        }
        try {
          const idsRes = await reportIds(P.idsFromBatch(batch), cfg.myUid);
          console.log('[dy-analyzer] 批内 ids 已保留:', idsRes.added, '新增 /', idsRes.total, '总计');
        } catch (e) {
          console.warn('[dy-analyzer] 批内 ids 保留失败:', e && e.message ? e.message : e);
        }
      }
      let head;
      if (stopRequested) {
        head = '已手动停止';
      } else if (seen.size >= MAX_VIDEOS) {
        head = '采集完成（已达采集上限 ' + MAX_VIDEOS + ' 条）';
      } else {
        head = '采集完成';
      }
      showToast(
        head + '：成功 ' + collected.length + ' 条，字段缺失 ' +
        missingCount + ' 处，被拒 ' + rejected.length + ' 条',
      );
    } catch (e) {
      showToast('采集出错：' + (e && e.message ? e.message : e));
    } finally {
      startBtn.textContent = '开始采集';
      startBtn.style.pointerEvents = 'auto';
      if (stopBtn) {
        stopBtn.style.display = 'none';
        stopBtn.style.pointerEvents = 'auto';
        stopBtn.textContent = '停止';
      }
      stopRequested = false;
    }
  }
```

3.7 删除原「结束一次性 reportIds」块（原 `try { const idsRes = await reportIds([...seen], cfg.myUid); ... } catch` 整段）。

- [ ] **Step 4: 运行冒烟测试确认 GREEN**

Run（在 `extension/` 目录）: `node --test tests/collect.smoke.test.mjs`
Expected: PASS。

- [ ] **Step 5: 全量插件测试回归**

Run（在 `extension/` 目录）: `node --test tests/`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add extension/content/collect.js extension/tests/collect.smoke.test.mjs
git commit -m "feat: 主页采集实时计数/手动停止，id 按批增量上报"
```

---

### Task 3: README 更新 + 全量回归

**Files:**
- Modify: `extension/README.md`

- [ ] **Step 1: README 补充停止/计数说明**

在 `extension/README.md` 的采集用法处追加：

```markdown
### 采集计数与手动停止

- 点击「开始采集」后，按钮实时显示「采集中 N 条」；
- 需要提前结束时点旁边的红色「停止」：停止滚动，但已采集数据照常入库、id 照常保留；
- 一条都未采集时停止会直接取消，不入库。
```

- [ ] **Step 2: 全量回归**

```bash
cd extension && node --test tests/
cd D:/DjangoProject/PythonProject11 && .\.venv\Scripts\python.exe -m pytest -q
cd frontend && npm run build
```

Expected: 插件 Node 全部 PASS；后端 pytest 全绿（当前基线 83 passed）；前端 build 成功。

- [ ] **Step 3: 提交**

```bash
git add extension/README.md
git commit -m "docs: README 补充采集计数与手动停止说明"
```

- [ ] **Step 4: 真机验收清单（用户侧）**

1. 自己主页点「开始采集」→ 按钮变「采集中 N 条」，随滚动递增；
2. 中途点「停止」→ toast「已手动停止：成功 X 条…」，看板出现已采数据；
3. 采集 >100 条的主页（如之前 128 卡片）→ 停止/结束后 `video_ids.txt` 中该主页 id 全部存在（分批写入，不再整批被拒）；
4. 重复采集不重复追加 id（服务端去重不变）。
