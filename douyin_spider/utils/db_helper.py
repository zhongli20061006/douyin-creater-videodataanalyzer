# douyin_spider/utils/db_helper.py
"""
MySQL 数据库连接辅助工具
提供连接池管理、单条/批量插入、查询等常用操作
"""

import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MySQLHelper:
    """MySQL 数据库操作助手"""

    def __init__(self, host='localhost', port=3307, user='root',
                 password='', database='douyin_spider', charset='utf8mb4'):
        """
        初始化数据库连接参数
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=DictCursor,
                autocommit=False
            )
            logger.info("MySQL 连接成功")
            return self.connection
        except Exception as e:
            logger.error(f"MySQL 连接失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            logger.info("MySQL 连接已关闭")

    @contextmanager
    def get_cursor(self):
        """上下文管理器，自动处理连接的打开与关闭"""
        conn = None
        cursor = None
        try:
            conn = pymysql.connect(
                host=self.host, port=self.port, user=self.user,
                password=self.password, database=self.database,
                charset=self.charset, cursorclass=DictCursor
            )
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def execute(self, sql: str, params: tuple = None) -> int:
        """
        执行单条 SQL 语句（INSERT/UPDATE/DELETE）
        返回受影响的行数
        """
        with self.get_cursor() as cursor:
            rows = cursor.execute(sql, params)
            return rows

    def executemany(self, sql: str, params_list: List[tuple]) -> int:
        """
        批量执行 SQL 语句
        返回受影响的总行数
        """
        with self.get_cursor() as cursor:
            rows = cursor.executemany(sql, params_list)
            return rows

    def query_one(self, sql: str, params: tuple = None) -> Optional[Dict[str, Any]]:
        """查询单条记录"""
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def query_all(self, sql: str, params: tuple = None) -> List[Dict[str, Any]]:
        """查询多条记录"""
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def insert_video_info(self, video_data: Dict[str, Any]) -> bool:
        """
        插入或更新视频信息（利用 ON DUPLICATE KEY UPDATE）
        """
        sql = """
            INSERT INTO video_info 
                (video_id, video_title, video_desc, author_name, author_id,
                 publish_time, like_count, comment_count, share_count, play_count,
                 video_url, cover_url, crawl_time)
            VALUES 
                (%(video_id)s, %(video_title)s, %(video_desc)s, %(author_name)s, %(author_id)s,
                 %(publish_time)s, %(like_count)s, %(comment_count)s, %(share_count)s, %(play_count)s,
                 %(video_url)s, %(cover_url)s, %(crawl_time)s)
            ON DUPLICATE KEY UPDATE
                video_title = VALUES(video_title),
                video_desc = VALUES(video_desc),
                author_name = VALUES(author_name),
                like_count = VALUES(like_count),
                comment_count = VALUES(comment_count),
                share_count = VALUES(share_count),
                play_count = VALUES(play_count),
                update_time = NOW()
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute(sql, video_data)
            return True
        except Exception as e:
            logger.error(f"插入视频信息失败: {e}, 数据: {video_data}")
            return False

    def batch_insert_video_info(self, video_list: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        批量插入视频信息
        返回 (成功数量, 失败数量)
        """
        success = 0
        fail = 0
        for video in video_list:
            if self.insert_video_info(video):
                success += 1
            else:
                fail += 1
        return success, fail

    def check_video_exists(self, video_id: str) -> bool:
        """检查视频是否已存在于数据库"""
        sql = "SELECT 1 FROM video_info WHERE video_id = %s LIMIT 1"
        result = self.query_one(sql, (video_id,))
        return result is not None

    def get_video_statistics(self, video_id: str) -> Optional[Dict]:
        """获取指定视频的互动统计数据"""
        sql = """
            SELECT like_count, comment_count, share_count, play_count, crawl_time 
            FROM video_info 
            WHERE video_id = %s
        """
        return self.query_one(sql, (video_id,))

    def insert_crawl_log(self, spider_name: str, video_id: str,
                         status: int, error_msg: str = None) -> bool:
        """记录爬取日志"""
        sql = """
            INSERT INTO crawl_log (spider_name, video_id, status, error_msg)
            VALUES (%s, %s, %s, %s)
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute(sql, (spider_name, video_id, status, error_msg))
            return True
        except Exception as e:
            logger.error(f"记录爬取日志失败: {e}")
            return False


# 全局单例（可选）
_db_helper_instance = None


def get_db_helper(host='localhost', port=3306, user='root',
                  password='', database='douyin_spider') -> MySQLHelper:
    """获取 MySQLHelper 单例对象（简单实现，生产环境建议使用连接池）"""
    global _db_helper_instance
    if _db_helper_instance is None:
        _db_helper_instance = MySQLHelper(host, port, user, password, database)
    return _db_helper_instance
