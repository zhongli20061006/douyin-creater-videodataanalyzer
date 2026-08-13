# 开源版发布准备 设计稿

日期：2026-08-13
状态：设计稿（用户已确认全部决策点，待用户审阅定稿后进入实施计划）。

## 1. 背景与目标

当前仓库是「本地开发版」，功能完整但包含爬虫（Scrapy + Playwright + Redis 队列）、本地「无限制」采集模式、以及大量本地运维入口。开源发布的目标是产出一个定位为「个人数据自采集 + 自分析」的精简开源包：

- 浏览器插件默认「仅自己」，只采集登录账号自己的主页/详情数据；
- 后端只保留数据接收、视频列表/详情、个人分析、定时清理、导出；
- 去掉 Scrapy / Playwright / Redis / 队列 / 收集 / 数据总览 / 数据质量等与「个人自用」无关的内容；
- 通过发布脚本从主仓库生成干净的开源包，推送到独立开源仓库，历史从零开始，杜绝凭据风险。

## 2. 已确认决策

1. **发布形态**：独立开源 GitHub 仓库 + 主仓库发布脚本生成干净目录（方案 A）；
2. **开源版范围**：插件 + 后端接收 + 视频数据页 + 个人分析页；移除爬虫/队列/收集/质量/总览；
3. **定时清理**：开源版保留，逻辑不变（30 天、按作者、自定义条数、开关、删除前备份）；配置存储从 Redis 改为**本地 JSON 文件**（去掉 Redis 依赖）；主仓库同步改为 JSON（主仓库 Redis 仅保留给爬虫队列）；
4. **数据导出**：视频数据页加「导出」按钮，导出当前筛选结果（搜索/发布时间范围/排序），CSV 与 Excel 两种；主仓库与开源版都加该入口；
5. **插件默认模式**：主仓库保持「无限制」（本地开发），发布脚本生成开源包时把默认值替换为「仅自己」；
6. 开源版仍保留时间检索、收藏率、非本人标注、按作者清理等已交付能力。

## 3. 开源版保留 / 移除清单

### 3.1 保留

- 插件 `extension/`（manifest 描述更新为含收藏；默认模式在发布时改为 limited）；
- 后端：FastAPI + MySQL，接口：
  - `POST /api/extension/videos`（数据接收，令牌守卫）；
  - `GET /api/videos`、`GET /api/videos/{video_id}`（搜索/排序/分页/时间筛选/详情）；
  - `GET /api/analyze/authors`、`GET /api/analyze/personal`（个人分析，时间筛选 + sort_by 含 collects）；
  - `GET /api/cleanup/status`、`POST /api/cleanup/toggle`、`POST /api/cleanup/settings`（配置 JSON 化）；
  - `GET /api/export`（新增：导出当前筛选结果 CSV/Excel）；
- 后端模块：`extension_receiver.py`、`analyzer.py`、`time_filter.py`、`cleanup_service.py`、`export_service.py`（从 quality.py 抽出 build_csv/build_xlsx）、`api.py`；
- 前端：`Videos.vue`（含导出按钮）、`PersonalAnalyzer.vue`、`StatCard.vue`、路由/布局/api 组合等；
- `README.md`（重写开源版定位）、`LICENSE`、`requirements.txt`（精简）、`local_config.example.py`；
- `run_backend.ps1` / `stop_backend.ps1`（启动脚本）。

### 3.2 移除

- `douyin_spider/`（Scrapy 爬虫）、`collector.py`、`queue_service.py`、`quality.py`、`start_server.py`、`start_spider.py`、`batch_push.py`；
- `video_ids.txt` 及其 `/api/extension/ids`、`/api/extension/ids/status` 接口（开源版无爬虫队列，不再需要 id 队列）；
- `/api/spider/*`、`/api/queue/*`、`/api/crawl`、`/api/collect/author`、`/api/quality/*`、`/api/stats`、`/api/stats/authors`（数据总览移除后不再需要）；
- 前端：`Dashboard.vue`、`Collect.vue`、`Quality.vue`、`Queue.vue`、`PieChart.vue` 及相关路由；
- `SpiderManager`、Redis 依赖（清理配置已 JSON 化，开源版无需 Redis）；
- 开发期调试文件与日志（`douyinpage*.html`、`*.log` 等，由发布脚本排除）。

> 说明：以上移除清单只作用于「开源包」；主仓库本身保留这些文件与功能（含 `quality.py` 与数据质量页）。

## 4. 关键改动

### 4.1 定时清理配置 JSON 化（主仓库 + 开源版）

- 新增配置文件 `cleanup_config.json`（项目根目录，`.gitignore` 排除，运行时本地生成）：
  ```json
  {
    "enabled": false,
    "last_clean_time": null,
    "batch_size": 200,
    "authors": []
  }
  ```
- `cleanup_service.py` 新增线程安全的 JSON 读写函数（文件锁 + 原子写，沿用 `extension_receiver` 的 ids 文件锁模式）：
  - `read_cleanup_config(path) -> dict`
  - `write_cleanup_config(path, config: dict) -> None`
- `api.py` 的 `cleanup_status` / `cleanup_toggle` / `cleanup_settings` / `_cleanup_once` 从 JSON 文件读写，替换原 Redis 读写；`CLEANUP_CONFIG_PATH` 常量指向项目根目录；
- 主仓库移除 Redis 作为清理配置存储的用法（Redis 仍保留给爬虫队列，但清理不再依赖 Redis，开源版彻底无 Redis）。

### 4.2 数据导出（主仓库 + 开源版）

- 新增 `export_service.py`：把 `quality.py` 的 `build_csv` / `build_xlsx` 与 `EXPORT_COLUMNS`（含 collect_count）抽出，列与现在一致；
- 新增 `GET /api/export`：参数复用 `/api/videos` 的 search/sort_by/order/start_date/end_date（不含分页，导出全部匹配行），返回 CSV 或 xlsx 附件；
- 前端 `Videos.vue` 加「导出 CSV」「导出 Excel」按钮，用 `window.location.href` 指向 `/api/export`（携带当前 search/sort_by/order/start_date/end_date 参数），由后端返回附件下载；
- 主仓库 `Quality.vue` 的导出入口保留（避免重复实现，统一指向 `/api/export` 或保留原 `/api/quality/export`；本设计统一新增 `/api/export`，质量页后续可切到同一接口）。

### 4.3 插件默认模式与描述

- 主仓库：`options.js` / `collect.js` 默认值保持 `unlimited`（本地开发）；
- 发布脚本：生成开源包时把 `extension/options/options.js` 与 `extension/content/collect.js` 中的默认值 `'unlimited'` 替换为 `'limited'`；
- `manifest.json` description 更新为「采集自己抖音主页视频的播放量与详情页互动（点赞/评论/分享/收藏）数据，上报到自己的后端。只能采集自己的数据」。

### 4.4 依赖精简

- 开源版 `requirements.txt` 仅保留：`fastapi`、`uvicorn`、`pymysql`、`pandas`、`openpyxl`（导出用）、`pydantic`；
- 移除 `scrapy`、`playwright`、`fake-useragent`、`redis`、`mysql-connector-python`（爬虫用）、`jsonpath` 等。

### 4.5 前端裁剪

- 路由与菜单只保留「视频数据」「个人分析」两项；
- 删除 Dashboard/Collect/Quality/Queue 页面与 `PieChart.vue` 引用；
- 清理控件保留在「视频数据」页（开源版唯一入口）；「个人分析」页不放清理控件。

### 4.6 README 重写

- 标题「抖音创作者数据分析器」；
- 定位：个人自采集 + 自分析；
- 说明：插件默认「仅自己」、后端本地运行、时间检索、收藏率、定时清理、导出；
- 合规声明保留并置于显眼位置；
- 移除爬虫/队列/Playwright 相关说明。

## 5. 发布脚本设计（`scripts/build_open_source_release.py`）

- 输入：主仓库根目录；
- 输出：`release/open-source/` 干净目录（`release/` 加入 `.gitignore`）；
- 步骤：
  1. 按「保留清单」复制文件（白名单，而非复制后删黑名单）；
  2. 替换插件默认模式 `unlimited` → `limited`；
  3. 写入精简后的 `requirements.txt`；
  4. 生成 README 开源版说明（若与主仓库 README 不同）；
  5. 在输出目录初始化 git、写 `.gitignore`；
  6. 打印「复制完成，请 review 后推送到开源仓库」提示（**不自动 push**，推送由用户确认）。
- 脚本本身保留在主仓库，不进开源包。

## 6. 测试策略（T2 严格 TDD）

- `cleanup_service` JSON 读写：默认配置、读写往返、并发原子写（文件锁）、坏 JSON 容错；
- `export_service`：CSV 表头含 collect_count、xlsx 生成、特殊字符转义；
- `api.py` 清理接口 JSON 化：status/toggle/settings 读写配置（用临时文件 mock `CLEANUP_CONFIG_PATH`）；
- 插件默认模式：开源包生成后 `grep` 校验 `options.js`/`collect.js` 默认值为 `limited`（发布脚本测试）；
- 发布脚本：白名单复制结果包含保留文件、不含移除文件；
- 回归：主仓库 pytest 全量、`node --test`、`npm run build`。

## 7. 文件结构

| 文件 | 动作 |
| --- | --- |
| `cleanup_service.py` | 加 JSON 配置读写 |
| `export_service.py` | 新增（从 quality.py 抽出） |
| `api.py` | 清理配置 JSON 化 + `/api/export` + 移除开源版不需要的接口（由发布脚本裁剪或运行时路由区分） |
| `frontend/src/pages/Videos.vue` | 加导出按钮 |
| `frontend/src/router/index.ts`、`layouts/MainLayout.vue` | 裁剪菜单 |
| `extension/manifest.json` | 描述更新 |
| `requirements.txt` | 精简 |
| `README.md` | 重写 |
| `scripts/build_open_source_release.py` | 新增发布脚本 |
| `tests/test_cleanup_service.py`、`tests/test_export_service.py`、`tests/test_release_script.py` 等 | 新增测试 |
| `docs/superpowers/specs/2026-08-13-open-source-release-design.md` | 本设计稿 |
| `docs/superpowers/plans/2026-08-13-open-source-release.md` | 实施计划（下一步） |

## 8. 非目标

- 不重写 git 历史、不删除 `backup-pre-cleanup`（本设计不触碰，开源包历史从零开始，与该分支无关）；
- 不做云部署（另议）；
- 不改数据库结构；
- 不改爬虫主仓库功能（爬虫保留给本地开发仓库）。

## 9. 风险与已知边界

- 主仓库清理配置从 Redis 迁到 JSON 后，已有的 Redis 清理配置（若存在）不迁移——清理功能此前默认关闭、几乎无存量配置，影响可忽略；
- JSON 配置并发写用文件锁串行化，清理调度为单后台线程，写冲突概率极低；
- 开源包无 Redis，部署更简单，但 `requirements.txt` 需在发布脚本中强制覆盖；
- 发布脚本不自动 push，避免误推；推送前用户 review 输出目录。
