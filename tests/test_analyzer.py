"""个人分析聚合逻辑单测。"""
from datetime import datetime

from analyzer import build_trend, summarize_rows, top_videos


def make_row(**over):
    row = {
        'video_id': '1',
        'video_title': '标题',
        'author_name': '作者',
        'author_id': 'A1',
        'publish_time': datetime(2026, 5, 12, 14, 13, 52),
        'like_count': 100,
        'comment_count': 10,
        'share_count': 5,
        'play_count': 1000,
        'crawl_time': datetime(2026, 8, 10, 17, 7, 59),
        'update_time': datetime(2026, 8, 10, 17, 7, 59),
    }
    row.update(over)
    return row


def test_summarize_rows_totals():
    rows = [
        make_row(video_id='1', like_count=100, comment_count=10, share_count=5, play_count=1000),
        make_row(video_id='2', like_count=50, comment_count=2, share_count=1, play_count=200),
    ]
    summary = summarize_rows(rows)
    assert summary['total_videos'] == 2
    assert summary['total_likes'] == 150
    assert summary['total_comments'] == 12
    assert summary['total_shares'] == 6
    assert summary['total_plays'] == 1200


def test_summarize_latest_sync_uses_max_update_time():
    rows = [
        make_row(video_id='1', crawl_time=datetime(2026, 1, 1), update_time=datetime(2026, 8, 10)),
        make_row(video_id='2', crawl_time=datetime(2026, 8, 9), update_time=datetime(2026, 6, 1)),
    ]
    assert summarize_rows(rows)['latest_sync'] == datetime(2026, 8, 10)


def test_summarize_latest_sync_falls_back_to_crawl_time_when_update_missing():
    rows = [
        make_row(video_id='1', crawl_time=datetime(2026, 3, 1), update_time=None),
        make_row(video_id='2', crawl_time=datetime(2026, 5, 1), update_time=None),
    ]
    assert summarize_rows(rows)['latest_sync'] == datetime(2026, 5, 1)


def test_summarize_empty_rows():
    summary = summarize_rows([])
    assert summary['total_videos'] == 0
    assert summary['total_likes'] == 0
    assert summary['latest_sync'] is None


def test_summarize_handles_null_counts():
    summary = summarize_rows([make_row(like_count=None, comment_count=None)])
    assert summary['total_likes'] == 0
    assert summary['total_comments'] == 0


def test_build_trend_groups_by_month_asc():
    rows = [
        make_row(video_id='1', publish_time=datetime(2026, 5, 1)),
        make_row(video_id='2', publish_time=datetime(2026, 5, 20)),
        make_row(video_id='3', publish_time=datetime(2026, 3, 15)),
        make_row(video_id='4', publish_time=None),
    ]
    trend = build_trend(rows)
    assert trend == [
        {'month': '2026-03', 'count': 1},
        {'month': '2026-05', 'count': 2},
    ]


def test_top_videos_sorted_by_like_desc_limited():
    rows = [make_row(video_id=str(i), like_count=i) for i in range(15)]
    top = top_videos(rows, limit=5)
    assert [r['video_id'] for r in top] == ['14', '13', '12', '11', '10']
