"""浏览器插件数据接收器：字段校验、归一化、批次内去重、部分更新 SQL 构建。

纯逻辑模块（与 quality.py 同模式），api.py 只做薄层调用。
"""
import re
import os
import tempfile
import threading
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


INSERT_COLUMNS = (
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'play_count',
    'video_url', 'cover_url',
)


def dedupe_records(records: list[dict]) -> list[dict]:
    """批次内按 video_id 去重，保留第一条。"""
    seen: set[str] = set()
    result: list[dict] = []
    for record in records:
        video_id = record['video_id']
        if video_id in seen:
            continue
        seen.add(video_id)
        result.append(record)
    return result


def build_upsert(record: dict) -> tuple[str, tuple]:
    """构建部分更新 upsert SQL。

    - INSERT 写入全部 12 字段（None → NULL）；
    - ON DUPLICATE KEY UPDATE 只更新非 None 字段 + crawl_time/update_time，
      因此主页层（play_count 有值、互动为 None）不会覆盖详情页已补的互动数据。
    """
    values = [record.get(c) for c in INSERT_COLUMNS]
    placeholders = ', '.join(['%s'] * len(INSERT_COLUMNS))
    update_cols = [c for c in INSERT_COLUMNS[1:] if record.get(c) is not None]
    updates = [f'{c}=VALUES({c})' for c in update_cols]
    updates.append('crawl_time=NOW()')
    updates.append('update_time=NOW()')
    sql = (
        f'INSERT INTO video_info ({", ".join(INSERT_COLUMNS)}, crawl_time) '
        f'VALUES ({placeholders}, NOW()) '
        f'ON DUPLICATE KEY UPDATE {", ".join(updates)}'
    )
    return sql, tuple(values)


_IDS_FILE_LOCK = threading.Lock()


def merge_ids(existing: list[str], new_ids: list[str]) -> list[str]:
    """去重合并：保留已有顺序，新 ID 追加在末尾；返回新列表。"""
    seen: set[str] = set()
    merged: list[str] = []
    for vid in existing:
        if vid not in seen:
            seen.add(vid)
            merged.append(vid)
    for vid in new_ids:
        if vid not in seen:
            seen.add(vid)
            merged.append(vid)
    return merged


def _read_ids(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def read_ids_file(path: str) -> list[str]:
    """读取 video_ids.txt 全部 ID（去空白行）；文件缺失返回空列表。"""
    return _read_ids(path)


def _write_ids_atomic(path: str, ids: list[str]) -> None:
    """写临时文件 + os.replace 原子替换，避免写一半损坏。"""
    directory = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.video_ids.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ids))
            if ids:
                f.write('\n')
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _lock_ids_file(path: str):
    """跨平台文件锁：fcntl（POSIX）/ msvcrt（Windows）；返回锁句柄。
    锁文件放系统临时目录，避免在项目根残留 .lock。
    """
    import hashlib
    lock_name = 'dy_analyzer_ids_' + hashlib.md5(path.encode('utf-8')).hexdigest() + '.lock'
    lock_path = os.path.join(tempfile.gettempdir(), lock_name)
    fh = open(lock_path, 'a+')
    try:
        import fcntl  # type: ignore
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    except ImportError:
        import msvcrt  # type: ignore
        fh.seek(0)
        if fh.read(1) == '':
            fh.write('\0')
            fh.flush()
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    return fh


def _unlock_ids_file(fh) -> None:
    try:
        import fcntl  # type: ignore
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except ImportError:
        import msvcrt  # type: ignore
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    fh.close()


def append_ids_file(path: str, new_ids: list[str]) -> tuple[int, int]:
    """并发安全地把新 ID 合并进文件：进程内锁 + 文件锁 + 原子替换。
    返回 (新增条数, 合并后总条数)。
    """
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            existing = _read_ids(path)
            merged = merge_ids(existing, new_ids)
            _write_ids_atomic(path, merged)
            return len(merged) - len(existing), len(merged)
        finally:
            _unlock_ids_file(fh)
