"""数据质量：扫描分类、概览统计、修正、删除校验与 CSV 导出。"""
import csv
import io
from datetime import datetime, timedelta

STALE_DAYS = 90
MAX_DELETE_IDS = 200
PLACEHOLDER_MARKERS = ('在抖音记录美好生活',)
DELETABLE_ISSUES = ('empty', 'placeholder', 'stale')

ISSUE_LABELS = {
    'empty': '疑似无效（标题与作者均为空）',
    'placeholder': '占位页标题',
    'stale': '陈旧未更新',
    'missing_author': '作者缺失（保留）',
}

EXPORT_COLUMNS = [
    'video_id', 'video_title', 'video_desc', 'author_name', 'author_id',
    'publish_time', 'like_count', 'comment_count', 'share_count', 'play_count',
    'video_url', 'cover_url', 'crawl_time', 'update_time',
]

ISSUE_FIELDS = [
    'video_id', 'video_title', 'author_name', 'author_id',
    'like_count', 'comment_count', 'share_count', 'play_count',
    'publish_time', 'crawl_time', 'update_time',
]


def normalize_title(title):
    if title is None:
        return ''
    return ' '.join(str(title).split())


def is_placeholder_title(title):
    if not title:
        return False
    return any(marker in title for marker in PLACEHOLDER_MARKERS)


def is_empty_record(row):
    title = (row.get('video_title') or '').strip()
    author = (row.get('author_name') or '').strip()
    return not title and not author


def is_stale(row, now=None):
    now = now or datetime.now()
    update_time = row.get('update_time')
    if not update_time:
        return False
    if isinstance(update_time, str):
        try:
            update_time = datetime.fromisoformat(update_time)
        except ValueError:
            return False
    return (now - update_time) > timedelta(days=STALE_DAYS)


def classify_row(row):
    issues = []
    if is_empty_record(row):
        issues.append('empty')
    if is_placeholder_title(row.get('video_title')):
        issues.append('placeholder')
    if is_stale(row):
        issues.append('stale')
    title_ok = (row.get('video_title') or '').strip()
    author_missing = not (row.get('author_name') or '').strip()
    if title_ok and author_missing:
        issues.append('missing_author')
    return issues


def summarize(rows):
    return {
        'total': len(rows),
        'distinct_video_ids': len({r.get('video_id') for r in rows}),
        'authors': len({r.get('author_id') for r in rows if r.get('author_id')}),
        'latest_update': max((r.get('update_time') for r in rows), default=None),
        'issue_counts': {
            label: sum(1 for r in rows if label in classify_row(r))
            for label in ISSUE_LABELS
        },
    }


def issue_view(row):
    view = {f: row.get(f) for f in ISSUE_FIELDS}
    view['issue_types'] = classify_row(row)
    return view
