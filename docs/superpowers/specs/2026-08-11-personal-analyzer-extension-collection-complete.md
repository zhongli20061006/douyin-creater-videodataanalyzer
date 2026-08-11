# 抖音个人视频数据分析器 - 采集完善设计（主页全量翻页 + 网络 hook + video_id 保留）

日期：2026-08-11
状态：待用户审阅（两个决策点采用推荐方案，备选已列明被拒理由）
前置设计：`docs/superpowers/specs/2026-08-11-personal-analyzer-extension-design.md`（MVP 基线，本设计为其采集链路的完善修订）

## 1. 背景与问题

真实使用中发现三个问题：

1. **主页采集不全**：自己主页 58 个视频，插件只采到 39 条。
   根因：抖音主页作品列表是懒加载，滚动容器不是 `window`，插件用窗口滚动无法触发加载更多，
   连续 3 轮无新卡片即停止；
2. **详情数据靠手动浏览**：点赞/评论/分享需要逐个打开视频详情页被动同步，量大、费时；
3. **部分视频播放量为空**：只有详情同步记录（点赞/评论/分享有值）而主页采集未覆盖的视频，
   `play_count` 为空（详情页不显示播放量，同步时未伪造）。

另需将采集到的 video_id 保留下来，供现有爬虫后续刷新数据。

## 2. 目标（本轮做）

- 主页自动翻页，确保 100 条以内的全部视频一次性采全（播放量必达）；
- 详情信息自动化：**被动网络 hook** 观察主页作品列表接口响应，
  一次拿到全部字段（play_count / like / comment / share / publish_time / cover / author）；
- 采集完成后把 video_id 追加写入 `video_ids.txt`（现有爬虫输入文件，去重），
  后续跑爬虫即可用新数据刷新 `video_info`；
- 保留浮层/详情页被动同步（hook 未覆盖场景的补充）。

## 3. 决策点（采用推荐项，备选被拒理由）

### 决策 A：详情信息自动化方式 —— 采用「网络 hook（被动观察）」

- **推荐**：注入页面级 hook，被动观察抖音主页作品列表接口（如 `/aweme/v1/web/aweme/post/`）
  的响应 JSON，解析 `aweme_list` 拿到完整字段。
  - 不发额外请求、不改请求，只读已存在的响应 → 与「绕开自动化风控」的初衷一致；
  - 主页翻页本身就会触发这些接口，采完即全量。
- **备选 B（被拒）**：自动逐个打开视频详情页补采。
  - 能拿到同样字段，但等于自动批量访问视频页，请求量随视频数线性增长，
    明显增加风控风险；与合规边界冲突，故不采用。

### 决策 B：video_id 保留方式 —— 采用「写入 video_ids.txt」

- **推荐**：插件主页采集结束后，调用 `POST /api/extension/ids`，
  后端把本次 video_ids 去重后**追加**到项目根 `video_ids.txt`（现有爬虫输入文件，已 gitignore）。
  - 与现有 `start_spider.py` / 爬虫输入直接打通，用户跑一次爬虫即可刷新数据；
  - 追加而非覆盖，不破坏已有内容。
- **备选（被拒）**：写入 Redis 队列。
  - 队列语义是「待消费任务」，本需求是「保留 ID 供后续刷新」，写队列会造成
    「未消费堆积 + 是否消费两难」的状态混乱；且现有 `/api/crawl` 已承担入队职责，职责重复。

## 4. 实现设计

### 4.1 主页全量翻页（多策略滚动）

- `collect.js` 新增 `findScrollContainer(root)`：从 `[data-e2e="user-post-list"]` 向上遍历祖先，
  返回首个「可滚动」元素（`scrollHeight > clientHeight` 或 `overflow-y` 为 `auto/scroll`）；
- 滚动策略：优先滚容器（`container.scrollTop = container.scrollHeight`），
  容器不存在或未增长时兜底 `window.scrollTo(0, document.documentElement.scrollHeight)`；
- 每轮：滚动到底 → 随机等待 1.5–3 秒 → 解析新卡片 → 去重收集；
- 停止条件保持不变：累计达 100 条，或连续 3 轮无新卡片；
- `findScrollContainer` 为纯 DOM 逻辑，提取到 `parse.js` 并用 jsdom 单测（嵌套滚动容器 fixture）。

### 4.2 网络 hook（被动观察接口响应）

架构：MV3 需要「页面世界」才能看到页面的 fetch/XHR，因此：

```text
hook.js（content_scripts，world: MAIN，注入页面世界）
  拦截 window.fetch / XMLHttpRequest，匹配作品列表/详情接口
  → 解析响应 JSON 的 aweme_list → postMessage 给 content script
collect.js（content_scripts，isolated world）
  接收消息 → parseAwemeList() 归一化为记录 → 去重合并 → 随主页批次上报
```

- `manifest.json` 增加 `hook.js`（`"world": "MAIN"`、`run_at: document_start`，
  仅 `https://www.douyin.com/*`）；
- 接口匹配规则（前缀匹配，命中任一）：
  - 作品列表：URL 含 `/aweme/v1/web/aweme/post/`（主页翻页数据源）；
  - 详情类：URL 含 `/aweme/v1/web/aweme/detail/`（浏览详情时的补充）；
- `hook.js` **只读**响应：不修改请求头/体，不发送任何新请求；
- `parse.js` 新增纯函数 `parseAwemeList(json)`：从 `aweme_list` 提取
  `video_id / video_title / video_desc / play_count / like_count / comment_count / share_count /
   publish_time(create_time) / cover_url / author_name / author_id`，
  字段缺失按容错规则记 null/0 + `missing_fields`；
- 合并策略：同一 video_id，**hook 数据优先**（更全，含 publish_time/互动），
  DOM 卡片数据兜底（hook 未命中时）；
- 合规：hook 不改动页面行为、不额外请求；限速与 100 条上限仍由 collect.js 控制。

### 4.3 video_id 保留给爬虫

- `extension_receiver.py` 新增纯函数 `merge_ids(existing, new_ids)`：
  去重、保持顺序、返回新列表（可单测）；
- `api.py` 新增 `POST /api/extension/ids`（body: `{video_ids: [...], author_id}`）：
  - 校验：video_ids 非空、每条 15–20 位数字、条数 ≤ 100；
  - 读取项目根 `video_ids.txt` → `merge_ids` 去重合并 → 写回文件；
  - 返回 `{added, total}`（added = 新增条数，total = 合并后文件行数）；
- `video_ids.txt` 已在 `.gitignore`（不提交）；文件缺失时自动创建；
- collect.js 主页采集结束后调用该端点（同一批 video_ids 去重后提交）。

### 4.4 保留的机制

- 浮层/详情页被动同步（点赞/评论/分享补充）保持不变，作为 hook 未覆盖场景的兜底；
- 部分更新 upsert 不变：主页采集补播放量时不覆盖详情已补的互动数据；
- 主页采集修好后，重跑一次即可补上现存「播放量为空」的记录。

## 5. 测试策略（TDD）

### 后端

- `tests/test_extension_receiver.py` 新增：
  - `merge_ids` 去重/保序/保留已有内容；
  - `/api/extension/ids` 校验（空列表/非法 ID/超 100 条拒绝）；
- 真库/文件验证：临时写 `video_ids.txt` 测试内容 → 调接口 → 验证合并结果 → 恢复原文件
  （不动用户已有内容；测试用前缀 `ext_test_` 的 ID）。

### 插件

- `extension/tests/parse.test.mjs` 新增：
  - `parseAwemeList`：用构造的接口 JSON fixture（含完整 statistics / create_time /
    缺失字段场景）断言字段提取与容错；
  - `findScrollContainer`：jsdom 嵌套滚动容器 fixture 断言容器命中与 window 兜底；
- `collect.js` 的滚动/上报编排依赖真实页面，维持 T3 真机验收；
- 验收清单更新：主页一次采全（58/58）、播放量 100% 有值、`video_ids.txt` 追加成功。

## 6. 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `extension/content/hook.js` | 页面世界网络 hook（观察接口响应，postMessage） | 新建 |
| `extension/content/parse.js` | 新增 `parseAwemeList` / `findScrollContainer` 纯函数 | 修改 |
| `extension/content/collect.js` | 滚动容器策略 + hook 消息接收合并 + 采集完成上报 ids | 修改 |
| `extension/manifest.json` | 增加 hook.js（world: MAIN） | 修改 |
| `extension/tests/parse.test.mjs` | hook 解析与滚动容器测试 | 修改 |
| `extension/README.md` | 说明全量翻页与 id 保留用法 | 修改 |
| `extension_receiver.py` | 新增 `merge_ids` | 修改 |
| `api.py` | 新增 `POST /api/extension/ids` | 修改 |
| `tests/test_extension_receiver.py` | merge_ids 与 ids 接口校验测试 | 修改 |
| `README.md` | 项目 README 更新（全量采集说明） | 修改 |

## 7. 非目标（本轮不做）

- 不改数据库表结构；
- 不动爬虫本体（Scrapy/队列/Playwright）与现有 `/api/crawl`；
- 不加令牌鉴权（沿用 MVP 决策，稳定后再评估）；
- 不做定时自动采集（用户手动点「开始采集」触发）；
- 不采集图文（`/note/`）与收藏数。

## 8. 实施阶段

1. **后端**：`merge_ids` + `POST /api/extension/ids` + 单测 + 文件验证；
2. **hook 解析**：`parseAwemeList` / `findScrollContainer` 纯函数 + Node 测试；
3. **插件接线**：hook.js + collect.js 滚动/合并/上报 ids + manifest；
4. **收尾**：README 更新、全量回归、真机验收清单（58/58 全量 + 播放量 100% + id 文件）。

每阶段独立验证，完成后再进入下一阶段。
