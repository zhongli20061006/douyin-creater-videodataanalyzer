"""个人视频数据分析：概览聚合、发布趋势、Top 视频。"""
from collections import Counter
from datetime import datetime
from typing import Any, Optional

TOP_VIDEOS_LIMIT = 10

INSIGHTS_MIN_SAMPLE_SIZE = 5
INSIGHTS_MIN_BUCKET_SIZE = 3
INSIGHTS_MAX_LIMIT = 50
INSIGHTS_WEIGHTS = {'play': 0.5, 'engage': 0.3, 'collect': 0.2}
INSIGHTS_METRIC_LABELS = {'play': '播放量', 'engage': '互动率', 'collect': '收藏率'}


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _rate(numerator: int, denominator: int):
    """比率，分母为 0 返回 None。"""
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def summarize_rows(rows: list[dict]) -> dict:
    """按作者过滤后的概览：总数、总和、最近同步、互动率、数据完整度。"""
    def total(field: str) -> int:
        return sum(int(r.get(field) or 0) for r in rows)

    sync_times = [
        _as_datetime(r.get('update_time') or r.get('crawl_time'))
        for r in rows
        if r.get('update_time') or r.get('crawl_time')
    ]

    completeness: dict = {}
    for field in ('play_count', 'like_count', 'comment_count', 'share_count', 'collect_count', 'publish_time'):
        if field == 'publish_time':
            missing = sum(1 for r in rows if not r.get(field))
        else:
            missing = sum(1 for r in rows if r.get(field) in (None, 0))
        key = field.replace('_count', '')
        completeness[key] = {
            'missing': missing,
            'total': len(rows),
            'missing_rate': round(missing / len(rows), 4) if rows else 0,
        }

    return {
        'total_videos': len(rows),
        'total_likes': total('like_count'),
        'total_comments': total('comment_count'),
        'total_shares': total('share_count'),
        'total_plays': total('play_count'),
        'total_collects': total('collect_count'),
        'latest_sync': max(sync_times) if sync_times else None,
        'engagement': {
            'like_rate': _rate(total('like_count'), total('play_count')),
            # 无播放量时评论/分享率退化为以点赞为分母（用户规则）
            'comment_rate': _rate(
                total('comment_count'),
                total('play_count') or total('like_count'),
            ),
            'share_rate': _rate(
                total('share_count'),
                total('play_count') or total('like_count'),
            ),
            'collect_rate': _rate(
                total('collect_count'),
                total('play_count') or total('like_count'),
            ),
        },
        'completeness': completeness,
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


def build_play_trend(rows: list[dict]) -> list[dict]:
    """按 publish_time 的「年-月」汇总播放量，升序；无发布时间或无播放量不计入。"""
    totals: dict[str, int] = {}
    for r in rows:
        pt = _as_datetime(r.get('publish_time'))
        play = r.get('play_count')
        if pt is None or not play:
            continue
        month = f'{pt.year:04d}-{pt.month:02d}'
        totals[month] = totals.get(month, 0) + int(play)
    return [{'month': m, 'plays': totals[m]} for m in sorted(totals)]


SORT_KEYS = {
    'likes': 'like_count',
    'plays': 'play_count',
    'comments': 'comment_count',
    'shares': 'share_count',
    'collects': 'collect_count',
}


def _sort_value(r: dict, sort_by: str):
    if sort_by == 'engagement':
        play = int(r.get('play_count') or 0)
        if not play:
            return -1
        return int(r.get('like_count') or 0) / play
    return int(r.get(SORT_KEYS.get(sort_by, 'like_count')) or 0)


def top_videos(rows: list[dict], limit: int = TOP_VIDEOS_LIMIT, sort_by: str = 'likes') -> list[dict]:
    """按指定维度降序取前 limit 条；互动率分母为 0 排后。"""
    ordered = sorted(rows, key=lambda r: _sort_value(r, sort_by), reverse=True)
    return ordered[:limit]


def _bucket_for_days(days: int) -> str:
    """按发布天数返回成熟度桶名。"""
    if days <= 7:
        return '0-7天'
    if days <= 30:
        return '8-30天'
    if days <= 90:
        return '31-90天'
    return '91天以上'


def _publish_days(value: Any, now: datetime) -> Optional[int]:
    """解析发布时间并返回距 now 的天数；无效时间返回 None。"""
    pt = _as_datetime(value)
    if pt is None:
        return None
    return max((now.date() - pt.date()).days, 0)


def _insight_metrics(row: dict) -> dict:
    """返回 play/engage/collect 三项原始指标，无法计算的为 None。"""
    play = int(row.get('play_count') or 0)
    like = int(row.get('like_count') or 0)
    collect = int(row.get('collect_count') or 0)
    engage = None
    collect_metric = None
    if play > 0:
        engage = like / play
        collect_metric = collect / play
    elif like > 0:
        collect_metric = collect / like
    return {'play': play, 'engage': engage, 'collect': collect_metric}


def _percentile(values: list, value: float) -> Optional[float]:
    """计算 value 在 values 中的百分位（0-100，保留 1 位小数）。"""
    if not values:
        return None
    less = sum(1 for x in values if x < value)
    equal = sum(1 for x in values if x == value)
    return round(100 * (less + 0.5 * equal) / len(values), 1)


def _explain(percentiles: dict) -> str:
    """取偏离 50 最大的指标生成中文解释。"""
    best_key = None
    best_distance = -1.0
    best_value = None
    for key, value in percentiles.items():
        if value is None:
            continue
        distance = abs(value - 50)
        if distance > best_distance:
            best_key = key
            best_distance = distance
            best_value = value
    if best_key is None:
        return '数据不足'
    label = INSIGHTS_METRIC_LABELS[best_key]
    if best_value >= 50:
        return f'{label}超过同发布时长视频中 {best_value}%'
    return f'{label}低于同发布时长视频中 {best_value}%'


def analyze_insights(rows: list[dict], now: Optional[datetime] = None, limit: int = 10) -> dict:
    """按成熟度分桶 + 多指标百分位识别潜力爆款与异常偏低视频。"""
    if now is None:
        now = datetime.now()
    limit = max(1, min(int(limit), INSIGHTS_MAX_LIMIT))

    cleaned = []
    for row in rows:
        days = _publish_days(row.get('publish_time'), now)
        if days is None:
            continue
        count_fields = ('play_count', 'like_count', 'collect_count')
        if all(row.get(field) in (None, 0) for field in count_fields):
            continue
        metrics = _insight_metrics(row)
        cleaned.append({
            'video_id': row.get('video_id'),
            'video_title': row.get('video_title'),
            'publish_time': row.get('publish_time'),
            'days_since_publish': days,
            'maturity_bucket': _bucket_for_days(days),
            'play_count': int(row.get('play_count') or 0),
            'engage_rate': round(metrics['engage'], 4) if metrics['engage'] is not None else None,
            'collect_rate': round(metrics['collect'], 4) if metrics['collect'] is not None else None,
            'metrics': metrics,
        })

    if len(cleaned) < INSIGHTS_MIN_SAMPLE_SIZE:
        return {
            'sample_size': len(cleaned),
            'insufficient_sample': True,
            'top': [],
            'bottom': [],
            'generated_at': now.isoformat(timespec='seconds'),
        }

    bucket_items: dict = {}
    for item in cleaned:
        bucket_items.setdefault(item['maturity_bucket'], []).append(item)

    def pool_values(pool: list, key: str) -> list:
        return [item['metrics'][key] for item in pool if item['metrics'][key] is not None]

    scored = []
    for item in cleaned:
        pool = bucket_items[item['maturity_bucket']]
        if len(pool) < INSIGHTS_MIN_BUCKET_SIZE:
            pool = cleaned
        percentiles = {}
        for key in INSIGHTS_WEIGHTS:
            value = item['metrics'][key]
            percentiles[key] = _percentile(pool_values(pool, key), value) if value is not None else None
        available_weights = {key: INSIGHTS_WEIGHTS[key] for key in percentiles if percentiles[key] is not None}
        total_weight = sum(available_weights.values())
        if total_weight == 0:
            continue
        score = sum(INSIGHTS_WEIGHTS[key] * percentiles[key] for key in available_weights) / total_weight
        scored.append({
            'video_id': item['video_id'],
            'video_title': item['video_title'],
            'publish_time': item['publish_time'],
            'days_since_publish': item['days_since_publish'],
            'maturity_bucket': item['maturity_bucket'],
            'play_count': item['play_count'],
            'engage_rate': item['engage_rate'],
            'collect_rate': item['collect_rate'],
            'score': round(score, 1),
            'percentiles': percentiles,
            'explanation': _explain(percentiles),
        })

    top = sorted(scored, key=lambda x: (-x['score'], x['video_id'] or ''))[:limit]
    bottom = sorted(scored, key=lambda x: (x['score'], x['video_id'] or ''))[:limit]
    return {
        'sample_size': len(cleaned),
        'insufficient_sample': False,
        'top': top,
        'bottom': bottom,
        'generated_at': now.isoformat(timespec='seconds'),
    }
