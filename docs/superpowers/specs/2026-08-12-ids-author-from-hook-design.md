# video_ids 作者归属改为以网络 hook 真实作者为准（修复）设计

日期：2026-08-12
状态：用户已确认（「修吧，以 hook 的真实数据为准」）。

## 1. 背景与问题（真机证据）

收集页作者列「全部映射成我的名字」：文件里 133 条新采集记录的 `author_id` 全是当前登录账号 uid
（`4358913414407163` = 黑白阿巴巴，用户本人）。

根因：`collect.js` 上报 ids 时用 `cfg.myUid`（登录账号）作为作者，而不是**被采集主页的真实作者**。
网络 hook（`parseAwemeList`）从接口响应 `aweme.author.uid` 能拿到真实作者，但上报 ids 时没有使用。

## 2. 目标

- ids 上报的 `author_id` 以 hook 真实作者为准；
- 无 hook 时：仅自己模式回退登录 uid（采集自己，准确）；无限制模式记空（未知，不误导）；
- 修正已写入文件的历史错误作者（以库反查覆盖）；
- 插件 videos 上报（入库）本就 hook 优先，无需改动。

## 3. 实现设计

### 3.1 纯函数（owner：`parse.js`）

```js
function resolveAuthorId(hookRecords, fallback) {
  for (const r of hookRecords || []) {
    if (r && r.author_id) return String(r.author_id);
  }
  return fallback || '';
}
```

- 从 hook 记录（`parseAwemeList` 输出，含真实 `author_id`）取第一个非空作者；
- 无则回退 `fallback`（调用方传入：仅自己模式 → `cfg.myUid`，否则 `''`）；
- 加入 `api` 导出，Node 单测。

### 3.2 collect.js

`collectProfile` 在采集循环结束、上报循环之前计算一次：
```js
const batchAuthorId = P.resolveAuthorId([...hookMap.values()], complianceLimited ? cfg.myUid : '');
```
`reportIds(P.idsFromBatch(batch), batchAuthorId)` 替代 `cfg.myUid`。

### 3.3 数据修正（一次性，用户已授权）

- 先备份 `video_ids.txt` 到系统临时目录；
- 对 `author_id == '4358913414407163'` 的行，反查库 `video_info.author_id`：
  查到且不同 → 覆盖为库值；库值相同或查不到 → 保持；
- 写回文件，输出修正行数。

## 4. 测试策略（T2 严格 TDD）

- `parse.test.mjs`：`resolveAuthorId` 取 hook 首个非空作者 / 空数组回退 fallback / undefined 输入；
- `collect.smoke.test.mjs`：注入 hook 数据（`CustomEvent`）→ 采集 → 断言 ids 上报 `author_id` 为 hook 真实作者；
- 回归：`node --test`、`pytest -q`、`npm run build`。

## 5. 文件结构

| 文件 | 动作 |
| --- | --- |
| `extension/content/parse.js` | 新增 `resolveAuthorId` + 导出 |
| `extension/content/collect.js` | 上报 ids 用 `resolveAuthorId(hookMap, fallback)` |
| `extension/tests/parse.test.mjs` | 纯函数测试 |
| `extension/tests/collect.smoke.test.mjs` | hook 作者优先测试 |
| `video_ids.txt` | 一次性数据修正（备份后执行） |
| `docs/superpowers/specs/2026-08-12-ids-author-from-hook-design.md` | 本设计 |
| `docs/superpowers/plans/2026-08-12-ids-author-from-hook.md` | 实施计划 |

## 6. 非目标

- 不改后端与文件格式；
- 不做无 hook 时的作者猜测（未知即未知）；
- 历史 241 行 author 为空的数据不在本次修正范围（仍可走 backfill 或用户自行采集覆盖）。

## 7. 实施阶段

1. `resolveAuthorId` + Node 测试（RED → GREEN）；
2. collect.js 接线 + smoke 测试（RED → GREEN）；
3. 数据修正（备份 → 反查覆盖 → 验证）；
4. 全量回归；
5. 用户确认后提交。
