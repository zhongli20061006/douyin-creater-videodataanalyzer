# douyin_spider/items.py
import scrapy


class DouyinVideoItem(scrapy.Item):
    """抖音视频基础信息数据模型"""
    # 视频唯一标识
    video_id = scrapy.Field()
    # 视频标题
    video_title = scrapy.Field()
    # 视频描述
    video_desc = scrapy.Field()
    # 作者昵称
    author_name = scrapy.Field()
    # 作者ID
    author_id = scrapy.Field()
    # 发布时间
    publish_time = scrapy.Field()
    # 点赞数
    like_count = scrapy.Field()
    # 评论数
    comment_count = scrapy.Field()
    # 分享/收藏数
    share_count = scrapy.Field()
    # 播放量
    play_count = scrapy.Field()
    # 视频链接
    video_url = scrapy.Field()
    # 封面图链接
    cover_url = scrapy.Field()
    # 爬取时间
    crawl_time = scrapy.Field()