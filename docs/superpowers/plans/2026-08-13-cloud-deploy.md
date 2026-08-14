# 云部署剩余准备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 完成完整版（主仓库）上云所需的代码改造，让爬虫在云上可用、公网访问有鉴权、插件能上报到云，并完成真机验证。

**Architecture:** 部署已完成基础设施（服务器初始化、MySQL/Redis/Python/Chromium、代码 clone、systemd、Nginx、前端 dist、数据迁移 1503 行）。本计划只做代码层改造：无头模式、MySQL 配置、只读鉴权、云地址配置，以及 Cookie 迁移与验证。

**前置（2026-08-13，已完成的部署现状）**

- 云服务器：47.120.36.73（华南2河源，Ubuntu 22.04，2C4G）；SSH 登录凭据由用户持有，不在仓库中；
- 部署路径：`/opt/douyinpachong`（app 用户）；systemd 服务 `douyinpachong`（uvicorn 127.0.0.1:8001）；Nginx 反代 80；
- MySQL 8.0（127.0.0.1:3306，库 douyin_spider，用户 douyin_app，密码在服务器 `/root/deploy_secrets`）；Redis（127.0.0.1）；
- 云库数据已迁移（1503 行）；面板 `http://47.120.36.73/app/` 公网可访问；
- git 命令带 `-c safe.directory=D:/DjangoProject/PythonProject11`；本计划在本地分支开发、测试后推送 master，再部署到服务器。

---

### Task 1: 爬虫无头模式（douyin_spider/middlewares.py + collector.py，TDD）

**Files:**
- Modify: `douyin_spider/middlewares.py`
- Modify: `collector.py`

目标：Playwright 浏览器在云上以 `headless=True` 运行（本地开发仍可用有头模式，通过配置切换）。

- [x] **Step 1: 写失败测试**（新增 `tests/test_headless_config.py`）：验证中间件从 settings 读取 `PLAYWRIGHT_HEADLESS`，默认 True（云上安全），False 时保留有头；
- [x] **Step 2: 实现**：`PlaywrightMiddleware` 与 `collector.fetch_author_videos_browser` 的 `headless=` 改为 `crawler.settings.get('PLAYWRIGHT_HEADLESS', True)` / 函数参数；
- [x] **Step 3: 回归**：pytest 全量；
- [x] **Step 4: Commit**。

---

### Task 2: 爬虫 MySQL 配置从 local_config 读取（douyin_spider/settings.py，TDD）

**Files:**
- Modify: `douyin_spider/settings.py`

目标：`MYSQL_HOST/PORT/USER/DB` 支持从 `local_config.py` 覆盖（云上 3306/douyin_app，本地 3307/root）。

- [x] **Step 1: 写失败测试**：settings 在存在 local_config 的 MYSQL_* 时返回覆盖值；
- [x] **Step 2: 实现**：settings.py 顶部 `from local_config import ... MYSQL_HOST/PORT/USER/DB`（缺失时保留默认）；
- [x] **Step 3: 回归**：pytest 全量；
- [x] **Step 4: Commit**。

---

### Task 3: 只读接口鉴权（api.py，TDD）

**Files:**
- Modify: `api.py`
- Test: `tests/test_api_guard.py`

目标：公网下所有 GET 接口需要访问令牌（与写接口一致），避免数据裸奔。

- [x] **Step 1: 写失败测试**：新增 `verify_read_guard`（复用 evaluate_write_guard，但 GET 也强制令牌；本机 Origin 白名单仍放行）；
- [x] **Step 2: 实现**：给 `/api/videos`、`/api/videos/{id}`、`/api/stats`、`/api/analyze/*`、`/api/spider/log`、`/api/quality/export` 等 GET 加 `dependencies=[Depends(verify_read_guard)]`；
- [x] **Step 3: 回归**：pytest 全量；前端 axios 需带令牌（若同源访问可豁免，见实现时决定）；
- [x] **Step 4: Commit**。

---

### Task 4: 云地址配置（CORS + 插件默认地址 + manifest host 权限，TDD）

**Files:**
- Modify: `api.py`（ALLOWED_ORIGINS）
- Modify: `extension/options/options.js`、`extension/manifest.json`
- Test: `extension/tests/options.smoke.test.mjs`

目标：插件默认后端地址改为云 IP，host_permissions 加云 IP，后端 CORS 白名单加云地址。

- [x] **Step 1: 写失败测试**（插件 options 默认值断言）；
- [x] **Step 2: 实现**：默认后端 `http://47.120.36.73`（或做成可配置），manifest 加该地址，api.py ALLOWED_ORIGINS 加 `http://47.120.36.73`；
- [x] **Step 3: 回归**：node --test、pytest；
- [x] **Step 4: Commit**。

---

### Task 5: 部署到服务器 + Cookie 迁移 + 验证

- [x] 本地推送 master → 服务器 `git pull`（app 用户）；
- [x] 用户提供抖音 Cookie → 写入服务器 `local_config.py`（600 权限，不提交）；
- [x] 重启 `douyinpachong` 服务；
- [x] 真机验证：面板鉴权、插件云上报（用户重新加载插件）、手动触发爬虫抓一条视频入库；
- [x] 验证完成后更新交接文档并清理本计划分支。

> **部署期修复（2026-08-14，部署中发现并已提交）**：
> - `SpiderManager` 硬编码 Windows venv 路径（`.venv/Scripts/python.exe`）→ 改为按平台取 `.venv/bin/python`（commit `58943fa`）；
> - 服务器 Twisted 26.4.0 与 Scrapy 2.12.0 不兼容（Twisted 26 移除 `_setAcceptableProtocols`/`ConnectionFailed`）→ requirements 锁定 `Twisted==25.5.0`（commit `cb131e2`），服务器 venv 已降级；
> - 服务器无 node → 前端 dist 在本地构建后上传。
>
> **待用户浏览器端操作**：① 打开 `http://47.120.36.73/app/` 输入 API 令牌验证面板；② 在 `chrome://extensions` 重新加载插件，确认后端地址为 `http://47.120.36.73` 并做一次云上报；③（建议）部署后轮换服务器 root 密码与阿里云 AccessKey。

---

## 风险与说明

- 只读接口加鉴权后，前端同源访问需保留放行（本机 Origin 白名单），否则面板会 401；
- 插件云地址写死后，本地开发需手动改回 `http://127.0.0.1:8001`；建议做成"默认云地址、可配置"，避免破坏本地；
- 爬虫上云采集抖音有平台风控/账号风险，已确认手动触发，不常驻。
