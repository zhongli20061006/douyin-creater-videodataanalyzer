"""浏览器插件数据接收器：字段校验、归一化、批次内去重、部分更新 SQL 构建。

纯逻辑模块（与 quality.py 同模式），api.py 只做薄层调用。
"""
import re
from datetime import datetime
from typing import Any, Optional

MAX_BATCH = 100
VIDEO_ID_RE = re.compile(r'^\d{15,20}$')
SOURCE_URL_RE = re.compile(r'^https://www\.douyin\.com/user/[^/?#]+/?$')
HTTP_URL_RE = re.compile(r'^https?://\S+$')

COUNT_FIELDS = ('like_count', 'comment_count', 'share_count', 'play_count')
TEXT_LIMITS = {
    'video_title': 512,
    'video_desc': 5000,
    'author_name': 128,
    'author_id': 64,
    'video_url': 2048,
    'cover_url': 1024,
}


def validate_video_id(video_id: Any) -> bool:
    """video_id 必须是 15-20 位纯数字字符串。"""
    return isinstance(video_id, str) and bool(VIDEO_ID_RE.match(video_id.strip()))


def validate_source_url(url: Any) -> bool:
    """source_url 必须是抖音用户主页链接。"""
    return isinstance(url, str) and bool(SOURCE_URL_RE.match(url.strip()))


def parse_datetime(value: Any) -> Optional[datetime]:
    """接受 ISO 8601 / 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD'；无效返回 None（不拒绝）。"""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def parse_count(value: Any) -> Optional[int]:
    """接受 int / 数字字符串；负数、小数、非数字返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and re.fullmatch(r'\d+(?:\.\d+)?', value.strip()):
        number = float(value)
    else:
        return None
    if number < 0 or number != int(number):
        return None
    return int(number)
