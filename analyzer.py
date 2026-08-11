"""个人视频数据分析：概览聚合、发布趋势、Top 视频。"""
from collections import Counter
from datetime import datetime
from typing import Any, Optional

TOP_VIDEOS_LIMIT = 10


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def summarize_rows(rows: list[dict]) -> dict:
    """按作者过滤后的概览：总数、总和、最近同步时间（MAX(crawl_time)）。"""
    def total(field: str) -> int:
        return sum(int(r.get(field) or 0) for r in rows)

    crawl_times = [
        _as_datetime(r.get('crawl_time'))
        for r in rows
        if r.get('crawl_time')
    ]
    return {
        'total_videos': len(rows),
        'total_likes': total('like_count'),
        'total_comments': total('comment_count'),
        'total_shares': total('share_count'),
        'total_plays': total('play_count'),
        'latest_sync': max(crawl_times) if crawl_times else None,
    }


def build_trend(rows: list[dict]) -> list[dict]:
    """按 publish_time 的「年-月」分组计数，升序；publish_time 为空的不计入。"""
    counter: Counter = Counter()
    for r in rows:
        pt = _as_datetime(r.get('publish_time'))
        if pt is None:
            continue
        counter[f'{pt.year:04d}-{pt.month:02d}'] += 1
    return [{'month': m, 'count': c} for m, c in sorted(counter.items())]


def top_videos(rows: list[dict], limit: int = TOP_VIDEOS_LIMIT) -> list[dict]:
    """按 like_count 降序取前 limit 条。"""
    ordered = sorted(
        rows,
        key=lambda r: int(r.get('like_count') or 0),
        reverse=True,
    )
    return ordered[:limit]
