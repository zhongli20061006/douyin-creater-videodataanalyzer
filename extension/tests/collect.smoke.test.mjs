import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JSDOM, VirtualConsole } from 'jsdom'

const parseSrc = readFileSync(new URL('../content/parse.js', import.meta.url), 'utf-8')
const collectSrc = readFileSync(new URL('../content/collect.js', import.meta.url), 'utf-8')

// jsdom 25 + Node 24 下，MutationObserver 回调会被延迟上报一个虚假的 jsdomError
// （回调体实际正常执行，断言不受影响）。这里过滤该噪音，保持测试输出干净。
const virtualConsole = new VirtualConsole()
virtualConsole.on('jsdomError', () => {})

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
    virtualConsole,
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
          apiToken: 'test-token',
        }),
        set: (_obj, cb) => { if (cb) cb() },
      },
    },
  }
  const calls = []
  window.fetch = async (url, opts = {}) => {
    calls.push({ url: String(url), headers: (opts && opts.headers) || {} })
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
    assert.ok(calls.some((c) => c.url.includes('/api/extension/videos')))
    assert.ok(calls.some((c) => c.url.includes('/api/extension/ids')))
    const videoCall = calls.find((c) => c.url.includes('/api/extension/videos'))
    assert.ok(videoCall, '应有 /api/extension/videos 调用')
    assert.equal(videoCall.headers['X-API-Token'], 'test-token')
    const idsCall = calls.find((c) => c.url.includes('/api/extension/ids'))
    assert.ok(idsCall, '应有 /api/extension/ids 调用')
    assert.equal(idsCall.headers['X-API-Token'], 'test-token')

    // 采集结束按钮复位
    assert.ok(await waitFor(() => mainBtn.textContent === '开始采集'))
  } finally {
    dom.window.close()
  }
})
