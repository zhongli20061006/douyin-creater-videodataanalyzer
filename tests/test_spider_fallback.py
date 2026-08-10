"""修复：兜底（页面异常）数据必须标记为不完整，避免覆盖已有完整记录。"""
import scrapy
from scrapy.http import TextResponse

from douyin_spider.spiders.douyin_video import DouyinVideoSpider


def make_spider():
    spider = DouyinVideoSpider()
    spider.redis_client = None  # 队列为空，_chain_next 不会产生请求
    return spider


def test_parse_video_page_fallback_marks_item_incomplete():
    spider = make_spider()
    response = TextResponse(
        url='https://www.douyin.com/video/999',
        body=b'<html><head><title>Test Title</title></head><body></body></html>',
        encoding='utf-8',
        request=scrapy.Request(url='https://www.douyin.com/video/999'),
    )

    results = list(spider.parse_video_page(response))

    assert len(results) == 1
    assert results[0]['video_id'] == '999'
    assert results[0].get('incomplete') is True
