"""定时清理服务：开关/间隔判断、待删选择、备份 CSV 生成（纯逻辑）。"""
import csv
import io
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

CLEANUP_INTERVAL_DAYS = 30
CLEANUP_BATCH_SIZE = 200
CLEANUP_BACKUP_DIR = os.path.join(tempfile.gettempdir(), 'douyin_cleanup_backup')

BACKUP_FIELDS = (
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'collect_count',
    'play_count', 'video_url', 'cover_url', 'crawl_time', 'update_time',
)


def should_run_cleanup(enabled, last_clean_time: Optional[datetime], now: datetime,
                       interval_days: int = CLEANUP_INTERVAL_DAYS) -> bool:
    """开关开启且距上次执行满 interval_days 才执行；last_clean_time 为 None（首次）时执行。"""
    if not enabled:
        return False
    if last_clean_time is None:
        return True
    return (now - last_clean_time) >= timedelta(days=interval_days)


def select_stale_ids(rows: list[dict], batch_size: int = CLEANUP_BATCH_SIZE) -> list[str]:
    """按 update_time 升序取前 batch_size 个 video_id；update_time 缺失排最前。"""
    ordered = sorted(rows, key=lambda r: r.get('update_time') or datetime.min)
    return [str(r['video_id']) for r in ordered[:batch_size]]


def build_backup_csv(rows: list[dict]) -> str:
    """把待删行转 CSV 文本（含全部业务字段，缺失字段留空）。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=BACKUP_FIELDS, extrasaction='ignore')
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in BACKUP_FIELDS})
    return buf.getvalue()
