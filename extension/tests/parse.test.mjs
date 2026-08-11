import { createRequire } from 'node:module'
import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const {
  parseCount,
  extractSecUidFromHref,
  parseProfileCards,
  parseVideoDetail,
} = require('../content/parse.js')

function domOf(html) {
  return new JSDOM(html)
}

const PROFILE_HTML = `
<div data-e2e="user-post-list"><ul>
  <li>
    <div><a href="/video/7672018085449279859?count=10&amp;secUid=MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl">
      <div class="GGxeUe0C">
        <div><img src="https://p3-pc-sign.douyinpic.com/coverA.jpeg?x-signature=abc" alt=""></div>
        <div class="jXmtohcJ"><span class="icon"></span><span class="BP1CQkLg">236</span></div>
        <p class="EB3BkdQ8">标题A</p>
      </div>
      <p class="frUrWD64">标题A</p>
    </a></div>
  </li>
  <li>
    <div><a href="/video/7672018085449279860?secUid=MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl">
      <div><img src="https://p3-pc-sign.douyinpic.com/coverB.jpeg" alt=""></div>
      <div class="jXmtohcJ"><span class="icon"></span><span>1.2万</span></div>
      <p class="frUrWD64">标题B</p>
    </a></div>
  </li>
  <li>
    <div><a href="/note/7647172401004949235">
      <div><img src="https://p3-pc-sign.douyinpic.com/coverC.jpeg" alt=""></div>
      <p class="frUrWD64">这是一篇图文</p>
    </a></div>
  </li>
</ul></div>
`

test('parseCount 支持纯数字/万/亿/千分位', () => {
  assert.equal(parseCount('236'), 236)
  assert.equal(parseCount('4.0万'), 40000)
  assert.equal(parseCount('1.2亿'), 120000000)
  assert.equal(parseCount('4,000'), 4000)
  assert.equal(parseCount('abc'), null)
  assert.equal(parseCount(null), null)
})

test('extractSecUidFromHref 提取作者 secUid', () => {
  assert.equal(
    extractSecUidFromHref('//www.douyin.com/user/MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI'),
    'MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI',
  )
  assert.equal(extractSecUidFromHref('/video/123'), '')
})

test('parseProfileCards 提取视频卡片字段', () => {
  const { document } = domOf(PROFILE_HTML).window
  const root = document.querySelector('[data-e2e="user-post-list"]')
  const cards = parseProfileCards(root, {
    author_name: '黑白阿巴巴',
    author_id: '4358913414407163',
  })
  assert.equal(cards.length, 2)
  assert.equal(cards[0].video_id, '7672018085449279859')
  assert.equal(cards[0].video_title, '标题A')
  assert.equal(cards[0].play_count, 236)
  assert.equal(cards[0].cover_url, 'https://p3-pc-sign.douyinpic.com/coverA.jpeg?x-signature=abc')
  assert.equal(cards[0].author_name, '黑白阿巴巴')
  assert.equal(cards[0].author_id, '4358913414407163')
  assert.equal(cards[0].sec_uid, 'MS4wLjABAAAA06jEnQt6n222TZfcskYj66Eae2cwa5P_-zn43ANyMO4-ozTFc8wQI4dpvCi2FEhl')
  assert.deepEqual(cards[0].missing_fields, [])
})

test('parseProfileCards 支持万格式并跳过图文', () => {
  const { document } = domOf(PROFILE_HTML).window
  const cards = parseProfileCards(document.querySelector('[data-e2e="user-post-list"]'), {})
  assert.equal(cards[1].play_count, 12000)
  assert.ok(!cards.some((c) => c.video_id === '7647172401004949235'))
})

test('parseProfileCards 统计缺失字段', () => {
  const html = `
  <div data-e2e="user-post-list"><ul>
    <li><div><a href="/video/7672018085449279899"><div><div class="jXmtohcJ"><span class="icon"></span><span></span></div></div></a></div></li>
  </ul></div>`
  const { document } = domOf(html).window
  const cards = parseProfileCards(document.querySelector('[data-e2e="user-post-list"]'), {})
  assert.equal(cards.length, 1)
  assert.ok(cards[0].missing_fields.includes('video_title'))
  assert.ok(cards[0].missing_fields.includes('play_count'))
})

const DETAIL_HTML = `
<div>
  <div data-e2e="feed-video" data-e2e-vid="7671480850864786742">
    <video poster="https://p3-sign.douyinpic.com/poster.jpeg?x-signature=def"></video>
  </div>
  <div data-e2e="video-desc"><span>第262集：标题</span><a href="//www.douyin.com/search/%E5%8E%86%E5%8F%B2?aweme_id=7671480850864786742">#历史</a></div>
  <a href="//www.douyin.com/user/MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI">@作者</a>
  <div data-e2e="video-player-digg"><div></div><div class="n1ekR9OB">4.0万</div></div>
  <div data-e2e="feed-comment-icon"><div></div><div class="cipURsys">481</div></div>
  <div data-e2e="video-player-share"><div></div><div class="mvwEat0w">1150</div></div>
</div>
`

test('parseVideoDetail 提取互动数据与作者 secUid', () => {
  const { document } = domOf(DETAIL_HTML).window
  const detail = parseVideoDetail(document)
  assert.equal(detail.video_id, '7671480850864786742')
  assert.equal(detail.like_count, 40000)
  assert.equal(detail.comment_count, 481)
  assert.equal(detail.share_count, 1150)
  assert.equal(detail.video_desc, '第262集：标题#历史')
  assert.equal(detail.video_url, 'https://www.douyin.com/video/7671480850864786742')
  assert.equal(detail.cover_url, 'https://p3-sign.douyinpic.com/poster.jpeg?x-signature=def')
  assert.equal(detail.author_sec_uid, 'MS4wLjABAAAATTGGMqqjAd_B2UP9s9ThMW5sj0J0Hw4XtLCytt0UOBI')
  assert.equal(detail.play_count, null)
  assert.equal(detail.publish_time, null)
})

test('parseVideoDetail 无 video_id 返回 null', () => {
  const { document } = domOf('<div></div>').window
  assert.equal(parseVideoDetail(document), null)
})
