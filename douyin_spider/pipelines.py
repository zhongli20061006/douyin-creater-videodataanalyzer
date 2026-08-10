import mysql.connector
import logging
from datetime import datetime
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


def build_insert_params(item):
    """把 item 转成入库参数字典，缺字段时补默认值，避免兜底数据触发 KeyError。"""
    return {
        'video_id': item.get('video_id', ''),
        'video_title': normalize_title(item.get('video_title')),
        'video_desc': normalize_title(item.get('video_desc')),
        'author_name': item.get('author_name', ''),
        'author_id': item.get('author_id', ''),
        'publish_time': item.get('publish_time'),
        'like_count': item.get('like_count', 0),
        'comment_count': item.get('comment_count', 0),
        'share_count': item.get('share_count', 0),
        'play_count': item.get('play_count', 0),
        'video_url': item.get('video_url', ''),
        'cover_url': item.get('cover_url', ''),
        'crawl_time': item.get('crawl_time') or datetime.now(),
    }


def should_insert_ignore(item):
    """兜底产生的『不完整』数据只能 INSERT IGNORE，绝不覆盖已有完整记录。"""
    return item.get('incomplete') is True


PLACEHOLDER_MARKERS = ('在抖音记录美好生活',)


def normalize_title(title):
    """标题规范化：去首尾空白、合并连续空白/换行。"""
    if title is None:
        return ''
    return ' '.join(str(title).split())


def is_placeholder_title(title):
    """占位页标题（无效视频页特征）判断。"""
    if not title:
        return False
    return any(marker in title for marker in PLACEHOLDER_MARKERS)


def should_skip_item(item):
    """标题与作者均为空，或标题为占位页 → 跳过不建行。"""
    title = (item.get('video_title') or '').strip()
    author = (item.get('author_name') or '').strip()
    return (not title and not author) or is_placeholder_title(item.get('video_title'))


class MySQLPipeline:
    def __init__(self, mysql_host, mysql_port, mysql_user, mysql_password, mysql_db):
        self.mysql_host = mysql_host
        self.mysql_port = mysql_port
        self.mysql_user = mysql_user
        self.mysql_password = mysql_password
        self.mysql_db = mysql_db
        self.connection = None
        self.cursor = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mysql_host=crawler.settings.get('MYSQL_HOST', 'localhost'),
            mysql_port=crawler.settings.get('MYSQL_PORT', 3307),
            mysql_user=crawler.settings.get('MYSQL_USER', 'root'),
            mysql_password=crawler.settings.get('MYSQL_PASSWORD', ''),
            mysql_db=crawler.settings.get('MYSQL_DB', 'douyin_spider'),
        )

    def open_spider(self, spider):
        try:
            self.connection = mysql.connector.connect(
                host=self.mysql_host,
                port=self.mysql_port,
                user=self.mysql_user,
                password=self.mysql_password,
                database=self.mysql_db,
                charset='utf8mb4'
            )
            self.cursor = self.connection.cursor(dictionary=True)
            logger.info("✅ MySQL 连接成功")
        except Exception as e:
            logger.error(f"❌ MySQL 连接失败: {e}")
            self.connection = None

    def close_spider(self, spider):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def process_item(self, item, spider):
        if should_skip_item(item):
            raise DropItem(f"跳过无效记录（空记录或占位页）: {item.get('video_id', '')}")
        if not self.connection:
            raise DropItem("数据库连接不可用，丢弃 Item")
        upsert_sql = """
              INSERT INTO video_info
              (video_id, video_title, video_desc, author_name, author_id,
               publish_time, like_count, comment_count, share_count, play_count,
               video_url, cover_url, crawl_time)
              VALUES (%(video_id)s, %(video_title)s, %(video_desc)s, %(author_name)s, %(author_id)s, \
                      %(publish_time)s, %(like_count)s, %(comment_count)s, %(share_count)s, %(play_count)s, \
                      %(video_url)s, %(cover_url)s, %(crawl_time)s) ON DUPLICATE KEY \
              UPDATE \
                  video_title = \
              VALUES (video_title), video_desc = \
              VALUES (video_desc), author_name = \
              VALUES (author_name), author_id = \
              VALUES (author_id), publish_time = \
              VALUES (publish_time), like_count = \
              VALUES (like_count), comment_count = \
              VALUES (comment_count), share_count = \
              VALUES (share_count), play_count = \
              VALUES (play_count), video_url = \
              VALUES (video_url), cover_url = \
              VALUES (cover_url), update_time = NOW() \
              """
        insert_ignore_sql = """
              INSERT IGNORE INTO video_info
              (video_id, video_title, video_desc, author_name, author_id,
               publish_time, like_count, comment_count, share_count, play_count,
               video_url, cover_url, crawl_time)
              VALUES (%(video_id)s, %(video_title)s, %(video_desc)s, %(author_name)s, %(author_id)s, \
                      %(publish_time)s, %(like_count)s, %(comment_count)s, %(share_count)s, %(play_count)s, \
                      %(video_url)s, %(cover_url)s, %(crawl_time)s)
              """
        sql = insert_ignore_sql if should_insert_ignore(item) else upsert_sql
        try:
            item['crawl_time'] = datetime.now()
            self.cursor.execute(sql, build_insert_params(item))
            self.connection.commit()
            logger.info(f"✅ 数据入库: {item['video_id']}")
            return item
        except Exception as e:
            self.connection.rollback()
            logger.error(f"入库失败: {e}")
            raise DropItem(f"MySQL 错误: {e}")
