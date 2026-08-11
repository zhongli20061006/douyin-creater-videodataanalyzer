# 抖音个人视频数据分析器（浏览器插件版）设计

日期：2026-08-11
状态：设计已获用户确认（本窗口确认「A/B 按推荐执行」+ 3 条补充建议已纳入），待用户审阅本文档
项目：douyinpachong（D:\DjangoProject\PythonProject11）

## 1. 背景与目标

现有项目是「抖音爬虫管理系统」（Scrapy + Redis + MySQL + FastAPI + Vue 3），
作者主页一键采集因平台风控不可用。本功能换一条合规路线：

博主在**自己的真实浏览器**里用浏览器插件采集**自己主页**的视频卡片数据，
后端只做「数据接收器」：校验字段 → 分类 → 按 video_id 去重 upsert 到现有 `video_info` 表；
看板复用现有 Vue 应用新增「个人分析」页做分析。爬虫（Scrapy/队列/Playwright）
不参与这条链路，但原项目本体保留不动。

已确认的产品决策（前序窗口拍板）：

1. 方向：浏览器插件版「个人视频数据分析器」，面向小博主采集自己主页视频数据做分析；
2. 数据来源：插件在博主真实浏览器运行（真实会话/指纹），从自己主页 DOM 提取视频卡片字段，
   可加网络 hook 兜底——绕开抖音自动化风控；
3. 架构：后端只做「数据接收器」；爬虫不参与这条路，但保留；
4. MVP 放当前仓库，用 `extension/` 独立目录 + 后端接收接口 + 看板「个人分析」页；
   验证成立后再评估拆独立仓库/抽公共库；
5. 合规边界必须设计进产品：只在当前登录账号自己的作者主页启用采集
   （来源白名单 + 校验 sec_user_id 是自己）、采集限速（一次上限约 100 条、自然翻页间隔）、
   README 如实说明「只能采自己的数据」；
6. 接收接口 MVP 就要带字段校验 + 按 video_id 去重（防垃圾/重复）；
   将来给第三方用再加令牌鉴权；
7. 采集字段：全量基础字段（video_id、video_title、video_desc、author_name、author_id、
   publish_time、like_count、comment_count、share_count、play_count、video_url、cover_url）。

本窗口新增的 4 条补充建议（已确认纳入）：

- 插件后端地址可配置，存入 `chrome.storage.local`，默认 `http://127.0.0.1:8001`，
  支持局域网/远端后端；
- DOM 提取逐字段容错：元素取不到记 null/0，不中断采集；
  结果展示「成功条数」与「字段缺失条数」，而不是「失败条数」；
- 看板显示「最近同步时间」（= `MAX(crawl_time)`），用户重复采集后可判断数据新旧。
- **分层工作流**：抖音自己主页的视频卡片直接显示**播放量**（而非点赞量），
  因此主页采集层先采 play_count 等卡片字段；用户点进自己的视频详情页后，
  详情页采集层被动提取点赞/评论/分享/发布时间/描述等详细数据并回补该 video_id。
  本地 `douyin_page.html` 样例已确认详情页存在 `data-e2e="detail-video-publish-time"`
  （绝对发布时间）、`video-player-digg`、`feed-comment-icon`、`video-player-share`
  等元素，分层方案有据可依。

## 2. 范围

### 本轮做（MVP）

- `extension/`：Chrome Manifest V3 插件（DOM 采集 + 配置页 + 容错统计）；
- 后端接收接口 `POST /api/extension/videos`（字段校验 + 去重 upsert）；
- 看板「个人分析」页（`PersonalAnalyzer.vue` + `GET /api/analyze/personal`）；
- README 更新（插件安装说明 + 合规声明 + 已知限制）。

### 本轮不做

- 网络 hook 兜底（观察页面已有接口响应补 play_count / publish_time）——列为验证后的下一阶段；
- 令牌鉴权（将来给第三方用再加）；
- Scrapy/队列/Playwright 参与此链路（原项目保留）；
- 数据库结构变更（零迁移、零改表）；
- 定时刷新、粘贴 ID 补数据、采集批次历史表（MVP 不引入新表）。

## 3. 架构与数据流

```text
博主浏览器（真实登录会话）
  自己主页 DOM（播放量等卡片字段）──┐
                                  ├─▶ 本地/局域网后端 :8001
  点击自己的视频详情页（点赞/评论/   │    POST /api/extension/videos
    分享/发布时间/描述）────────────┘    校验 → 批次内去重 → upsert
                                        ▼
                              video_info 表（现有表，零结构变更）
                                        ▼
                              看板「个人分析」页（Vue3 + ECharts）
```

插件只读已渲染的 DOM，不发额外采集请求；后端是唯一写入入口。

### 两层工作流

- **主页采集层**：博主在自己主页点「开始采集」后自动滚动翻页，
  提取卡片字段（video_id、标题、**播放量**、封面、作者信息），分批上报；
- **详情页采集层**：用户自然浏览时点开自己的视频详情页
  （`https://www.douyin.com/video/{video_id}`），插件被动提取该视频的
  点赞/评论/分享/发布时间/描述等详细数据，自动回补上报同一个 video_id；
- 两层共用同一个接收接口与 upsert 逻辑：主页先建行（play_count 有值、
  互动字段为空/0），详情页浏览后覆盖补充互动字段——数据逐步完善，不重复造记录。

## 4. 插件设计（extension/）

### 目录结构

```text
extension/
  manifest.json          # MV3：content_scripts 匹配 douyin.com；权限 storage、host_permissions
  content/
    parse.js             # 纯 DOM 解析：parseProfileCards()（主页卡片）+ parseVideoDetail()（详情页）
                         # （可在 Node 单测；无 chrome API 依赖）
    collect.js           # content script 入口：主页模式（白名单/按钮/滚动/上报）
                         # + 详情页模式（白名单/被动提取/防抖上报/结果提示）
  options/
    options.html         # 配置页：后端地址
    options.js           # 读写 chrome.storage.local
  README.md              # 插件安装、配置、合规说明
```

MVP 不制作图标资源（manifest 不声明 icons，Chrome 使用默认图标），
不在本轮引入 imagegen / 位图资产。

### manifest.json 要点

- `manifest_version: 3`；
- `content_scripts`: 匹配 `https://www.douyin.com/*`（具体激活由 collect.js 白名单判断）；
- `permissions`: `storage`；
- `host_permissions`: `https://www.douyin.com/*`、`http://127.0.0.1:8001/*`、
  `http://localhost:8001/*`（默认后端；局域网地址由用户在 options 页自行填写，
  插件使用 `matches` 之外的地址发请求时按浏览器 host 权限弹窗确认——README 说明，
  这是浏览器安全机制，不视为故障）。

### 身份白名单（合规边界，插件端强制）

- 只在 `https://www.douyin.com/user/{sec_uid}` 页面启用；
- 从页面获取「当前登录账号」的 sec_user_id（页面用户信息/DOM/已登录态），
  与 URL 中的 sec_uid 比对，不一致则**不显示采集按钮**并提示「只能采集自己主页的数据」；
- 兼容抖音页面结构变化：若无法从页面确认当前登录账号，默认不启用采集并给出提示。

详情页模式同样做白名单校验：详情页作者（页面作者链接中的 sec_uid）必须与
当前登录账号一致，才自动提取并上报；否则忽略该页（用户可能在浏览他人视频）。

### 采集流程（collect.js）

**主页模式：**

1. 读取 `chrome.storage.local` 的后端地址（默认 `http://127.0.0.1:8001`）；
2. 白名单校验通过后，在页面插入悬浮按钮「开始采集」；
3. 点击后自动滚动翻页：每次滚动后等待随机间隔 1.5–3 秒（自然翻页），
   累计去重采集上限 **100 条**后停止（页面上显示已停止原因）；
4. 每采集到一批新卡片即调用 `parseProfileCards()` 解析
   （video_id、video_title、play_count、cover_url、author 信息），随后分批
   `POST {后端地址}/api/extension/videos` 上报（每批 ≤ 100）；
5. 全部结束后在按钮旁展示结果：成功条数、字段缺失条数、被拒条数（原因）。

**详情页模式（被动，无需按钮）：**

1. 在 `https://www.douyin.com/video/{video_id}` 激活，做白名单校验（作者是自己）；
2. 调用 `parseVideoDetail()` 提取 video_id、publish_time（绝对时间）、
   like_count、comment_count、share_count、video_desc、video_url、cover_url 等；
3. 同一 video_id 60 秒内只上报一次（防抖，避免重复浏览反复请求）；
4. 上报成功后页面右下角显示轻提示「已同步该视频详情」；
5. 详情页不做自动滚动、不发起额外请求——完全跟随用户自然浏览节奏。

### 逐字段容错（parse.js + collect.js）

- `parse.js` 两个解析函数对每个字段独立 try/catch；单个元素取不到时该字段记为 `null`（字符串类）
  或 `0`（计数类），**不中断整条/整批采集**；
- 每条视频记录统计 `missing_fields: string[]`（字段名列表），
  主页模式与详情页模式分别汇总「字段缺失条数」展示给用户
  （主页层缺的是互动/发布时间字段，属预期；详情页浏览后会被补齐）；
- 单条记录若连 video_id 都取不到，标记为该条解析失败并跳过（计入被拒/跳过数）；
- 解析失败绝不把异常抛到采集主循环外。

### 配置页（options.html / options.js）

- 一个输入框：后端地址（默认 `http://127.0.0.1:8001`）+ 保存/恢复默认按钮；
- 保存到 `chrome.storage.local` 键 `backendBaseUrl`；保存成功即提示；
- collect.js 每次采集开始前读取该配置（不缓存旧值），并做简单地址规范化
  （去尾部 `/`，非 http(s) 开头自动补 `http://`）；
- README 说明局域网/远端用法及浏览器 host 权限弹窗。

## 5. 接收接口设计

### `POST /api/extension/videos`

请求体：

```json
{
  "source_url": "https://www.douyin.com/user/MS4wLjABAAAAxxxx",
  "videos": [
    {
      "video_id": "7638884656238410714",
      "video_title": "标题",
      "video_desc": "描述（可为空）",
      "author_name": "昵称",
      "author_id": "96104954318",
      "publish_time": "2026-05-12T14:13:52" ,
      "like_count": 55728,
      "comment_count": 4814,
      "share_count": 3859,
      "play_count": 0,
      "video_url": "https://www.douyin.com/video/7638884656238410714",
      "cover_url": "https://p3-sign.douyinpic.com/xxx.jpeg"
    }
  ]
}
```

响应：

```json
{
  "source_url": "https://www.douyin.com/user/MS4wLjABAAAAxxxx",
  "accepted": 3,
  "upserted": 3,
  "rejected": [
    { "video_id": "bad-id", "reason": "video_id 必须为 15-20 位数字" }
  ]
}
```

### 校验规则（服务端强制，全部在 `extension_receiver.py` 纯逻辑中）

| 字段 | 规则 |
| --- | --- |
| `source_url` | 必填；匹配 `https://www.douyin.com/user/<sec_uid>` 且 sec_uid 非空 |
| `videos` | 必填数组；长度 1–100 |
| `video_id` | 必填；15–20 位纯数字（与现有前端校验一致） |
| `video_title` | 可选；trim 后 ≤ 512 字符（表列 varchar(512)） |
| `video_desc` | 可选；≤ 5000 字符 |
| `author_name` | 可选；≤ 128 字符 |
| `author_id` | 可选；≤ 64 字符；**同一批次所有记录的 author_id 必须一致**（防混入他人数据） |
| `publish_time` | 可选；ISO 8601 或 `YYYY-MM-DD HH:MM:SS`，无效值按 null 处理 |
| `like_count` / `comment_count` / `share_count` / `play_count` | 可选；int ≥ 0，缺省 0，负数/非数字拒绝 |
| `video_url` | 可选；http(s) 链接 ≤ 2048 |
| `cover_url` | 可选；http(s) 链接 ≤ 1024 |

其它规则：

- 批次内按 `video_id` 去重（重复只保留第一条，不报 rejected，计入去重说明）；
- 入库 upsert 复用现有模式：
  `INSERT ... ON DUPLICATE KEY UPDATE`（video_id 唯一键），
  `crawl_time` 更新为当前时间（= 最近同步时间），`update_time` 由表自动更新；
- 全参数化 SQL，禁止拼接；
- 响应中 `accepted = 通过校验的唯一条数`，`upserted = 实际写库条数`；
- 校验失败的条目标记到 `rejected`（video_id + reason），整批仍继续处理合法条目；
- 不记录 Cookie/令牌/完整请求体到日志。

### 模块边界

- `extension_receiver.py`（项目根，与 `quality.py` 同模式）：纯函数
  `validate_batch(payload) -> (valid_records, rejected)`、
  `dedupe_records(records)`、字段规范化/类型转换，全部可单测；
- `api.py`：薄层——读请求体、调纯函数、参数化 upsert、返回响应；
- 不做令牌鉴权（MVP 决策 6），但批次上限、字段校验、去重是 MVP 就有的防线。

## 6. 看板「个人分析」页

### `GET /api/analyze/personal?author_id=xxx`

纯聚合逻辑放 `analyzer.py`（项目根），api.py 只做查询 + 调函数。

响应：

```json
{
  "author_id": "96104954318",
  "author_name": "平原公子",
  "summary": {
    "total_videos": 182,
    "total_likes": 1000000,
    "total_comments": 50000,
    "total_shares": 20000,
    "total_plays": 0,
    "latest_sync": "2026-08-10T17:07:59"
  },
  "trend": [ { "month": "2026-05", "count": 12 } ],
  "top_videos": [
    {
      "video_id": "7638884656238410714",
      "video_title": "标题",
      "like_count": 55728,
      "comment_count": 4814,
      "share_count": 3859,
      "publish_time": "2026-05-12T14:13:52",
      "crawl_time": "2026-08-10T17:07:59"
    }
  ]
}
```

聚合规则：

- `summary`：按 author_id 过滤后的总数与总和；`latest_sync = MAX(crawl_time)`
  （用户建议 3：重复采集后用户直接看到数据新旧）；
- `trend`：按 `publish_time` 的「年-月」分组计数，升序（publish_time 为空的不计入）；
- `top_videos`：按 `like_count` 降序取前 10；
- 查询不到该作者时返回空 summary + 空数组（前端显示空态），不报错。

### PersonalAnalyzer.vue

- 顶部：作者下拉（数据源 `SELECT author_id, author_name FROM video_info GROUP BY ...`，
  复用现有 `GET /api/stats/authors` 风格的新端点或复用其数据）；
- 概览卡（复用 `StatCard`）：视频数、总点赞、总评论、总分享、**最近同步时间**；
- 图表（复用 ECharts 组件模式）：月度发布趋势柱状图；互动对比（赞/评/享总数条形图）；
- Top 10 视频表（复用表格样式，含点赞/评论/分享/发布时间/同步时间）；
- 空态：提示「先去插件采集自己主页的数据」；加载/错误态与现有页面一致；
- 路由 `/personal` + 侧边栏「个人分析」入口（MainLayout menus + router）。

## 7. 合规与安全

### 插件端（产品内建）

- 只在当前登录账号自己的作者主页启用（来源白名单 + sec_user_id 一致性校验）；
- 采集限速（随机 1.5–3 秒自然翻页间隔）、单次上限 100 条；
- README 如实声明「只能采自己的数据」，不采集他人主页。

### 后端安全边界

| 接口 | 风险 | 规则 | 处理位置 | 验证方式 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `POST /api/extension/videos` | 垃圾/伪造数据入库 | 字段校验 + 批次上限 100 + author 一致性 | `extension_receiver.py` | TDD 单测 + 真库验证 | 计划内 |
| 同上 | 批量写入覆盖旧数据 | upsert 但 `crawl_time` 刷新为最近同步 | api.py 参数化 SQL | 真库 before/after | 计划内 |
| 同上 | SQL 注入 | 全参数化 SQL | api.py | 单测 + 代码审查 | 计划内 |
| 同上 | 敏感值泄露 | 日志不记录 Cookie/令牌/完整请求体 | api.py 日志 | 代码审查 | 计划内 |

未触碰的边界：登录/角色体系（本项目无用户体系）、第三方令牌、支付、公网部署。
「后端无法验证 sec_uid 是否为自己」是已知限制，由插件白名单 + README 声明承担
（MVP 决策 5 的合规边界主要在插件端强制）。

## 8. 测试策略（TDD）

### 后端（T2 严格 TDD）

- `tests/test_extension_receiver.py`：字段校验、批次上限、author 一致性、
  批次内去重、字段规范化/类型转换、rejected 原因——先写失败测试再实现；
- `tests/test_analyzer.py`：summary/trend/top_videos 聚合——先写失败测试再实现；
- 真库集成验证：自建 `ext_test_` 前缀测试行，走真实接口验证 upsert 与去重，
  验证后清理测试行（只清自建测试数据，不动用户数据）；
- 回归：现有 `tests/` 全量保持通过。

### 插件（parse.js 用 Node 内置测试，T2）

- `extension/tests/parse.test.mjs`：用 `node --test` 跑；
- fixture 分两组：
  - 主页卡片组：构造含播放量/标题/链接/封面的卡片 HTML 片段
    （含缺失字段、结构变化场景），断言 `parseProfileCards()` 字段提取、缺失统计、
    video_id 缺失时的跳过行为；
  - 详情页组：按本地 `douyin_page.html` 的元素结构（`detail-video-publish-time`、
    `video-player-digg`、`feed-comment-icon`、`video-player-share`）构造 fixture，
    断言 `parseVideoDetail()` 提取与回补行为；
- 真实翻页采集属 T3（真实站点交互），由用户在自己主页按验收清单执行
  （本机无法用真实抖音会话自动化验证，README 注明）。

### 前端

- `npm run build`（vue-tsc + vite build）通过；
- 接口真库验证：`GET /api/analyze/personal` 返回真实聚合；
- 浏览器截图/用户点击验收看板页。

## 9. 已知限制（如实标注到 README 与页面）

- **主页采集层只采到播放量等卡片字段**：点赞/评论/分享/发布时间/描述在主页卡片
  不可见，需用户点开自己的视频详情页后由详情页采集层回补；未浏览过详情页的视频，
  这些字段保持空/0（看板「最近同步时间」可帮助判断数据完整度）；
- 主页卡片字段随页面改版可能变化：取不到的字段按容错规则记 null/0 并计入缺失统计；
- `video_desc` / `video_url`：详情页不一定携带 → 取不到记 null；
- 局域网/远端后端地址需要浏览器 host 权限授权，README 说明；
- sec_user_id「是自己」的校验只能在插件端完成，后端无法复核。

## 10. 实施阶段

1. **接收器**：`extension_receiver.py` + `POST /api/extension/videos` + 单测 + 真库验证；
2. **插件**：`extension/` 全套（主页采集层 + 详情页采集层）+ Node 解析测试
   （两组 fixture）+ README；
3. **看板分析页**：`analyzer.py` + `GET /api/analyze/personal` + `PersonalAnalyzer.vue` +
   路由/菜单 + build 验证；
4. **收尾**：README 更新、全量回归、用户浏览器验收清单交付。

每个阶段独立验证（测试 + 真库/构建证据），完成后再进入下一阶段。
