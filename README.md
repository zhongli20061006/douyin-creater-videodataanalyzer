# 抖音爬虫管理系统

基于 **Scrapy + Redis + MySQL + FastAPI + Vue 3** 的抖音视频数据采集与管理面板。支持批量任务队列、自动连续爬取、数据质量治理与多维度数据导出。

## 功能特性

- **视频爬取**：按视频 ID 批量入队，爬虫连续消费队列直到清空，数据自动入库（含去重更新）；
- **管理面板**（Vue 3 + Element Plus）：
  - 看板：实时统计 + 作者分布/质量分布图表（ECharts）；
  - 队列监控：队列内容、爬虫状态、实时日志（5 秒轮询）；
  - 视频数据：搜索、排序、分页、详情、删除；
  - 收集任务：粘贴 / 文件导入视频 ID（正式入口）；
  - 数据质量：问题报告、一键修正、确认后删除、导出 CSV / Excel；
- **数据质量治理**：入库时过滤空记录与占位页、标题规范化、不完整数据不覆盖已有记录（`INSERT IGNORE`）；
- **深色数据看板**：设计令牌统一（颜色/间距/圆角），Element Plus 深色主题；
- **个人视频数据分析器（浏览器插件版）**：
  - 博主在真实浏览器里用插件采集**自己主页**视频的播放量，浏览自己的视频详情页时
    自动补采点赞/评论/分享；
  - 后端只做「数据接收器」：字段校验 → 按 video_id 去重 → upsert 到 `video_info` 表，
    爬虫/队列/Playwright 不参与此链路；
  - 看板新增「个人分析」页：作者下拉、概览卡（含最近同步时间）、发布趋势、
    互动总量、Top 10 视频。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.13 · Scrapy 2.12 · FastAPI · MySQL · Redis · Playwright |
| 前端 | Vue 3.5 · Vite 8 · TypeScript · Element Plus · Pinia · ECharts |

## 目录结构

```text
.
├── api.py                 # FastAPI 应用与全部接口
├── collector.py           # 作者主页收集（受平台风控限制，见下）
├── quality.py             # 数据质量：分类/统计/删除校验/导出
├── queue_service.py       # 队列条目解析
├── douyin_spider/         # Scrapy 爬虫（管道、中间件、spider）
├── frontend/              # Vue 3 前端（npm 工程）
│   ├── src/pages/         # 看板/队列/视频/收集/质量/个人分析
│   └── dist/              # 构建产物（后端 /app 提供）
├── extension/             # 浏览器插件（个人主页采集，只采自己的数据）
├── local_config.example.py
└── tests/                 # pytest 单元测试
```

## 快速开始

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item local_config.example.py local_config.py   # 填入 Cookie 与 MySQL 密码
# 启动 MySQL 与 Redis 后：
.\run_backend.ps1          # 面板默认 http://localhost:8001
```

首次使用爬虫前安装浏览器：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

### 前端（开发）

```powershell
cd frontend
npm install
npm run dev                # http://localhost:5173/app/，/api 代理到 8001
npm run build              # 生产构建，由后端在 /app 提供服务
```

### 浏览器插件（个人数据采集）

1. 打开 Chrome → `chrome://extensions` → 开启「开发者模式」→「加载已解压的扩展程序」，
   选择 `extension/` 目录；
2. 点击插件图标配置后端地址（默认 `http://127.0.0.1:8001`）；
3. 登录抖音网页版，进入**自己的主页**，点击右下角「开始采集」；
4. 之后正常浏览自己的视频详情页，插件会自动同步点赞/评论/分享。

**合规声明（重要）**：本插件**只能采集当前登录账号自己的主页数据**——
白名单校验确保不在他人主页启用、不在他人视频详情页采集；
请勿用于采集他人主页数据，使用者须自行遵守抖音用户协议与相关法律法规。

**已知限制**：主页自动翻页全量采集（超过 100 条自动分批上报，不截断），
并通过被动网络 hook 补全点赞/评论/分享/发布时间；
浏览详情页时仍可被动补充（hook 未覆盖场景的兜底）；
图文（`/note/`）与收藏数不采集。

## 配置说明

- `local_config.py`（已在 `.gitignore`，不会提交）：`DOUYIN_COOKIES`（浏览器登录抖音后抓取）、`MYSQL_PASSWORD`；
- Cookie 会过期，需要定期更新；参考 `local_config.example.py`。

## 已知限制

- 抖音对「作者作品列表」接口有平台风控（自动化访问返回空数据），因此**后端自动收集暂不可用**；
  个人数据分析器改用浏览器插件，在博主真实浏览器中只采集**自己**主页的数据（见「浏览器插件」一节）；
- 请使用「粘贴视频 ID / 文件导入」添加爬虫任务；
- 爬虫使用真实浏览器渲染（Playwright 有头模式），后台运行时屏幕上会弹出浏览器窗口，属预期行为。

## 合规与用途声明

本项目仅供**学习与研究**用途。使用者须自行遵守：

- 抖音（字节跳动）及相关平台的用户协议、robots.txt 与服务条款；
- 《网络安全法》《数据安全法》《个人信息保护法》及适用的法律法规；
- 不得将本项目用于商业牟利、大规模数据采集或其他违反平台规则的目的。

本项目包含浏览器渲染、Cookie 注入等自动化技术，仅用于技术研究演示。请勿以此规避平台的反爬机制；因使用本项目产生的账号风险、法律风险由使用者自行承担。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

插件解析单测（需先 `cd extension; npm install`）：

```powershell
cd extension
npm test
```

## License

[MIT](LICENSE)
