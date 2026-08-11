# 后端鉴权与绑定加固 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端默认绑定 127.0.0.1、CORS 收紧白名单、扩展写接口令牌鉴权（fail-closed），扩展选项页支持配置令牌并携带 `X-API-Token` 上报。

**Architecture:** 纯逻辑（令牌校验、Origin 白名单、写守卫规则）放 `extension_receiver.py` 可单测；`api.py` 只做薄层依赖接线与 CORS/绑定配置；扩展侧 `options.js` 存令牌、`collect.js` 上报头；后端用 curl 实测端到端。

**Tech Stack:** FastAPI（无新依赖，TestClient 不可用）、pytest、Chrome MV3 vanilla JS + Node test runner + jsdom。

**Spec:** `docs/superpowers/specs/2026-08-11-backend-auth-bind-design.md`

---

### Task 1: 纯函数（extension_receiver.py，TDD）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_extension_receiver.py` 顶部 import 中追加：
```python
from extension_receiver import (
    MAX_BATCH,
    append_ids_file,
    build_upsert,
    dedupe_records,
    evaluate_write_guard,
    is_allowed_origin,
    is_valid_token,
    merge_ids,
    normalize_record,
    parse_count,
    parse_datetime,
    read_ids_file,
    validate_batch,
    validate_source_url,
    validate_video_id,
    write_ids_file,
)
```

在文件末尾追加：
```python
def test_is_valid_token():
    assert is_valid_token('abc', 'abc') is True
    assert is_valid_token('abc', 'abd') is False
    assert is_valid_token('', 'abc') is False
    assert is_valid_token('abc', '') is False
    assert is_valid_token(None, 'abc') is False


def test_is_allowed_origin():
    allowed = ['http://127.0.0.1:8001', 'http://localhost:8001', 'http://localhost:5173']
    assert is_allowed_origin('http://127.0.0.1:8001', allowed) is True
    assert is_allowed_origin('http://127.0.0.1:8001/', allowed) is True
    assert is_allowed_origin('HTTP://LOCALHOST:8001', allowed) is True
    assert is_allowed_origin('https://evil.com', allowed) is False
    assert is_allowed_origin(None, allowed) is False


def test_evaluate_write_guard_whitelist_origin():
    allowed = ['http://127.0.0.1:8001']
    ok, status, reason = evaluate_write_guard('http://127.0.0.1:8001', '', '', allowed)
    assert ok is True and status is None and reason is None


def test_evaluate_write_guard_fail_closed_when_token_unconfigured():
    allowed = ['http://127.0.0.1:8001']
    ok, status, reason = evaluate_write_guard('https://www.douyin.com', 'anything', '', allowed)
    assert ok is False and status == 503
    assert 'EXTENSION_API_TOKEN' in reason


def test_evaluate_write_guard_rejects_missing_token():
    allowed = ['http://127.0.0.1:8001']
    ok, status, reason = evaluate_write_guard('https://www.douyin.com', '', 'secret', allowed)
    assert ok is False and status == 403


def test_evaluate_write_guard_rejects_wrong_token():
    allowed = ['http://127.0.0.1:8001']
    ok, status, reason = evaluate_write_guard('https://www.douyin.com', 'bad', 'secret', allowed)
    assert ok is False and status == 401


def test_evaluate_write_guard_allows_valid_token():
    allowed = ['http://127.0.0.1:8001']
    ok, status, reason = evaluate_write_guard('https://www.douyin.com', 'secret', 'secret', allowed)
    assert ok is True and status is None and reason is None
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: FAIL（`ImportError: cannot import name 'is_valid_token' ...`）

- [ ] **Step 3: 最小实现**

在 `extension_receiver.py` 的 `validate_source_url` 之后追加：
```python
def is_valid_token(provided, expected) -> bool:
    """API 令牌校验；expected 为空一律视为未配置（fail-closed）。"""
    if not expected or not provided:
        return False
    return str(provided) == str(expected)


def is_allowed_origin(origin, allowed_origins) -> bool:
    """Origin 是否在白名单：去尾部斜杠、host 小写后比较。"""
    if not origin:
        return False
    normalized = str(origin).strip().rstrip('/')
    host = normalized.split('://')[-1].lower()
    for item in allowed_origins or []:
        item_norm = str(item).strip().rstrip('/')
        if item_norm == normalized:
            return True
        if item_norm.split('://')[-1].lower() == host:
            return True
    return False


def evaluate_write_guard(origin, provided_token, expected_token, allowed_origins) -> tuple:
    """写接口守卫：Origin 白名单或令牌通过。返回 (allowed, status_code, reason)。"""
    if is_allowed_origin(origin, allowed_origins):
        return True, None, None
    if not expected_token:
        return False, 503, '后端未配置 API 令牌（local_config.py 的 EXTENSION_API_TOKEN）'
    if not provided_token:
        return False, 403, '来源不被允许且未提供 API 令牌'
    if str(provided_token) != str(expected_token):
        return False, 401, 'API 令牌无效'
    return True, None, None
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交（待用户确认后统一执行，本步先跳过）**

---

### Task 2: api.py 守卫接线 + CORS 白名单 + 守卫测试

**Files:**
- Modify: `api.py`
- Create: `tests/test_api_guard.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_api_guard.py`：
```python
"""写接口守卫依赖：Origin 白名单或 X-API-Token；未配置令牌时 fail-closed。"""
import pytest
from fastapi import HTTPException

import api


@pytest.fixture(autouse=True)
def _configured_token(monkeypatch):
    monkeypatch.setattr(api, 'EXTENSION_API_TOKEN', 'test-token')
    yield


def _call_guard(origin, token):
    api.verify_write_guard(origin=origin, x_api_token=token)


def test_whitelist_origin_passes_without_token():
    _call_guard('http://127.0.0.1:8001', None)


def test_valid_token_passes_from_other_origin():
    _call_guard('https://www.douyin.com', 'test-token')


def test_missing_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', None)
    assert exc.value.status_code == 403


def test_wrong_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', 'bad')
    assert exc.value.status_code == 401


def test_fail_closed_when_token_unconfigured(monkeypatch):
    monkeypatch.setattr(api, 'EXTENSION_API_TOKEN', '')
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', 'test-token')
    assert exc.value.status_code == 503
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_guard.py -q`
Expected: FAIL（`AttributeError: module 'api' has no attribute 'verify_write_guard'`）

- [ ] **Step 3: 实现 api.py**

3.1 import 行改为：
```python
from fastapi import FastAPI, Query, HTTPException, Header, Depends
```

3.2 在 `VIDEO_IDS_PATH` 定义之后追加：
```python
try:
    from local_config import EXTENSION_API_TOKEN
except Exception:
    EXTENSION_API_TOKEN = ''

ALLOWED_ORIGINS = [
    'http://127.0.0.1:8001',
    'http://localhost:8001',
    'http://localhost:5173',
]
```

3.3 CORS 白名单改为：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
```

3.4 在 `def get_db():` 之前追加守卫依赖：
```python
def verify_write_guard(
    origin: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None, alias='X-API-Token'),
) -> None:
    """写接口守卫：Origin 白名单或 X-API-Token 通过；未配置令牌时 fail-closed。"""
    allowed, status_code, reason = extension_receiver.evaluate_write_guard(
        origin, x_api_token, EXTENSION_API_TOKEN, ALLOWED_ORIGINS,
    )
    if not allowed:
        raise HTTPException(status_code=status_code, detail=reason)
```

3.5 给下列 10 处路由装饰器追加 `dependencies=[Depends(verify_write_guard)]`，逐一改为（保留原参数）：
```python
@app.post('/api/crawl', response_model=CrawlResponse, dependencies=[Depends(verify_write_guard)])
@app.delete('/api/videos/{video_id}', dependencies=[Depends(verify_write_guard)])
@app.post('/api/spider/start', dependencies=[Depends(verify_write_guard)])
@app.post('/api/spider/stop', dependencies=[Depends(verify_write_guard)])
@app.post('/api/collect/author', dependencies=[Depends(verify_write_guard)])
@app.post('/api/quality/fix', dependencies=[Depends(verify_write_guard)])
@app.post('/api/quality/delete', dependencies=[Depends(verify_write_guard)])
@app.post('/api/extension/videos', dependencies=[Depends(verify_write_guard)])
@app.post('/api/extension/ids', dependencies=[Depends(verify_write_guard)])
@app.put('/api/extension/ids', dependencies=[Depends(verify_write_guard)])
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_guard.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 原 83 条 + 新增全部 PASS。

---

### Task 3: 扩展选项页令牌 + collect.js 上报头

**Files:**
- Modify: `extension/options/options.html`
- Modify: `extension/options/options.js`
- Modify: `extension/content/collect.js`
- Modify: `extension/tests/collect.smoke.test.mjs`
- Create: `extension/tests/options.smoke.test.mjs`

- [ ] **Step 1: 写失败测试**

1.1 修改 `extension/tests/collect.smoke.test.mjs`：
- 存储 mock 增加 `apiToken: 'test-token',`；
- `window.fetch` 改为记录 url 与 headers：
```js
  window.fetch = async (url, opts = {}) => {
    calls.push({ url: String(url), headers: (opts && opts.headers) || {} })
    if (String(url).includes('/api/extension/ids')) {
      return { ok: true, json: async () => ({ added: 0, total: 2 }) }
    }
    return { ok: true, json: async () => ({ accepted: 1, upserted: 1, rejected: [] }) }
  }
```
- 断言追加（在现有 `calls.some(...)` 两行之后）：
```js
    const videoCall = calls.find((c) => c.url.includes('/api/extension/videos'))
    assert.ok(videoCall, '应有 /api/extension/videos 调用')
    assert.equal(videoCall.headers['X-API-Token'], 'test-token')
    const idsCall = calls.find((c) => c.url.includes('/api/extension/ids'))
    assert.ok(idsCall, '应有 /api/extension/ids 调用')
    assert.equal(idsCall.headers['X-API-Token'], 'test-token')
```
并把原有 `calls.some((u) => u.includes(...))` 改为 `calls.some((c) => c.url.includes(...))`。

1.2 新建 `extension/tests/options.smoke.test.mjs`：
```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JSDOM } from 'jsdom'

const optionsHtml = readFileSync(new URL('../options/options.html', import.meta.url), 'utf-8')
const optionsJs = readFileSync(new URL('../options/options.js', import.meta.url), 'utf-8')

function createPage() {
  const dom = new JSDOM(optionsHtml, {
    runScripts: 'outside-only',
    url: 'chrome-extension://abc/options.html',
  })
  const { window } = dom
  const store = {}
  window.chrome = {
    storage: {
      local: {
        get: (keys) => Promise.resolve(Object.fromEntries(keys.map((k) => [k, store[k]]))),
        set: (obj) => Promise.resolve(Object.assign(store, obj)),
      },
    },
  }
  window.eval(optionsJs)
  return { window, store }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

test('选项页保存包含 API 令牌', async () => {
  const { window, store } = createPage()
  window.document.getElementById('token').value = 'my-secret-token'
  window.document.getElementById('backend').value = 'http://127.0.0.1:8001'
  window.document.getElementById('save').click()
  await flush()
  assert.equal(store.apiToken, 'my-secret-token')
})

test('选项页重置清空 API 令牌', async () => {
  const { window, store } = createPage()
  store.apiToken = 'old-token'
  window.document.getElementById('reset').click()
  await flush()
  assert.equal(store.apiToken, '')
})
```

- [ ] **Step 2: 运行确认 RED**

Run（在 `extension/` 目录）: `node --test tests/collect.smoke.test.mjs tests/options.smoke.test.mjs`
Expected: FAIL（`X-API-Token` 为 undefined / `getElementById('token')` 为 null）

- [ ] **Step 3: 实现选项页与 collect.js**

3.1 `options.html` 在采集模式 row 之后追加：
```html
  <div class="row">
    <label for="token">API 令牌</label>
    <input id="token" type="text" placeholder="与 local_config.py 的 EXTENSION_API_TOKEN 一致" />
    <div class="hint">后端已启用鉴权：令牌不匹配或未配置时采集上报会被拒绝。</div>
  </div>
```

3.2 `options.js` 全文替换为：
```js
const KEY = 'backendBaseUrl'
const MODE_KEY = 'complianceMode'
const TOKEN_KEY = 'apiToken'
const DEFAULT = 'http://127.0.0.1:8001'
const input = document.getElementById('backend')
const modeSel = document.getElementById('mode')
const tokenInput = document.getElementById('token')
const statusEl = document.getElementById('status')

chrome.storage.local.get([KEY, MODE_KEY, TOKEN_KEY]).then((data) => {
  input.value = data[KEY] || DEFAULT
  modeSel.value = data[MODE_KEY] || 'unlimited'
  tokenInput.value = data[TOKEN_KEY] || ''
})

function normalize(value) {
  let v = String(value || '').trim().replace(/\/+$/, '')
  if (v && !/^https?:\/\//i.test(v)) v = 'http://' + v
  return v || DEFAULT
}

document.getElementById('save').addEventListener('click', () => {
  const value = normalize(input.value)
  chrome.storage.local.set({
    [KEY]: value,
    [MODE_KEY]: modeSel.value,
    [TOKEN_KEY]: tokenInput.value.trim(),
  }).then(() => {
    input.value = value
    statusEl.textContent = '已保存：' + value
    setTimeout(() => { statusEl.textContent = '' }, 2500)
  })
})

document.getElementById('reset').addEventListener('click', () => {
  input.value = DEFAULT
  modeSel.value = 'unlimited'
  tokenInput.value = ''
  chrome.storage.local.set({ [KEY]: DEFAULT, [MODE_KEY]: 'unlimited', [TOKEN_KEY]: '' })
  statusEl.textContent = '已恢复默认'
  setTimeout(() => { statusEl.textContent = '' }, 2500)
})
```

3.3 `collect.js`：
- 常量区追加 `const KEY_TOKEN = 'apiToken';`
- `getConfig()` 中 `storageGet` 键数组与返回值追加 `KEY_TOKEN` / `apiToken: data[KEY_TOKEN] || ''`；
- `reportIds()` 请求头改为：
```js
      headers: { 'Content-Type': 'application/json', 'X-API-Token': cfg.apiToken },
```
- `report()` 请求头改为：
```js
      headers: { 'Content-Type': 'application/json', 'X-API-Token': cfg.apiToken },
```
- 两个函数的 `if (!resp.ok)` 分支在 throw 前追加：
```js
      if (resp.status === 401 || resp.status === 403 || resp.status === 503) {
        detail = '后端拒绝了请求：请检查 API 令牌配置（选项页与 local_config.py 一致）。' +
          (detail ? ' ' + detail : '')
      }
```

- [ ] **Step 4: 运行确认 GREEN**

Run（在 `extension/` 目录）: `node --test tests/collect.smoke.test.mjs tests/options.smoke.test.mjs`
Expected: 全部 PASS。

- [ ] **Step 5: 全量扩展测试回归**

Run（在 `extension/` 目录）: `node --test`
Expected: 原 18 条 + 新增 2 条全部 PASS。

---

### Task 4: 启动脚本 / 示例配置 / README

**Files:**
- Modify: `run_backend.ps1`
- Modify: `start_server.py`
- Modify: `local_config.example.py`
- Modify: `README.md`
- Modify: `extension/README.md`

- [ ] **Step 1: 绑定 127.0.0.1**

`run_backend.ps1`：`"-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "$Port"` 改为
`"-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "$Port"`。

`start_server.py`：`def start_api(host='0.0.0.0', port=8000, reload=False)` 改为 `host='127.0.0.1'`；
`parser.add_argument('--host', default='0.0.0.0', ...)` 改为 `default='127.0.0.1'`。

- [ ] **Step 2: 示例配置**

`local_config.example.py` 末尾追加：
```python
# 扩展写接口鉴权令牌（extension 选项页需填写同一令牌）
# 留空 = fail-closed：扩展上报会被后端拒绝（503）
EXTENSION_API_TOKEN = '请设置一段随机字符串'
```

- [ ] **Step 3: README**

项目 `README.md` 追加「后端安全」小节（内容见下）：
```markdown
## 后端安全
- 默认仅绑定 127.0.0.1（`run_backend.ps1` / `start_server.py` 可传 `--host` 覆盖，用于将来需要时手动开放局域网）；
- 扩展写接口（`/api/extension/*`、爬虫/队列控制、质量修复/删除、删除视频）鉴权规则：
  Origin 在本机白名单（127.0.0.1/localhost:8001、localhost:5173）或请求头 `X-API-Token` 匹配 `local_config.py` 的 `EXTENSION_API_TOKEN`；
- 令牌未配置时扩展上报一律拒绝（fail-closed，返回 503 并提示）；扩展选项页需填写同一令牌；
- 已知边界：读接口不校验令牌，靠 CORS 白名单兜底；令牌以明文存于本机 `local_config.py` 与浏览器存储，请勿外传。
```

`extension/README.md` 追加：
```markdown
### API 令牌
后端启用鉴权后，在选项页填写与后端 `local_config.py` 中 `EXTENSION_API_TOKEN` 一致的令牌；
未配置或令牌不匹配时采集上报会被后端拒绝（fail-closed），请检查两侧配置。
```

- [ ] **Step 4: 验证文档改动**

Run: `git -c safe.directory=D:/DjangoProject/PythonProject11 diff --stat`
Expected: 显示上述文件改动。

---

### Task 5: 全量回归

- [ ] **Step 1: 后端**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS（原 83 + 新增 12）。

- [ ] **Step 2: 扩展**

Run（在 `extension/` 目录）: `node --test`
Expected: 全部 PASS（原 18 + 新增 2）。

- [ ] **Step 3: 前端**

Run（在 `frontend/` 目录）: `npm run build`
Expected: 构建成功（chunk 大小警告为既有提示）。

---

### Task 6: 重启后端 + curl 实测（需用户确认）

- [ ] **Step 1: 用户确认后停止旧后端并重启**

Run: `.\stop_backend.ps1` 后 `.\run_backend.ps1`（或按用户指定方式）。
Expected: 日志显示 `http://127.0.0.1:8001`。

- [ ] **Step 2: curl 正/负路径（不写库、不改文件）**

说明：正路径用「守卫放行但业务校验拒绝 400」证明守卫通过，避免向 `video_ids.txt` 或 `video_info` 写入测试数据；
负路径用守卫直接返回的 403/401/503 证明拦截。

```powershell
$payload = '{"source_url":"https://www.douyin.com/user/MS4wLjABAAAA_test","videos":[]}'
# 负路径1：无令牌 + 非白名单 Origin → 403
$r1 = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8001/api/extension/videos' -Headers @{Origin='https://evil.com'} -ContentType 'application/json' -Body $payload -SkipHttpErrorCheck
$r1.StatusCode   # 预期 403
# 负路径2：错令牌 → 401
$r2 = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8001/api/extension/videos' -Headers @{'X-API-Token'='wrong-token'} -ContentType 'application/json' -Body $payload -SkipHttpErrorCheck
$r2.StatusCode   # 预期 401
# 负路径3：未配置令牌（如本地未填）→ 503；已配置则跳过
# 正路径：带正确令牌 → 守卫放行，业务校验拒绝 → 400
$token = (Get-Content local_config.py | Select-String 'EXTENSION_API_TOKEN\s*=\s*['"']([^'"']+)['"']').Matches[0].Groups[1].Value
$r3 = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8001/api/extension/videos' -Headers @{'X-API-Token'=$token} -ContentType 'application/json' -Body $payload -SkipHttpErrorCheck
$r3.StatusCode   # 预期 400（守卫已放行）
# 正路径2：白名单 Origin（模拟看板前端同源写操作）→ 同样 400
$r4 = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8001/api/extension/videos' -Headers @{Origin='http://127.0.0.1:8001'} -ContentType 'application/json' -Body $payload -SkipHttpErrorCheck
$r4.StatusCode   # 预期 400
```
Expected: 负路径 403/401，正路径 400（业务校验拒绝，说明守卫放行），且 `video_ids.txt` 行数不变、库无新增测试行。

- [ ] **Step 3: 看板冒烟**

浏览器打开 `http://127.0.0.1:8001` 确认页面可访问、收集页编辑保存正常（同源 Origin 放行）。

---

### Task 7: 提交（需用户确认）

- [ ] **Step 1: 确认后提交**

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add docs/superpowers/specs/2026-08-11-backend-auth-bind-design.md docs/superpowers/plans/2026-08-11-backend-auth-bind.md extension_receiver.py api.py tests/test_extension_receiver.py tests/test_api_guard.py extension/options/options.html extension/options/options.js extension/content/collect.js extension/tests/collect.smoke.test.mjs extension/tests/options.smoke.test.mjs run_backend.ps1 start_server.py local_config.example.py README.md extension/README.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 后端绑定 127.0.0.1 + 扩展写接口令牌鉴权（fail-closed）"
```

- [ ] **Step 2: 检查未跟踪文件**

确认 `Codex Image ...png` 未入库；`local_config.py` 未入库。
