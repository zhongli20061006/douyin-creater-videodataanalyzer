# 抖音创作者数据分析器（抖音爬虫管理系统）

基于 **Scrapy + Redis + MySQL + FastAPI + Vue 3** 的抖音视频数据采集、管理与个人创作数据分析面板。
支持批量视频任务队列、自动连续爬取、浏览器插件自采集、数据质量治理、多维度导出，
以及基于「成熟度分桶 + 多指标百分位」的爆款洞察。

> 合规优先：插件只采集「登录账号自己」的数据（开源版默认「仅自己」模式）。
> 本仓库仅供学习与研究使用，使用者须自行遵守抖音平台规则与相关法律法规。

## 功能特性

### 数据采集

- **爬虫（Scrapy + Playwright）**：按视频 ID 批量入队，连续消费 Redis 队列直到清空；真实浏览器渲染页面，数据自动入库（去重更新）；
- **浏览器插件（个人自采集）**：在真实浏览器里采集自己主页的播放量、点赞、评论、分享、收藏与发布时间，自动翻页全量采集，无需逐个打开视频；
- **作者主页收集（collector.py）**：作者主页 URL → Playwright 拦截页面内真实接口 → 视频预览列表（受平台风控限制，见「已知限制」）。

### 管理面板（Vue 3 + Element Plus）

- **数据总览**：实时统计 + 作者贡献度、质量分布图表（ECharts）；
- **爬虫复核**：队列内容、爬虫状态、实时日志、清空 / 批量移除队列；
- **视频数据**：搜索、排序、分页、详情、删除，支持按发布时间范围检索（含「本月」快捷）；
- **插件 ID 导入与管理**：粘贴 / 文件导入视频 ID，表格化管理采集状态与作者归属；
- **数据质量**：问题报告、一键修正、确认后删除、导出 CSV / Excel；
- **个人分析**：概览卡、互动率 / 收藏率、发布与播放趋势、Top 10 多维排序、数据完整度、**爆款洞察**；
- **设置**：面板 API 令牌、抖音 Cookie 管理（解析 / 更新 / 过期提示）。

### 数据分析

- **爆款洞察**：按发布天数分桶，对播放、互动率、收藏率计算百分位并加权评分，自动标记「潜力爆款」与「异常偏低」视频，并给出可解释的原因；
- 互动率、收藏率、发布趋势、每月播放量、Top 多维排序、数据完整度标注。

### 数据治理与运维

- **入库治理**：过滤空记录 / 占位页、标题规范化、不完整数据不覆盖已有记录（INSERT IGNORE 兜底）；
- **定时清理**：按作者维度、自定义条数，删除最旧数据前自动备份（默认每 30 天检查）；
- **数据导出**：按当前筛选结果导出 CSV / Excel（上限 1 万条，CSV 流式）；
- **深色数据看板**：设计令牌统一（颜色 / 间距 / 圆角），Element Plus 深色主题。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.13 · Scrapy 2.12 · FastAPI · MySQL · Redis · Playwright |
| 前端 | Vue 3.5 · Vite 8 · TypeScript · Element Plus · Pinia · ECharts |
| 插件 | Chrome Manifest V3（content script + background service worker） |

## 目录结构

```text
.
├── api.py                    # FastAPI 应用与全部接口
├── analyzer.py               # 个人分析聚合 + 爆款洞察评分
├── collector.py              # 作者主页收集（受平台风控限制）
├── quality.py                # 数据质量：扫描/统计/修正/删除校验
├── queue_service.py          # 爬虫队列条目解析
├── cleanup_service.py        # 定时清理规则与备份
├── export_service.py         # CSV / Excel 导出
├── extension_receiver.py     # 插件数据校验/去重/部分更新
├── cookie_config.py          # 抖音 Cookie 解析与读写
├── time_filter.py            # 发布时间范围过滤
├── douyin_spider/            # Scrapy 爬虫（管道、中间件、spider）
├── frontend/                 # Vue 3 前端（npm 工程，dist 为构建产物）
├── extension/                # Chrome 插件（个人主页自采集）
├── tests/                    # pytest 单元测试
├── scripts/                  # 开源版构建脚本等
├── release/open-source/      # 开源版发布产物（由脚本生成）
├── local_config.example.py   # 本地配置示例
├── local_config.py           # 本地敏感配置（.gitignore，不提交）
├── run_backend.ps1           # 一键启动后端（Windows）
├── stop_backend.ps1          # 一键停止后端（Windows）
└── start_server.py           # 通用启动入口（--host/--port/--reload）
```

## 快速开始

### 环境要求

- Python 3.13
- Node.js（前端开发 / 插件测试）
- MySQL（本地默认 localhost:3307，库名 douyin_spider）
- Redis（本地默认 localhost:6379）
- Chrome（插件与爬虫渲染）

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item local_config.example.py local_config.py
# 编辑 local_config.py：填入抖音 Cookie、MySQL 密码、API 令牌等
.\.venv\Scripts\python.exe -m playwright install chromium   # 首次使用爬虫前
.\.run_backend.ps1                                           # 面板默认 http://127.0.0.1:8001
```

### 前端（开发模式）

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5173/app/，/api 代理到 8001
npm run build    # 生产构建，由后端在 /app 提供
```

### 浏览器插件（个人数据自采集）

1. 打开 Chrome → chrome://extensions → 开启「开发者模式」→「加载已解压的扩展程序」，选择 extension/ 目录；
2. 点击插件图标配置后端地址（默认云服务器 http://47.120.36.73，本机开发改为 http://127.0.0.1:8001）与采集模式；
3. 登录抖音网页版，进入自己的主页，点击右下角「开始采集」——自动翻页全量采集，并通过被动网络 hook 补全点赞/评论/分享/发布时间；
4. 浏览自己的视频详情页时，插件仍会被动补充（hook 未覆盖场景的兜底）。

**采集模式（插件选项页可选）**

- **仅自己（开源发布推荐）**：白名单校验，只在当前登录账号自己的主页启用采集；
- **无限制（本地开发用）**：可采集任意用户主页，便于开发对照。

> 合规声明：主仓库本地开发默认「无限制」仅为开发便利；公开分发前请将插件默认模式改为「仅自己」（见 extension/content/collect.js 与 extension/options/options.js 的 complianceMode 默认值）。

## 配置说明（local_config.py）

local_config.py 已被 .gitignore 忽略，不会提交到 Git；复制 local_config.example.py 后填写：

| 配置项 | 说明 |
| --- | --- |
| DOUYIN_COOKIES | 浏览器登录抖音后抓取的 Cookie 字典；会过期，需定期更新 |
| MYSQL_PASSWORD | MySQL 密码（MYSQL_HOST / PORT / USER / DB 可在此覆盖，缺省走 douyin_spider/settings.py） |
| EXTENSION_API_TOKEN | 扩展上报鉴权令牌；插件选项页需填写同一令牌，留空时 fail-closed（503） |
| ALLOWED_AUTHOR_IDS | 服务端作者白名单；非空时后端拒绝白名单外作者的数据（开源版双保险） |
| CLEANUP_STORAGE | 清理配置存储：'redis'（本地版默认）/ 'json'（开源版，无 Redis 依赖） |

## 主要接口（/api）

| 分组 | 接口 |
| --- | --- |
| 分析 | /api/analyze/authors · /api/analyze/personal · /api/analyze/insights |
| 视频 | /api/videos · /api/stats · /api/export |
| 队列 / 爬虫 | /api/queue/* · /api/spider/* · /api/crawl |
| 质量 | /api/quality/* |
| 插件上报 | /api/extension/videos · /api/extension/ids |
| 清理 / 配置 | /api/cleanup/* · /api/config/cookie |

- 所有 GET /api/* 均挂只读鉴权（Origin 白名单或 X-API-Token，fail-closed）；
- 写接口（爬虫/队列控制、质量修复/删除、扩展上报等）鉴权规则见「后端安全」。

## video_ids.txt 说明

- 每行格式：video_id | status | author_id（纯 id 行视为 pending，向后兼容）；
- 插件采集上报的新 id 记为 pending，已存在的 id 重置 pending；
- 「导入爬虫队列」只推送 pending 与文件外的新 id，推送成功后标记 done，避免重复爬取；
- 收集页支持按作者 / 状态筛选，可将已采集改为「待采集」强制重爬。

## 后端安全

- 默认仅绑定 127.0.0.1（run_backend.ps1 / start_server.py 可传 --host 覆盖）；
- 写接口守卫：Origin 在本机白名单（127.0.0.1/localhost:8001、localhost:5173）或请求头 X-API-Token 匹配 local_config.py 的 EXTENSION_API_TOKEN；
- 只读接口同样走 verify_read_guard（Origin 白名单或 X-API-Token）；
- 令牌未配置时一律 fail-closed（返回 503 并提示）；
- 令牌以明文存于本机 local_config.py 与浏览器存储，请勿外传。

## 已知限制

- 抖音「作者作品列表」接口有平台风控，后端自动收集（collector.py）暂不可用；个人数据请使用浏览器插件在真实浏览器中采集；
- 爬虫使用 Playwright 有头模式，后台运行时屏幕上会弹出浏览器窗口，属预期行为；
- 插件不采集图文（/note/）；页面结构改版时取不到的字段会记为缺失并提示，不会中断采集；
- Cookie 会过期，需要定期更新；
- 全量 pytest 请使用 pytest tests -q（直接 pytest -q 会因 release/open-source/tests 同名模块导致收集冲突，属既有现象）。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q          # 后端单测
cd extension
node --test                                    # 插件解析单测
cd ..\frontend
npm run build                                  # 前端类型检查 + 生产构建
```

## 开源版

- 开源版由 scripts/build_open_source_release.py 生成到 release/open-source/：
  - 移除爬虫 / 队列 / 收集 / 数据总览 / 数据质量等依赖 Scrapy / Redis / Playwright 的模块；
  - 前端只保留视频数据 + 个人分析（含爆款洞察）；
  - 插件默认采集模式改为「仅自己」，CLEANUP_STORAGE 改为 json；
- 独立说明见 scripts/open_source_README.md；开源版仅需 FastAPI + MySQL 即可部署。

## 合规与用途声明

本项目仅供学习与研究用途。使用者须自行遵守：

- 抖音（字节跳动）及相关平台的用户协议、robots.txt 与服务条款；
- 《网络安全法》《数据安全法》《个人信息保护法》及适用的法律法规；
- 不得将本项目用于商业牟利、大规模数据采集或其他违反平台规则的目的。

本项目包含浏览器渲染、Cookie 注入等自动化技术，仅用于技术研究演示。请勿以此规避平台的反爬机制；因使用本项目产生的账号风险、法律风险由使用者自行承担。

## License

[MIT](LICENSE)
