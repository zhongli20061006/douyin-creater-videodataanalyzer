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
- **深色数据看板**：设计令牌统一（颜色/间距/圆角），Element Plus 深色主题。

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
│   ├── src/pages/         # 看板/队列/视频/收集/质量
│   └── dist/              # 构建产物（后端 /app 提供）
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

## 配置说明

- `local_config.py`（已在 `.gitignore`，不会提交）：`DOUYIN_COOKIES`（浏览器登录抖音后抓取）、`MYSQL_PASSWORD`；
- Cookie 会过期，需要定期更新；参考 `local_config.example.py`。

## 已知限制

- 抖音对「作者作品列表」接口有平台风控（自动化访问返回空数据），因此**作者主页一键收集暂不可用**；请使用「粘贴视频 ID / 文件导入」添加任务；
- 爬虫使用真实浏览器渲染（Playwright 有头模式），后台运行时屏幕上会弹出浏览器窗口，属预期行为。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

## License

待补充（开源协议选择后填写）。
