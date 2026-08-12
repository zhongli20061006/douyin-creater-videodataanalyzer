# 抖音个人视频数据分析器 - 后端鉴权与绑定加固设计

日期：2026-08-11
状态：设计已获用户拍板（决策 1 选 A：绑定 127.0.0.1 + 令牌双保险；决策 2 选 A：令牌未配置时 fail-closed 拒绝），本文件为实施真源。

前置设计：`docs/superpowers/specs/2026-08-11-personal-analyzer-extension-design.md`（MVP）

## 1. 背景与目标

现状风险（本窗口取证）：
- 后端启动入口默认 `--host 0.0.0.0`（`run_backend.ps1` / `start_server.py`），局域网任意设备可访问；
- CORS 为 `allow_origins=['*']` + `allow_credentials=True`，任意网站可跨域读取看板接口响应（数据泄露）；
- 全部写接口（扩展接收、id 文件、爬虫/队列控制、质量修复/删除）无鉴权，用户浏览任意网页时该网页脚本即可向本机 8001 POST 假数据或触发爬虫（drive-by localhost 写攻击）；
- 注意：仅绑定 127.0.0.1 挡不住用户浏览器内的 drive-by 写攻击，故令牌是必须项。

目标（本轮）：
- 后端默认绑定 127.0.0.1（不做局域网访问）；
- CORS 收紧为白名单；
- 扩展写接口要求 API 令牌（fail-closed：未配置令牌一律拒绝并明确提示）；
- 扩展选项页支持配置令牌，上报请求携带 `X-API-Token`；
- README 与 `local_config.example.py` 同步更新。

## 2. 用户已拍板的决策

### 决策 A：网络形态
- **采用**：不需要局域网访问。后端绑定 127.0.0.1 + 令牌双保险；本机 Chrome 扩展与看板不受影响，局域网其他设备无法打开看板。
- 备选（被拒）：保持 0.0.0.0 + 令牌。看板可跨设备访问，但令牌成为局域网内唯一防线。

### 决策 B：令牌未配置时的行为
- **采用**：fail-closed。未配置 `EXTENSION_API_TOKEN` 时，扩展写接口一律拒绝（503 + 明确提示「请先配置 API 令牌」）。
- 备选（被拒）：fail-open 放行。零打扰但留下后门，drive-by 注入仍可发生。

## 3. 实现设计

### 3.1 令牌配置（owner：`local_config.py` + `api.py` 读取）

- `local_config.py` 新增 `EXTENSION_API_TOKEN = '<随机串>'`（该文件已 gitignore，勿提交）；
- `local_config.example.py` 增加同名占位符与注释；
- `api.py` 启动时读取：`try: from local_config import EXTENSION_API_TOKEN except Exception: EXTENSION_API_TOKEN = ''`；
  模块级变量 `EXTENSION_API_TOKEN` 供守卫依赖读取（测试可 monkeypatch）。

### 3.2 纯函数（owner：`extension_receiver.py`，全部可单测）

- `is_valid_token(provided, expected) -> bool`：字符串相等比较；`expected` 为空一律返回 `False`（fail-closed 基础）；
- `is_allowed_origin(origin, allowed_origins) -> bool`：origin 规范化（去尾部 `/`、host 小写）后是否在白名单；
- `evaluate_write_guard(origin, provided_token, expected_token, allowed_origins) -> tuple[bool, Optional[int], Optional[str]]`：
  返回 `(allowed, status_code, reason)`，规则按顺序：
  1. `origin` 在白名单 → `(True, None, None)`；
  2. `expected_token` 为空 → `(False, 503, '后端未配置 API 令牌（local_config.py 的 EXTENSION_API_TOKEN）')`；
  3. `provided_token` 为空 → `(False, 403, '来源不被允许且未提供 API 令牌')`；
  4. `provided_token != expected_token` → `(False, 401, 'API 令牌无效')`；
  5. 其余 → `(True, None, None)`。

### 3.3 API 守卫（owner：`api.py` 薄层）

- `ALLOWED_ORIGINS = ['http://127.0.0.1:8001', 'http://localhost:8001', 'http://localhost:5173']`（Vite dev）；
- 依赖函数 `verify_write_guard(origin, x_api_token)`：调用 `evaluate_write_guard`，不通过则 `raise HTTPException(status_code=..., detail=...)`；
- 应用于全部写接口：`POST /api/extension/videos`、`POST/PUT /api/extension/ids`、`POST /api/crawl`、
  `POST /api/spider/start`、`POST /api/spider/stop`、`POST /api/collect/author`、
  `POST /api/quality/fix`、`POST /api/quality/delete`、`DELETE /api/videos/{video_id}`；
- 读接口（GET）不校验，靠 CORS 白名单兜底——作为已知边界写入 README 与本节。

### 3.4 CORS 与绑定

- `CORSMiddleware.allow_origins` 改为上述白名单（保留 `allow_credentials=True`，白名单 + 反射 Origin）；
- `run_backend.ps1` / `start_server.py` 默认 host 改为 `127.0.0.1`（保留 `--host` 参数可覆盖，供将来需要时手动开放）。

### 3.5 扩展（owner：`options.html` / `options.js` / `collect.js`）

- 选项页新增「API 令牌」输入框，存 `chrome.storage.local` 键 `apiToken`，保存/重置一并处理；
- `getConfig()` 读取 `apiToken`；
- `report()` / `reportIds()` 请求头增加 `X-API-Token: <apiToken>`；
- 上报收到 401/403/503 时，toast/日志给出明确提示「后端拒绝了请求：请检查 API 令牌配置（选项页与 local_config.py 一致）」。

### 3.6 前端

- 无需改动：看板与后端同源，Origin 在白名单内，收集页编辑/爬虫按钮照常工作。

## 4. 测试策略（T2 严格 TDD）

- `tests/test_extension_receiver.py` 新增：
  - `is_valid_token`：匹配 / 不匹配 / expected 为空 / provided 为空；
  - `is_allowed_origin`：白名单命中（含尾斜杠、host 大小写）/ 未命中 / None；
  - `evaluate_write_guard` 全 5 分支。
- 新建 `tests/test_api_guard.py`：直接调用 `api.verify_write_guard`（monkeypatch `api.EXTENSION_API_TOKEN`），断言 `HTTPException` 的 status/detail 与放行路径。
- 扩展：
  - `extension/tests/collect.smoke.test.mjs`：断言上报请求头含 `X-API-Token`；
  - 新建 `extension/tests/options.smoke.test.mjs`：选项页保存/重置包含 `apiToken`。
- 回归：pytest 全量、`node --test`、`npm run build`。
- 端到端：重启后端后用 curl 做 无令牌→401/403、错令牌→401、带令牌→成功（重启服务属运行状态变更，先征得用户同意）。
- 说明：`.venv` 未装 httpx，FastAPI TestClient 不可用；为避免引入新依赖，守卫行为在纯函数层 + 依赖函数直接调用层覆盖，路由接线由重启后 curl 实测证明。

## 5. 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `extension_receiver.py` | `is_valid_token` / `is_allowed_origin` / `evaluate_write_guard` 纯函数 | 修改 |
| `api.py` | 令牌读取、`ALLOWED_ORIGINS`、`verify_write_guard` 依赖、路由装饰、CORS 白名单 | 修改 |
| `run_backend.ps1` / `start_server.py` | 默认 host `127.0.0.1` | 修改 |
| `local_config.example.py` | `EXTENSION_API_TOKEN` 占位 | 修改 |
| `extension/options/options.html` / `options.js` | `apiToken` 输入/保存/重置 | 修改 |
| `extension/content/collect.js` | `X-API-Token` 头 + 401/403/503 提示 | 修改 |
| `tests/test_extension_receiver.py` | 纯函数测试 | 修改 |
| `tests/test_api_guard.py` | 守卫依赖测试 | 新建 |
| `extension/tests/collect.smoke.test.mjs` | 上报头断言 | 修改 |
| `extension/tests/options.smoke.test.mjs` | 选项页保存/重置 | 新建 |
| `README.md` / `extension/README.md` | 安全说明与配置 | 修改 |

## 6. 非目标

- 不引入登录/用户体系、角色权限；
- 不做令牌加密存储与轮换（本地个人工具，文件即凭据，README 如实声明）；
- 不改数据库结构与 `video_ids.txt` 格式；
- 读接口不加令牌（CORS 白名单兜底，作为已知边界）；
- 不安装新依赖（httpx / TestClient）；
- 不做速率限制（现有批量上限保持不变）。

## 7. 实施阶段

1. 纯函数 + pytest（RED → GREEN）；
2. `api.py` 守卫接线 + `tests/test_api_guard.py`；
3. 扩展选项页 + `collect.js` 头 + jsdom 测试；
4. 启动脚本 / CORS / `local_config.example.py` / README；
5. 全量回归（pytest / node --test / npm run build）；
6. 用户确认后重启后端，curl 正/负路径实测；
7. 用户确认后提交（分支 `codex/personal-analyzer-extension`）。

每阶段独立验证，完成后再进入下一阶段。
