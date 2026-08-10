# start_spider.py
import json
import os
import redis
import argparse
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

# 强制设置项目环境变量
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')

from douyin_spider.spiders.douyin_video import DouyinVideoSpider


class DouyinSpiderStarter:
    def __init__(self, redis_host='localhost', redis_port=6379, redis_password=None, redis_db=0):
        self.redis_client = redis.Redis(
            host=redis_host, port=redis_port, password=redis_password, db=redis_db, decode_responses=True
        )
        self.redis_key = 'douyin:start_urls'

    def push_video_url(self, video_url):
        task = json.dumps({'url': video_url, 'type': 'video'})
        self.redis_client.lpush(self.redis_key, task)
        print(f"✅ 已推送视频任务: {video_url}")

    def push_user_url(self, user_url):
        task = json.dumps({'url': user_url, 'type': 'user'})
        self.redis_client.lpush(self.redis_key, task)
        print(f"✅ 已推送用户任务: {user_url}")

    def push_batch_videos(self, video_ids):
        for vid in video_ids:
            self.push_video_url(f"https://www.douyin.com/video/{vid}")

    def get_queue_length(self):
        return self.redis_client.llen(self.redis_key)

    def clear_queue(self):
        self.redis_client.delete(self.redis_key)
        print("🗑️ Redis 队列已清空")

    def start_spider(self):
        settings = get_project_settings()
        settings.set('LOG_LEVEL', 'DEBUG')

        pipelines = settings.getdict('ITEM_PIPELINES')
        print(f"✅ 加载管道: {pipelines}")
        print(f"✅ Redis key: {self.redis_key}")
        print(f"✅ 当前队列长度: {self.get_queue_length()}")

        process = CrawlerProcess(settings)
        process.crawl(DouyinVideoSpider)
        process.start()

        print("✅ 爬虫进程已结束")

def main():
    parser = argparse.ArgumentParser(description='抖音分布式爬虫启动器')
    parser.add_argument('--mode', choices=['push', 'start', 'both'], default='both')
    parser.add_argument('--video-id', type=str, help='单个视频ID')
    parser.add_argument('--video-ids', nargs='+', help='批量视频ID')
    parser.add_argument('--user-url', type=str, help='用户主页URL')
    parser.add_argument('--redis-host', default='localhost')
    parser.add_argument('--redis-port', type=int, default=6379)
    parser.add_argument('--clear', action='store_true', help='清空队列')
    args = parser.parse_args()

    starter = DouyinSpiderStarter(redis_host=args.redis_host, redis_port=args.redis_port)

    if args.clear:
        starter.clear_queue()

    if args.mode in ('push', 'both'):
        if args.video_id:
            starter.push_video_url(f"https://www.douyin.com/video/{args.video_id}")
        if args.video_ids:
            starter.push_batch_videos(args.video_ids)
        if args.user_url:
            starter.push_user_url(args.user_url)
        print(f"📊 当前 Redis 队列长度: {starter.get_queue_length()}")

    if args.mode in ('start', 'both'):
        print("🚀 正在启动分布式爬虫...")
        starter.start_spider()


if __name__ == '__main__':
    main()