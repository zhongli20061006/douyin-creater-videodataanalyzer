# 云服务器运维手册（douyinpachong）

> 适用：完整版主仓库已上云后的日常维护。部署时间 2026-08-14。
> 服务器：47.120.36.73（阿里云 ECS 华南2河源，Ubuntu 22.04，2C4G）

## 0. 架构速览

```
浏览器面板 http://47.120.36.73/app/  ─┐
Chrome 插件（douyin.com 页面上报）────┼→ Nginx:80 → uvicorn 127.0.0.1:8001 (systemd: douyinpachong, app 用户)
手动爬虫（/api/spider/start）─────────┘        ├─ MySQL 8.0 (127.0.0.1:3306, 库 douyin_spider, 用户 douyin_app)
部署路径：/opt/douyinpachong                  └─ Redis (127.0.0.1, 队列 douyin:start_urls)
GitHub：zhongli20061006/douyin-creater-videodataanalyzer（分支 main）
```

## 1. 日常必做（按优先级）

### 1.1 凭据轮换
| 凭据 | 位置 | 频率 | 操作 |
|---|---|---|---|
| 抖音 Cookie | 服务器 `/opt/douyinpachong/local_config.py` 的 `DOUYIN_COOKIES` | **约每 2 个月**（sessionid/sid_guard 约 60 天过期） | 浏览器复制新 Cookie → 替换该字典 → `systemctl restart douyinpachong`。过期症状：爬虫日志只拿到兜底/无拦截数据、插件上报的计数为 0 |
| API 令牌 | 同上 `EXTENSION_API_TOKEN` | 泄露即换 | 改值 → 重启服务 → 同步改插件选项页 + 面板头部输入 |
| root 密码 | 阿里云控制台（实例 → 重置密码，需重启实例） | 泄露即换 / 每季度 | — |
| 阿里云 AccessKey | 仅本机/Workbench | 用完即删（RAM） | — |

### 1.2 数据备份（建议 crontab）
```bash
# 每日 03:30 备份，保留 7 天
30 3 * * * mysqldump -h127.0.0.1 -udouyin_app -p"$(cat /root/deploy_secrets)" douyin_spider > /root/backup/douyin_$(date +\%F).sql && find /root/backup -mtime +7 -delete
```
- 备份文件建议同步到 OSS/异地（`ossutil` 或 rclone）；
- Redis 只是队列，`queue_length` 平时为 0，无需持久化备份。

### 1.3 资源巡检（每月）
```bash
df -h                                   # 磁盘（journald / 日志最易吃满）
free -h                                 # 内存（2C4G 紧张：uvicorn+MySQL+Redis+Playwright 并发易 OOM）
systemctl status douyinpachong          # 服务状态
journalctl -u douyinpachong -n 50       # 最近日志
tail -30 /opt/douyinpachong/douyin_spider.log
```

## 2. 发布流程（代码变更上线）

服务器**没有 node**，前端 dist 需本地构建上传；后端纯代码直接 git pull。

1. 本地开发：分支 → TDD → 测试全绿（`pytest tests/` + `node --test` + `npm run build`）；
2. 合并 `main` → `git push origin main`；
3. 服务器（root）：
   ```bash
   su - app -c 'cd /opt/douyinpachong && git pull --ff-only'   # 仅后端改动
   systemctl restart douyinpachong
   ```
4. 若改了前端（`frontend/src`）：本地 `cd frontend && npm run build`，把 `frontend/dist/` 整个目录上传覆盖服务器 `/opt/douyinpachong/frontend/dist/`，`chown -R app:app`，重启；
5. 若改了 Python 依赖：先更新 requirements.txt 并在**本地回归**，服务器 `su - app -c 'cd /opt/douyinpachong && .venv/bin/python -m pip install -r requirements.txt'`。
   > ⚠️ Twisted 必须 `<26`（与 Scrapy 2.12 兼容，见 commit cb131e2）；升级 playwright 后必须 `su - app -c '/opt/douyinpachong/.venv/bin/python -m playwright install chromium'`（浏览器缓存在 `/home/app/.cache/ms-playwright`）。

## 3. 常见故障速查

| 症状 | 原因 | 处理 |
|---|---|---|
| 面板 401/403，数据加载不出 | API 令牌未填/填错 | 面板头部输入 `EXTENSION_API_TOKEN` 值 |
| 插件采集后数据不进库 | ①插件后端地址仍是 127.0.0.1:8001 ②令牌不对 ③插件没重载（manifest 缺云地址权限） | 选项页改 `http://47.120.36.73` + 填令牌 + `chrome://extensions` 重载 + 抖音页 F5 |
| 爬虫启动后日志 `Unhandled error in Deferred` | Twisted 被升到 26.x | `.venv/bin/python -m pip install "twisted==25.5.0"` |
| 爬虫启动报 `.venv/Scripts/python.exe` 不存在 | 用了旧代码 | git pull 到含 58943fa 的版本 |
| Playwright 浏览器不可用 | 浏览器缓存缺失/版本不匹配 | `su - app -c '...playwright install chromium'`；确认 `/home/app/.cache/ms-playwright` 存在 |
| 抓取只入库兜底数据（incomplete） | Cookie 过期 / 抖音风控 | 刷新 Cookie；风控时停止采集，勿连续触发 |
| 服务反复重启 | 代码异常/端口占用/OOM | `journalctl -u douyinpachong -n 100` 看堆栈；OOM 则降低并发 |

## 4. 安全清单

- [ ] 阿里云安全组**只放行 80/443**；22 端口改为仅你的固定 IP，或直接用 Workbench CLI（`workbench connect`）免公网 SSH；
- [ ] 建议上 HTTPS：Nginx 反代已就绪，certbot（Let's Encrypt）即可；上 HTTPS 后同步把 `ALLOWED_ORIGINS`/manifest/插件默认地址改为 `https://47.120.36.73`（需一个域名才能签证书，纯 IP 可用自签或 IP 证书）；
- [ ] 面板/插件令牌与 Cookie 均不写仓库（`local_config.py` 已 gitignore）；
- [ ] 服务器上不要手动改 git 跟踪文件（会被 `git pull` 覆盖）；只改 `local_config.py`。

## 5. 维护命令速查

```bash
# 登录（Workbench CLI，免公网 SSH）
workbench connect --region cn-heyuan --instance-id i-xxx

# 服务
systemctl status|restart|stop douyinpachong
journalctl -u douyinpachong -n 100 --no-pager
journalctl --vacuum-size=200M          # 日志占满磁盘时清理

# 手动触发爬虫（从面板：爬虫复核 → 队列；或 API）
curl -X POST http://127.0.0.1:8001/api/crawl -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" -d '{"video_ids":["<id>"]}'
curl -X POST http://127.0.0.1:8001/api/spider/start -H "X-API-Token: $TOKEN"

# 备份
mysqldump -h127.0.0.1 -udouyin_app -p"$(cat /root/deploy_secrets)" douyin_spider > /root/backup/douyin_$(date +%F).sql
```
