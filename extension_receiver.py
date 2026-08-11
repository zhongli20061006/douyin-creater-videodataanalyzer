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


def normalize_record(raw: dict) -> tuple[Optional[dict], Optional[str]]:
    """校验并归一化单条记录；返回 (record, None) 或 (None, reason)。

    字段语义：count 字段 None 表示「本批未采集」，upsert 时跳过更新；
    文本字段 None/缺失 → 空串；publish_time 无效值 → None（不拒绝）。
    """
    video_id = raw.get('video_id') or ''
    video_id = video_id.strip() if isinstance(video_id, str) else ''
    if not validate_video_id(video_id):
        return None, 'video_id 必须为 15-20 位数字'

    record: dict[str, Any] = {'video_id': video_id}
    for field in TEXT_LIMITS:
        value = raw.get(field)
        if value is None:
            record[field] = ''
        elif isinstance(value, str):
            cleaned = value.strip()
            if len(cleaned) > TEXT_LIMITS[field]:
                return None, f'{field} 长度超限'
            record[field] = cleaned
        else:
            return None, f'{field} 必须是字符串'

    record['publish_time'] = parse_datetime(raw.get('publish_time'))

    for field in COUNT_FIELDS:
        value = raw.get(field)
        if value is None:
            record[field] = None
            continue
        parsed = parse_count(value)
        if parsed is None:
            return None, f'{field} 必须是非负整数'
        record[field] = parsed

    for field in ('video_url', 'cover_url'):
        url = record[field]
        if url and not HTTP_URL_RE.match(url):
            return None, f'{field} 必须是 http(s) 链接'
    return record, None


def validate_batch(payload: dict) -> tuple[list[dict], list[dict]]:
    """整批校验：source_url、长度上限、author 一致性、逐条校验。
    返回 (valid_records, rejected)；批次级错误以 rejected 单条 reason 表达。
    """
    source_url = payload.get('source_url') or ''
    if not validate_source_url(source_url):
        return [], [{'video_id': '', 'reason': 'source_url 必须是抖音用户主页链接'}]

    videos = payload.get('videos')
    if not isinstance(videos, list) or not (1 <= len(videos) <= MAX_BATCH):
        return [], [{'video_id': '', 'reason': f'videos 必须是 1-{MAX_BATCH} 条'}]

    author_ids = {
        str(v.get('author_id', '')).strip()
        for v in videos
        if isinstance(v, dict) and v.get('author_id')
    }
    if len(author_ids) > 1:
        return [], [{'video_id': '', 'reason': '同一批次所有记录的 author_id 必须一致'}]

    valid: list[dict] = []
    rejected: list[dict] = []
    for v in videos:
        if not isinstance(v, dict):
            rejected.append({'video_id': '', 'reason': '记录必须是对象'})
            continue
        record, reason = normalize_record(v)
        if record is None:
            rejected.append({
                'video_id': str(v.get('video_id', ''))[:64],
                'reason': reason or '记录校验失败',
            })
        else:
            valid.append(record)
    return valid, rejected
