# 抖音创作者数据分析器 新窗口交接

工作目录：`D:\DjangoProject\PythonProject11`
当前日期：2026-08-12
当前目标：继续项目收尾——剩余待办为云部署（方向 A）（时间检索、定时清理、收藏字段均已在本窗口完成并验收；PR #1/#2/#3 均已合并）。

## 必须遵守

- 全程中文交流；
- 项目级流程以 `sliver-vibe-coding` 为顶层 owner（先读 SKILL.md 与 references/routes-index.md）；新功能/修改行为前先 `brainstorming`，实现必须 `test-driven-development`，多步任务先 `writing-plans`；
- 只做用户授权范围；不做破坏性操作（不删数据、不改数据库结构、不删用户文件——数据库改动需用户明确授权，用户已表态「收藏要详细讨论后动手」）；
- git 命令必须带 `-c safe.directory=D:/DjangoProject/PythonProject11`；git 写操作、联网、启动服务需用户确认；
- 每次声称完成前跑验证并给证据（命令 + 结果）；
- `local_config.py` 含真实凭据（Cookie / MySQL 密码 / 令牌），严禁提交；`backup-pre-cleanup` 分支含旧凭据历史，**严禁推送**，删除前先问用户。

## Git State

本窗口工作分支：`codex/collect-count`（2026-08-12 从 `codex/personal-analyzer-extension` 拉出，收藏字段专用，含 10 个提交未推送）。

主仓（唯一仓库）：
```text
On branch codex/personal-analyzer-extension
ahead of 'origin/codex/personal-analyzer-extension' by 13 commits
nothing to commit, working tree clean
```

本地分支：`codex/personal-analyzer-extension`（当前）、`master`（PR #1 目标）、`backup-pre-cleanup`（含旧凭据，禁推禁删需先问）。
远端：`origin/master`、`origin/codex/personal-analyzer-extension`（本地领先 13 提交未推送）。

最近提交（自 base 起）：
```text
e49ccf1 feat: 品牌改名「抖音创作者数据分析器」+ 数据总览水平条形图 + 插件 ID 导入与管理页调整
a6a6359 feat: 个人分析增强（互动率/播放趋势/多维排序/完整度）+ 图表深色配色修复
334ec19 feat: 爬虫队列管理（清空/批量移除）+ 导入跳过已采集提示
26e4070 feat: 原型收尾——作者归属/昵称映射/批量管理/CORS 修复/hook 作者修复
c9246e4 feat: video_ids.txt 增加 pending/done 状态，爬虫只推待采集 id
1bacc22 feat: 个人分析最近同步改为 MAX(update_time)，反映爬虫刷新
52e9b14 chore: 清理无用死文件（test/debug_spider/id 脚本与 douyin_spider/utils 死代码）
b9c0709 feat: 后端绑定 127.0.0.1 + 扩展写接口令牌鉴权（fail-closed）
191fa19 docs: README 补充采集计数与手动停止说明
```

## Current Truth

- 产品边界：浏览器插件采集创作者主页/详情数据 → 后端接收（校验/去重/部分更新 upsert）→ 看板分析。插件只在「当前登录账号自己的作者主页」启用（合规边界），本地版有「无限制」模式用于开发对照；GitHub 开源版发布前必须把选项页默认改成「仅自己」。
- 当前阶段：原型功能收尾完成，未部署；分支未合并。
- 主要 owner：`extension_receiver.py`（纯逻辑）、`api.py`（薄层）、`analyzer.py`（聚合）、`queue_service.py`（队列工具）、`extension/content/parse.js`（解析纯函数）、`frontend/src`（Vue3）。
- 当前真源文档（docs/superpowers/）：
  - specs：2026-08-11-personal-analyzer-extension-design.md（MVP）、collection-complete、extension-stop-counter-ids-fix、backend-auth-bind、2026-08-12-video-ids-status / video-ids-author / ids-author-name-batch / ids-author-from-hook / extension-background-relay / analyzer-enhancement / queue-manage
  - plans：对应上述各实施计划
  - handoff：本文件
- 用户确认过的非目标：定时采集（P2-C 取消）、目录重构（不做）、按作者分区（未做）、前端状态展示已并入收集页。
- 被拒绝路线：仅绑定 127.0.0.1 而不加令牌（不够）、CORS 白名单加 douyin.com（不安全）、fail-open 令牌（留后门）。

## 本窗口完成（按 owner）

### 收藏字段（collect_count）纳入（2026-08-12，本窗口新增）

- **数据库**：`ALTER TABLE video_info ADD COLUMN collect_count bigint DEFAULT '0' COMMENT '收藏数' AFTER share_count`；`share_count` 注释修正为「分享数」（实测 MySQL 按 DEFAULT 0 将存量 1443 行填 0，完整度把 0 视为缺失，等效未采集）；
- **爬虫**：`items.py` 加字段、`parse_video_data()` 提取 `statistics.collect_count`（缺失 0）、`pipelines.py` 两处 SQL + params 加列（全字段 upsert，兜底 INSERT IGNORE 不覆盖）；
- **插件**：`parseAwemeList`（hook JSON）与 `parseVideoDetail`（`[data-e2e="video-player-collect"]`）提取收藏；`mergeCardWithHook` 透传；
- **后端**：`extension_receiver.py` COUNT_FIELDS/INSERT_COLUMNS 加列（None=未采集跳过更新）；`api.py` VideoItem + 排序白名单；`analyzer.py` total_collects/completeness.collect/`sort_by='collects'`；
- **前端**：个人分析页（总收藏卡 7 卡布局、互动图加收藏、完整度加收藏、Top 按收藏排序与列）、视频数据页（收藏列/排序/详情抽屉）；
- **修复（验证暴露）**：unlimited 模式主页采集作者归属——以「卡片链接 secUid × hook `author.sec_uid` 精确匹配」确定页面主人（合拍/转载/跨页残留均归页面主人），自己主页（登录 secUid=页面 secUid）用登录配置；**RENDER_DATA 的 `app.odin` 是登录账号，不可用作页面主人**（曾误用导致 234 条错标，已删）；
- **数据操作**：删除 234 条错标行（author_id=登录账号且 author_name 空），删除前完整备份至 `D:\pip_tmp\collect_count_mislabeled_20260812.json`（可恢复）。

### 时间检索 + 定时清理 + 个人分析标注（2026-08-12，本窗口新增）

- **时间检索**：`/api/videos`、`/api/stats`、`/api/analyze/personal` 支持 `start_date`/`end_date`（`YYYY-MM-DD` 闭区间，按 `publish_time`）；非法格式或起止倒置 → 400；前端三页（视频数据/数据总览/个人分析）加日期范围选择器（含「本月」快捷），与搜索/排序/分页/作者选择组合；
- **定时清理（升级版，按作者精准）**：后端启动时注册后台循环（每 24h 检查一次），开关开启且距上次执行满 30 天时执行；**按作者维度**——作者多选（空=全部作者），删除条数可自定义（前端填写，默认 200，存 Redis）；被选中作者行数 > N 时按 `update_time` 升序删最旧 N 条，≤ N 不删；删除前完整备份到 `CLEANUP_BACKUP_DIR`（默认系统临时目录 `douyin_cleanup_backup`）并写日志，备份失败不删；Redis keys：`douyin:cleanup_enabled` / `douyin:cleanup_last_time` / `douyin:cleanup_batch_size` / `douyin:cleanup_authors`；配置入口 = 视频数据页 + 数据质量页（控件：开关/条数/作者多选，共用同一 Redis 状态）；
- **收藏率**：`analyzer.summarize_rows` 的 `engagement` 新增 `collect_rate`（无播放量退化以点赞为分母）；个人分析页新增「收藏率」卡；
- **非本人标注**：个人分析页在 `play.missing_rate >= 0.99` 时显示「分享率、收藏率以点赞数为分母计算」；
- **顺带修复**：`/api/analyze/personal` 的 `sort_by` 白名单补上 `collects`（此前前端有「按收藏」但后端会 400）；FastAPI `on_event` 改为 lifespan 写法（消除弃用警告）。

### 后端（Python）
- 鉴权：绑定 127.0.0.1、CORS 白名单、写接口守卫（Origin 白名单或 X-API-Token，fail-closed）；`/api/extension/ids/status`、`/api/queue/clear`、`/api/queue/remove`；
- `video_ids.txt`：`id|status|author_id` 三列、状态管理、作者归属、昵称映射（`attach_author_names`）、`set_ids_status`、`backfill_authors`（函数就绪未执行）、PUT 允许空数组清空；
- 分析：`latest_sync=MAX(update_time)`、互动率（无播放量时评论/分享率退化以点赞为分母）、`build_play_trend`、`completeness`、`top_videos(sort_by)`；
- 爬虫队列：清空/批量移除（保序重建）。

### 插件（Chrome MV3）
- CORS 修复：上报改走 background service worker（`background.js` 转发，`collect.js` 用 `chrome.runtime.sendMessage`）；
- 作者归属：`resolveAuthorId(hookRecords, fallback, videoIds)` 以网络 hook 真实作者为准，并按本次采集 video_id 过滤跨页面残留；
- 选项页新增 API 令牌（`apiToken`）。

### 前端（Vue3）
- 品牌改名「抖音创作者数据分析器」；菜单/路由：数据总览、爬虫复核、插件 ID 导入与管理、视频数据、数据质量、个人分析；
- 数据总览：作者贡献度水平条形图（Top 15，移除两张饼图）；
- 个人分析：互动率卡、每月播放量趋势图、Top 多维排序、数据完整度卡（含非主页来源标注）、深色图表配色修复；
- 插件 ID 导入与管理页：表格化（状态/作者筛选、批量待采集/已采集/删除）、tab 顺序调整；
- 队列监控：多选移除选中、清空队列；质量页说明文案。

### 文档
- specs/plans 若干（见 Current Truth）；README 补充后端安全、video_ids 状态、上报机制。

### 开源版发布准备（2026-08-13，本窗口新增，分支 `codex/open-source-release`）

- **导出**：新增 `export_service.py` 与 `GET /api/export`（当前筛选结果 CSV/Excel，上限 10000、CSV 流式、xlsx 临时文件）；视频数据页加「导出 CSV/Excel」按钮；
- **服务端作者白名单**：`ALLOWED_AUTHOR_IDS`（非空时后端拒绝白名单外作者，空 = 本地不限制）；
- **清理配置双存储**：本地版 `CLEANUP_STORAGE='redis'`（默认），开源版 `'json'`（本地 `cleanup_config.json`，无 Redis）；
- **发布脚本**：`scripts/build_open_source_release.py` 白名单复制 + 裁剪（去爬虫/队列/收集/质量/总览，前端只留视频数据+个人分析）+ 插件默认模式改「仅自己」+ `CLEANUP_STORAGE` 改 json + npm 构建 dist + 覆盖精简 README/requirements，输出 `release/open-source/`（不自动 push）；
- 开源包已生成并验证：无 `douyin_spider/` 等、`frontend/dist` 存在、插件默认 `limited`、`CLEANUP_STORAGE='json'`；待用户在其他机器实测。

## 变更文件

工作树干净，无未提交/未跟踪文件（用户截图此前已由用户自行删除）。

## 验证证据

已通过（本窗口最近一次，2026-08-12）：
```bash
cd extension && node --test        # 32 passed
.\.venv\Scripts\python.exe -m pytest -q   # 160 passed（1 条 pandas/pyarrow 既有警告）
cd frontend && npm run build       # 构建成功（chunk 大小警告为既有提示）
```

真机已验证：插件主页采集（计数/停止/入库）、CORS 修复后上报、作者归属以 hook 为准（含 SPA 残留过滤）、收集页表格/批量操作、队列清空/移除；**收藏字段**：爬虫跑 2 条历史数据（收藏 610/162 入库）；浏览器插件在「Token就是词元」主页采集 60 条，作者与收藏全部正确入库（60/60 有收藏值）；**时间检索**：三接口 2026-08 过滤（1503→61 / 个人 305→4）、非法日期 400；**清理开关**：默认关闭、toggle 开/关往返正确；浏览器四页验证通过。

未验证：`backfill_authors` 历史 241 行补全（未执行，需用户确认）；部署相关全部（未部署）；定时清理的「满 30 天实际执行」需等真实到期（逻辑与单测已覆盖，测试可用注入间隔验证）。

## 运行状态

- 后端：FastAPI 运行于 `http://127.0.0.1:8001`（监听 127.0.0.1，当前进程 PID 见 `backend.pid`）；启动：`.\run_backend.ps1` / `.\stop_backend.ps1`；
- MySQL：localhost:3307/douyin_spider；Redis：localhost:6379；`video_ids.txt` 当前 450 行（含未清理的错标 author id）；
- 扩展 API 令牌（选项页需与 `local_config.py` 的 `EXTENSION_API_TOKEN` 一致）：`fd184385866db9c80d9e74689f817cb0`；
- 插件需在 `chrome://extensions` 重新加载、且刷新抖音页面后新代码才生效。
- **云服务器（2026-08-13 部署中）**：公网 `47.120.36.73`（阿里云 ECS，华南2河源，Ubuntu 22.04，2C4G）；SSH 登录凭据由用户持有（**严禁写入仓库/交接文档**）；
- 云上部署路径 `/opt/douyinpachong`（app 用户）；systemd 服务 `douyinpachong`（uvicorn 127.0.0.1:8001）；Nginx 反代 80；MySQL 127.0.0.1:3306/douyin_spider（用户 douyin_app，密码在服务器 `/root/deploy_secrets`）；Redis 127.0.0.1；云库已迁移 1503 行；面板 `http://47.120.36.73/app/` 公网可访问；
- 云上令牌/爬虫 Cookie 在服务器 `/opt/douyinpachong/local_config.py`（600 权限，不提交）。

## 漂移警告

- 不要推 `backup-pre-cleanup`（旧凭据历史）；删除前必须问用户；
- 不要改回 CORS `allow_origins=['*']`（drive-by 风险）；扩展上报已走 background SW，白名单保持收紧；
- 不要删 `local_config.py`、`video_ids.txt`；数据库结构改动（如收藏列）必须经用户明确授权；
- `PUT /api/extension/ids` 空数组=清空文件是既定语义（配合批量删除全选）；
- 「导入爬虫队列」只推 pending/新 id，已 done 的显示「跳过已采集」（防重复是设计）；
- 插件 collect.js 的 `resolveAuthorId` 必须传本次采集 video_id 列表（防跨页面残留误标作者）；
- 交接提到「最近同步」已改为 `MAX(update_time)`，不要再改回 crawl_time。
- **RENDER_DATA 的 `app.odin` 是登录账号，不是页面主人**；主页采集归属以「卡片 secUid × hook author.sec_uid 匹配」为准（含合拍/转载/跨页残留），不要再回到 RENDER_DATA odin；
- 主页采集归属语义：采哪个主页，记录（含合拍/转载）就归哪个主页主人；hook 只补数据不改归属；
- 收藏字段已纳入：不要回退 `INSERT_COLUMNS`/`COUNT_FIELDS`/前端收藏展示；`video_ids.txt` 中错标 author 的 id 未清理（待用户决定）。
- 定时清理开关默认关闭；开启后每 30 天按作者规则执行（作者多选 + 自定义条数，均存 Redis）；单作者行数 ≤ 条数 N 不删；删除前备份到 `CLEANUP_BACKUP_DIR`，备份失败不删；`CLEANUP_BATCH_SIZE` 仅作 Redis 缺省值（1-1000 可在前端调整）。
- 时间检索只按 `publish_time`；不要扩展到 crawl_time/update_time 过滤（当前无此需求）。
- 云服务器 SSH(22) 当前对全网开放，建议收紧为本地公网 IP；RDP(3389) 可删除（Linux 用不到）；
- 云上爬虫浏览器需改无头模式（当前 `headless=False` 跑不了）；爬虫 MySQL 配置需从 local_config 读（当前 settings 写死 3307/root）；
- 公网只读接口目前无鉴权，需补访问令牌（计划 Task 3）后再长期暴露；
- 云上 `local_config.py`、`/root/deploy_secrets` 均不写入仓库/交接文档，凭据只在服务器本地。

## 下一步

1. **开源发布已完成**：开源包已推送到独立仓库 `zhongli20061006/douyin-data-analyzer`（main 分支）；
2. **云部署剩余（按 docs/superpowers/plans/2026-08-13-cloud-deploy.md 执行）**：爬虫无头模式、爬虫 MySQL 配置、只读接口鉴权、云地址配置（CORS/插件）、Cookie 迁移与真机验证；
3. 可选：`backfill_authors` 历史数据补全、开源版发布准备（默认「仅自己」模式等）、`video_ids.txt` 错标 author 清理。
