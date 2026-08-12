# 插件上报改走 background service worker 转发 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 background service worker 转发插件上报请求，绕开 content script 的页面 CORS 限制，保持后端与 CORS 白名单不变。

**Architecture:** `background.js` 只做 fetch 转发（受 host_permissions 支持）；`collect.js` 的 `report`/`reportIds` 改走 `chrome.runtime.sendMessage`；smoke 测试同步改造。

**Tech Stack:** Chrome MV3 vanilla JS + Node test runner + jsdom。

**Spec:** `docs/superpowers/specs/2026-08-12-extension-background-relay-design.md`

---

### Task 1: background.js + 冒烟测试（TDD）

**Files:**
- Create: `extension/background.js`
- Create: `extension/tests/background.smoke.test.mjs`

- [ ] **Step 1: 写失败测试**

新建 `extension/tests/background.smoke.test.mjs`：
```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JSDOM } from 'jsdom'

const backgroundSrc = readFileSync(new URL('../background.js', import.meta.url), 'utf-8')

function createContext() {
  const dom = new JSDOM('', { runScripts: 'outside-only', url: 'chrome-extension://abc/background.html' })
  const { window } = dom
  let listener = null
  const fetchCalls = []
  window.chrome = {
    runtime: {
      onMessage: {
        addListener: (fn) => { listener = fn },
      },
    },
  }
  window.fetch = async (url, opts = {}) => {
    fetchCalls.push({ url: String(url), opts })
    return { status: 200, text: async () => '{"ok":true}' }
  }
  window.eval(backgroundSrc)
  return { window, getListener: () => listener, fetchCalls }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

test('background 收到请求消息后转发 fetch 并回传响应', async () => {
  const { getListener, fetchCalls } = createContext()
  const listener = getListener()
  assert.ok(listener, 'background.js 应注册 onMessage listener')
  let response = null
  const sendResponse = (r) => { response = r }
  const ret = listener(
    {
      type: 'dy-analyzer-request',
      url: 'http://127.0.0.1:8001/api/extension/videos',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Token': 'token-x' },
      body: '{"videos":[]}',
    },
    {},
    sendResponse,
  )
  assert.equal(ret, true, 'async listener 应返回 true 保持通道')
  await flush()
  assert.equal(fetchCalls.length, 1)
  assert.equal(fetchCalls[0].url, 'http://127.0.0.1:8001/api/extension/videos')
  assert.equal(fetchCalls[0].opts.method, 'POST')
  assert.equal(fetchCalls[0].opts.headers['X-API-Token'], 'token-x')
  assert.equal(fetchCalls[0].opts.body, '{"videos":[]}')
  assert.deepEqual(response, { ok: true, status: 200, bodyText: '{"ok":true}' })
})

test('background 转发失败时回传 ok:false', async () => {
  const ctx = createContext()
  ctx.window.fetch = async () => { throw new Error('network down') }
  let response = null
  const sendResponse = (r) => { response = r }
  ctx.getListener()(
    { type: 'dy-analyzer-request', url: 'http://127.0.0.1:8001/x', method: 'POST', headers: {}, body: '{}' },
    {},
    sendResponse,
  )
  await flush()
  assert.deepEqual(response, { ok: false, error: 'network down' })
})
```

- [ ] **Step 2: 运行确认 RED**

Run（`extension/`）: `node --test tests/background.smoke.test.mjs`
Expected: FAIL（`background.js` 不存在 / 未注册 listener）。

- [ ] **Step 3: 实现 background.js**

新建 `extension/background.js`：
```js
/* 抖音个人视频数据分析器 — background service worker
 * 只做一件事：把 content script 的上报请求转发到本地后端。
 * 扩展上下文 fetch 凭 host_permissions 跨域，不受页面 CORS 限制；不改动请求内容。
 */
'use strict';

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== 'dy-analyzer-request') return;
  (async () => {
    try {
      const resp = await fetch(message.url, {
        method: message.method || 'POST',
        headers: message.headers || {},
        body: message.body,
      });
      sendResponse({ ok: true, status: resp.status, bodyText: await resp.text() });
    } catch (e) {
      sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
    }
  })();
  return true;
});
```

- [ ] **Step 4: 运行确认 GREEN**

Run（`extension/`）: `node --test tests/background.smoke.test.mjs`
Expected: 全部 PASS。

---

### Task 2: collect.js requestBackend + smoke 改造（TDD）

**Files:**
- Modify: `extension/content/collect.js`
- Modify: `extension/tests/collect.smoke.test.mjs`

- [ ] **Step 1: 写失败测试**

`extension/tests/collect.smoke.test.mjs` 的 `createPage` 改造：
- `window.chrome.storage` 保留；新增 `window.chrome.runtime.sendMessage` mock：
```js
  const messages = []
  window.chrome.runtime = {
    sendMessage: async (msg) => {
      messages.push(msg)
      if (String(msg.url).includes('/api/extension/ids')) {
        return { ok: true, status: 200, bodyText: JSON.stringify({ added: 0, total: 2 }) }
      }
      return { ok: true, status: 200, bodyText: JSON.stringify({ accepted: 1, upserted: 1, rejected: [] }) }
    },
  }
```
- 删除 `window.fetch` mock（不再走 fetch）；
- 返回对象增加 `messages`；
- 断言部分（替换原 fetch 相关断言）：
```js
    const videoMsg = messages.find((m) => m.url.includes('/api/extension/videos'))
    assert.ok(videoMsg, '应有 /api/extension/videos 上报消息')
    assert.equal(videoMsg.method, 'POST')
    assert.equal(videoMsg.headers['X-API-Token'], 'test-token')
    const idsMsg = messages.find((m) => m.url.includes('/api/extension/ids'))
    assert.ok(idsMsg, '应有 /api/extension/ids 上报消息')
    assert.equal(idsMsg.headers['X-API-Token'], 'test-token')
```

- [ ] **Step 2: 运行确认 RED**

Run（`extension/`）: `node --test tests/collect.smoke.test.mjs`
Expected: FAIL（当前走 `window.fetch`，无 `messages` / 无 sendMessage 调用）。

- [ ] **Step 3: 实现 collect.js**

3.1 在 `reportIds` 之前新增 `requestBackend`：
```js
  async function requestBackend(url, method, payload) {
    const cfg = await getConfig();
    const resp = await chrome.runtime.sendMessage({
      type: 'dy-analyzer-request',
      url: url,
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-API-Token': cfg.apiToken },
      body: JSON.stringify(payload),
    });
    if (!resp || !resp.ok) {
      throw new Error(resp && resp.error ? resp.error : '请求失败');
    }
    return { status: resp.status, text: resp.bodyText };
  }
```

3.2 `reportIds` 替换为：
```js
  async function reportIds(videoIds, authorId) {
    const cfg = await getConfig();
    const resp = await requestBackend(cfg.backendBaseUrl + '/api/extension/ids', 'POST', {
      video_ids: videoIds,
      author_id: authorId,
    });
    if (resp.status < 200 || resp.status >= 300) {
      let detail = 'HTTP ' + resp.status;
      try {
        const err = JSON.parse(resp.text);
        detail = err.detail || detail;
      } catch (e) { /* ignore */ }
      if (resp.status === 401 || resp.status === 403 || resp.status === 503) {
        detail = '后端拒绝了请求：请检查 API 令牌配置（选项页与 local_config.py 一致）。' +
          (detail ? ' ' + detail : '');
      }
      throw new Error(detail);
    }
    return JSON.parse(resp.text);
  }
```

3.3 `report` 替换为：
```js
  async function report(videos, sourceUrl) {
    const cfg = await getConfig();
    const resp = await requestBackend(cfg.backendBaseUrl + '/api/extension/videos', 'POST', {
      source_url: sourceUrl,
      videos: videos,
    });
    if (resp.status < 200 || resp.status >= 300) {
      let detail = 'HTTP ' + resp.status;
      try {
        const err = JSON.parse(resp.text);
        detail = err.detail || detail;
      } catch (e) { /* ignore */ }
      if (resp.status === 401 || resp.status === 403 || resp.status === 503) {
        detail = '后端拒绝了请求：请检查 API 令牌配置（选项页与 local_config.py 一致）。' +
          (detail ? ' ' + detail : '');
      }
      throw new Error(detail);
    }
    return JSON.parse(resp.text);
  }
```

- [ ] **Step 4: 运行确认 GREEN**

Run（`extension/`）: `node --test tests/collect.smoke.test.mjs`
Expected: 全部 PASS。

---

### Task 3: manifest.json 接线

**Files:**
- Modify: `extension/manifest.json`

- [ ] **Step 1: 加 background**

在 `"permissions": ["storage"],` 之后追加：
```json
  "background": {
    "service_worker": "background.js"
  },
```

- [ ] **Step 2: 全量扩展测试**

Run（`extension/`）: `node --test`
Expected: 全部 PASS（原 20 + 新增 background 2）。

---

### Task 4: 回归 + README

**Files:**
- Modify: `extension/README.md`

- [ ] **Step 1: README 补充**

在「API 令牌」小节后追加：
```markdown
### 上报机制
插件上报请求经 background service worker 转发到后端，不受页面 CORS 限制；
后端仍按 `X-API-Token` 校验（fail-closed），选项页需与 `local_config.py` 配置一致。
```

- [ ] **Step 2: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 103 passed；
Run（`extension/`）: `node --test` → 全部 PASS；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）+ 真机验证

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension/background.js extension/manifest.json extension/content/collect.js extension/tests/background.smoke.test.mjs extension/tests/collect.smoke.test.mjs extension/README.md docs/superpowers/specs/2026-08-12-extension-background-relay-design.md docs/superpowers/plans/2026-08-12-extension-background-relay.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "fix: 插件上报改走 background service worker，修复 CORS 预检拦截"
```

真机：`chrome://extensions` 重新加载插件 → 采集 → 数据入库、id 带作者落盘。
