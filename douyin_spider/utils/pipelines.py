import mysql.connector
import logging
from datetime import datetime
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class MySQLPipeline:
    """MySQL 数据存储管道"""

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
        self.connection = mysql.connector.connect(
            host=self.mysql_host,
            port=self.mysql_port,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.mysql_db,
            charset='utf8mb4'
        )
        self.cursor = self.connection.cursor()
        logger.info("MySQL 数据库连接成功")

    def close_spider(self, spider):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            logger.info("MySQL 数据库连接已关闭")

    def process_item(self, item, spider):
        if item.get('publish_time'):
            if isinstance(item['publish_time'], (int, float)):
                item['publish_time'] = datetime.fromtimestamp(item['publish_time'])

        item['crawl_time'] = datetime.now()

        sql = """
            INSERT INTO video_info
            (video_id, video_title, video_desc, author_name, author_id,
             publish_time, like_count, comment_count, share_count, play_count,
             video_url, cover_url, crawl_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                like_count = VALUES(like_count),
                comment_count = VALUES(comment_count),
                share_count = VALUES(share_count),
                play_count = VALUES(play_count)
        """
        try:
            self.cursor.execute(sql, (
                item.get('video_id'),
                item.get('video_title'),
                item.get('video_desc'),
                item.get('author_name'),
                item.get('author_id'),
                item.get('publish_time'),
                item.get('like_count', 0),
                item.get('comment_count', 0),
                item.get('share_count', 0),
                item.get('play_count', 0),
                item.get('video_url'),
                item.get('cover_url'),
                item.get('crawl_time'),
            ))
            self.connection.commit()
            logger.info(f"视频数据存储成功: {item.get('video_id')} - {item.get('video_title')}")
        except Exception as e:
            self.connection.rollback()
            logger.error(f"数据存储失败: {e}")
            raise DropItem(f"MySQL 存储失败: {e}")

        return item
