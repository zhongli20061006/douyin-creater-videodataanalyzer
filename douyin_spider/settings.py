# douyin_spider/settings.py

# 爬虫名称
BOT_NAME = 'douyin_spider'

SPIDER_MODULES = ['douyin_spider.spiders']
NEWSPIDER_MODULE = 'douyin_spider.spiders'

# 遵守 robots.txt（建议设置为 True）
ROBOTSTXT_OBEY = False  # 抖音 robots.txt 限制较严格，开发调试时可关闭

# 并发设置
CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8
CONCURRENT_REQUESTS_PER_IP = 8

# 下载延迟（秒），控制请求频率
DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOADER_MIDDLEWARES = {
    # ... 保留原有中间件 ...
    'douyin_spider.middlewares.PlaywrightMiddleware': 543,  # 放在靠后位置
}
# Cookie 设置
COOKIES_ENABLED = True
# 抖音网页版 Cookie 属于敏感凭据，放在项目根目录 local_config.py（已在 .gitignore 中，不会提交）

# ========== 本地敏感配置（凭据不入 Git）==========
# 复制 local_config.example.py 为 local_config.py 并填入真实值
try:
    from local_config import DOUYIN_COOKIES, MYSQL_PASSWORD  # noqa: F401
except ImportError:
    DOUYIN_COOKIES = {}
    MYSQL_PASSWORD = ''
# 关闭 Telnet 控制台
TELNETCONSOLE_ENABLED = False

# 默认请求头
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# 中间件配置
# douyin_spider/settings.py

DOWNLOADER_MIDDLEWARES = {
    'douyin_spider.middlewares.RandomUserAgentMiddleware': 400,
    'douyin_spider.middlewares.DouyinDownloaderMiddleware': 500,
    'douyin_spider.middlewares.RequestDelayMiddleware': 550,
    'douyin_spider.middlewares.PlaywrightMiddleware': 543,  # 新增
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 600,
}

# 重试设置
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]


ITEM_PIPELINES = {
    'douyin_spider.pipelines.MySQLPipeline': 300,
}

# MySQL 数据库配置（密码来自上方 local_config 导入）
MYSQL_HOST = 'localhost'
MYSQL_PORT = 3307
MYSQL_USER = 'root'
MYSQL_DB = 'douyin_spider'

# ========== 分布式爬虫配置（Scrapy-Redis）==========
# 启用 Redis 调度器
'''
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
# 启用 Redis 去重过滤器
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"
# 持久化爬取队列（爬虫关闭后不清空队列）
SCHEDULER_PERSIST = True
# 优先级队列
SCHEDULER_QUEUE_CLASS = 'scrapy_redis.queue.PriorityQueue'
'''
# Redis 连接配置
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_PARAMS = {
    'password': None,  # 如有密码则填写
    'db': 0,
}
# 从 Redis 读取起始 URL 的 key
REDIS_START_URLS_KEY = 'douyin:start_urls'

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FILE = 'douyin_spider.log'
