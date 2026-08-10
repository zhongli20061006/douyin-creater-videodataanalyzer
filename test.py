import os
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')

import logging
logging.basicConfig(level=logging.DEBUG)

from scrapy.utils.project import get_project_settings
from douyin_spider.spiders.douyin_video import DouyinVideoSpider

# 加载设置
settings = get_project_settings()
settings.set('LOG_LEVEL', 'DEBUG')

# 手动创建爬虫实例
spider = DouyinVideoSpider()
spider.settings = settings
spider.logger.setLevel(logging.DEBUG)

# 尝试获取起始请求
print("=" * 50)
print("正在尝试生成起始请求...")
print(f"Redis key: {spider.redis_key}")
print(f"Scheduler class: {settings.get('SCHEDULER')}")

try:
    requests = list(spider.start_requests())
    print(f"成功生成 {len(requests)} 个请求")
    for req in requests:
        print(f"  -> {req.url}")
except Exception as e:
    print(f"生成请求时出错: {e}")
    import traceback
    traceback.print_exc()

print("=" * 50)