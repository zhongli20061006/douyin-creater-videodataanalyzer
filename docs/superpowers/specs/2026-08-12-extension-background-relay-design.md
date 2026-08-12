# 插件上报改走 background service worker 转发（CORS 修复）设计

日期：2026-08-12
状态：用户已确认（方向 B：SW 转发，保持 CORS 白名单收紧）。

## 1. 背景与问题（真机证据）

P1 将 CORS 收紧为本机白名单后，插件 content script 从 `https://www.douyin.com` 页面发起的上报请求被浏览器预检拦截：
```
Access to fetch at 'http://127.0.0.1:8001/api/extension/videos' from origin
'https://www.douyin.com' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present ...
```

根因：**MV3 content script 的 fetch 仍受页面 CORS 限制**；只有 background service worker 的 fetch 能凭
`host_permissions` 跨域（扩展上下文）。P1 时假设「host_permissions 可绕过 CORS」不适用于 content script，
属设计疏漏；请求未到达后端，采集数据未入库。

## 2. 目标

- 上报请求改由 background service worker（SW）转发，绕开页面 CORS；
- CORS 白名单保持收紧不动；后端与令牌守卫不改；
- 主页采集 / 详情页被动同步 / ids 批内上报三条路径语义零变化。

## 3. 实现设计

### 3.1 文件改动（仅 4 个）

| 文件 | 动作 |
| --- | --- |
| `extension/manifest.json` | 新增 `"background": {"service_worker": "background.js"}`，其余不动 |
| `extension/background.js` | 新建：监听 `chrome.runtime.onMessage`，转发 `dy-analyzer-request` 消息为 fetch，只读不改内容 |
| `extension/content/collect.js` | `report` / `reportIds` 改走新增 `requestBackend`（sendMessage → SW），错误处理语义保留 |
| `extension/tests/*` | smoke 测试改造/新增（见测试策略） |

### 3.2 消息协议

```
content → SW:
{ type: 'dy-analyzer-request', url, method, headers, body }

SW → content（sendResponse）:
{ ok: true, status: 200, bodyText: '...' }
{ ok: false, error: 'Failed to fetch' }
```

- SW 用 async listener + `return true` 保持通道；
- content 端 `JSON.parse(bodyText)` 后沿用现有 `res.accepted / res.upserted / idsRes.added` 逻辑；
- 非 2xx：解析 bodyText 的 `detail`，401/403/503 拼接「请检查 API 令牌配置」提示（与现有一致）。

### 3.3 collect.js requestBackend

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

### 3.4 模块影响矩阵（不破坏）

| 模块 | 影响 |
| --- | --- |
| `hook.js`（MAIN world）、`parse.js`、`options.html/js` | 不动 |
| 后端 API / CORS / 令牌守卫 | 不改；SW 请求凭 `X-API-Token` 通过守卫 |
| 主页采集 / 详情被动 / ids 上报 | 三条路径都走 requestBackend，语义不变 |
| 停止/计数/toast/错误兜底 | 不动 |

## 4. 测试策略（T2 严格 TDD）

- `extension/tests/background.smoke.test.mjs`（新建）：eval background.js，mock `chrome.runtime.onMessage` 与 `fetch`，
  触发 listener，断言 fetch 收到正确 url/method/headers/body，sendResponse 返回 `{ok,status,bodyText}`；
- `extension/tests/collect.smoke.test.mjs`（改造）：mock `chrome.runtime.sendMessage`，断言上报消息含
  `X-API-Token` 头与正确 body；覆盖 SW 返回非 2xx → 报错提示路径；
- 回归：`node --test`、`pytest -q`、`npm run build`（后两者确认无连带破坏）；
- 真机：用户重载插件 → 采集 → 数据入库、id 带作者落盘、看板可见。

## 5. 非目标

- 不改后端、不改 CORS 白名单、不改 options 配置项；
- 不做消息加密/签名（本机 http 已有令牌）；
- 不重构 collect.js 其余逻辑。

## 6. 文件结构

| 文件 | 动作 |
| --- | --- |
| `extension/background.js` | 新建 |
| `extension/manifest.json` | 加 background |
| `extension/content/collect.js` | requestBackend + report/reportIds 改造 |
| `extension/tests/background.smoke.test.mjs` | 新建 |
| `extension/tests/collect.smoke.test.mjs` | 改造 |
| `docs/superpowers/specs/2026-08-12-extension-background-relay-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-extension-background-relay.md` | 实施计划 |

## 7. 实施阶段

1. background.js + smoke（RED → GREEN）；
2. collect.js requestBackend + smoke 改造（RED → GREEN）；
3. manifest.json 接线；
4. 全量回归 + README 轻量说明；
5. 用户确认后提交；真机重载插件采集验证。
