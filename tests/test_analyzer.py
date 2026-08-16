"""个人分析聚合逻辑单测。"""
from datetime import datetime, timedelta

from analyzer import analyze_insights, build_play_trend, build_trend, summarize_rows, top_videos


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


NOW = datetime(2026, 8, 16, 12, 0, 0)


def rows_with_days(days_list):
    """按发布天数生成可评分行，play/like/collect 成比例，保证互动率、收藏率可计算。"""
    rows = []
    for i, days in enumerate(days_list, start=1):
        play = i * 100
        rows.append(make_row(
            video_id=str(i),
            publish_time=NOW - timedelta(days=days),
            play_count=play,
            like_count=int(play * 0.1),
            collect_count=int(play * 0.05),
        ))
    return rows


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


def test_summarize_engagement_rates():
    rows = [
        make_row(video_id='1', play_count=200, like_count=20, comment_count=4, share_count=2, collect_count=10),
        make_row(video_id='2', play_count=0, like_count=10, comment_count=0, share_count=0, collect_count=0),
    ]
    summary = summarize_rows(rows)
    assert summary['engagement'] == {
        'like_rate': 0.15,
        'comment_rate': 0.02,
        'share_rate': 0.01,
        'collect_rate': 0.05,
    }


def test_summarize_engagement_none_when_no_play_and_no_like():
    summary = summarize_rows([make_row(video_id='1', play_count=0, like_count=0, comment_count=0, share_count=0, collect_count=0)])
    assert summary['engagement'] == {
        'like_rate': None,
        'comment_rate': None,
        'share_rate': None,
        'collect_rate': None,
    }


def test_summarize_engagement_falls_back_to_like_when_no_play():
    rows = [make_row(video_id='1', play_count=0, like_count=10, comment_count=2, share_count=1, collect_count=3)]
    e = summarize_rows(rows)['engagement']
    assert e['like_rate'] is None
    assert e['comment_rate'] == 0.2
    assert e['share_rate'] == 0.1
    assert e['collect_rate'] == 0.3


def test_summarize_completeness_counts_missing():
    rows = [
        make_row(video_id='1', play_count=0, like_count=10, comment_count=None, share_count=0, publish_time=None),
        make_row(video_id='2', play_count=100, like_count=10, comment_count=1, share_count=1, publish_time=None),
    ]
    c = summarize_rows(rows)['completeness']
    assert c['play'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['like'] == {'missing': 0, 'total': 2, 'missing_rate': 0.0}
    assert c['comment'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['share'] == {'missing': 1, 'total': 2, 'missing_rate': 0.5}
    assert c['publish_time'] == {'missing': 2, 'total': 2, 'missing_rate': 1.0}


def test_build_play_trend():
    rows = [
        make_row(video_id='1', publish_time=datetime(2026, 5, 1), play_count=100),
        make_row(video_id='2', publish_time=datetime(2026, 5, 20), play_count=50),
        make_row(video_id='3', publish_time=datetime(2026, 3, 15), play_count=200),
        make_row(video_id='4', publish_time=datetime(2026, 3, 16), play_count=0),
        make_row(video_id='5', publish_time=None, play_count=999),
    ]
    assert build_play_trend(rows) == [
        {'month': '2026-03', 'plays': 200},
        {'month': '2026-05', 'plays': 150},
    ]


def test_top_videos_sort_by_plays():
    rows = [make_row(video_id=str(i), play_count=i * 10, like_count=100 - i) for i in range(1, 12)]
    top = top_videos(rows, limit=3, sort_by='plays')
    assert [r['video_id'] for r in top] == ['11', '10', '9']


def test_top_videos_sort_by_engagement_puts_zero_play_last():
    rows = [
        make_row(video_id='a', play_count=100, like_count=50),
        make_row(video_id='b', play_count=0, like_count=999),
        make_row(video_id='c', play_count=200, like_count=50),
    ]
    top = top_videos(rows, limit=3, sort_by='engagement')
    assert [r['video_id'] for r in top] == ['a', 'c', 'b']


def test_summarize_total_collects():
    rows = [
        make_row(video_id='1', collect_count=300),
        make_row(video_id='2', collect_count=150),
    ]
    summary = summarize_rows(rows)
    assert summary['total_collects'] == 450


def test_summarize_collect_completeness():
    rows = [
        make_row(video_id='1', collect_count=0),
        make_row(video_id='2', collect_count=200),
        make_row(video_id='3', collect_count=None),
    ]
    c = summarize_rows(rows)['completeness']['collect']
    assert c == {'missing': 2, 'total': 3, 'missing_rate': round(2 / 3, 4)}


def test_top_videos_sort_by_collects():
    rows = [make_row(video_id=str(i), collect_count=i * 3) for i in range(1, 12)]
    top = top_videos(rows, limit=3, sort_by='collects')
    assert [r['video_id'] for r in top] == ['11', '10', '9']


def test_summarize_collect_rate_uses_play_first():
    rows = [make_row(video_id='1', play_count=200, like_count=20, collect_count=10)]
    e = summarize_rows(rows)['engagement']
    assert e['collect_rate'] == 0.05


def test_analyze_insights_insufficient_sample():
    rows = [
        make_row(video_id='1', publish_time=NOW - timedelta(days=1), play_count=100),
        make_row(video_id='2', publish_time=NOW - timedelta(days=2), play_count=200),
    ]
    result = analyze_insights(rows, now=NOW)
    assert result['insufficient_sample'] is True
    assert result['sample_size'] == 2
    assert result['top'] == []
    assert result['bottom'] == []


def test_analyze_insights_skips_missing_publish_time_and_empty_metrics():
    rows = [
        make_row(video_id='1', publish_time=None, play_count=100),
        make_row(video_id='2', publish_time=NOW - timedelta(days=1), play_count=0, like_count=0, comment_count=0, share_count=0, collect_count=0),
    ]
    rows += rows_with_days([1, 2, 3, 4, 5])
    result = analyze_insights(rows, now=NOW)
    assert result['sample_size'] == 5


def test_analyze_insights_bucket_boundaries():
    rows = rows_with_days([0, 7, 8, 30, 31, 90, 91])
    result = analyze_insights(rows, now=NOW)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    assert by_id['1']['maturity_bucket'] == '0-7天'
    assert by_id['2']['maturity_bucket'] == '0-7天'
    assert by_id['3']['maturity_bucket'] == '8-30天'
    assert by_id['4']['maturity_bucket'] == '8-30天'
    assert by_id['5']['maturity_bucket'] == '31-90天'
    assert by_id['6']['maturity_bucket'] == '31-90天'
    assert by_id['7']['maturity_bucket'] == '91天以上'


def test_analyze_insights_top_and_bottom_sorted_by_score():
    rows = rows_with_days([5, 5, 5, 5, 5])
    result = analyze_insights(rows, now=NOW, limit=3)
    assert [item['video_id'] for item in result['top']] == ['5', '4', '3']
    assert [item['video_id'] for item in result['bottom']] == ['1', '2', '3']


def test_analyze_insights_falls_back_to_global_when_bucket_too_small():
    rows = rows_with_days([1, 1, 1, 1, 10, 10])
    result = analyze_insights(rows, now=NOW, limit=10)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    assert by_id['6']['percentiles']['play'] == 91.7


def test_analyze_insights_renormalizes_weights_when_engage_missing():
    rows = rows_with_days([5, 5, 5, 5])
    rows.append(make_row(
        video_id='zero-play',
        publish_time=NOW - timedelta(days=5),
        play_count=0,
        like_count=10,
        collect_count=1,
    ))
    result = analyze_insights(rows, now=NOW, limit=10)
    by_id = {item['video_id']: item for item in result['top'] + result['bottom']}
    item = by_id['zero-play']
    assert item['percentiles']['engage'] is None
    assert item['score'] is not None


def test_analyze_insights_explanation_uses_most_extreme_metric():
    rows = rows_with_days([5, 5, 5, 5])
    rows.append(make_row(
        video_id='zero-play',
        publish_time=NOW - timedelta(days=5),
        play_count=0,
        like_count=100,
        collect_count=0,
    ))
    result = analyze_insights(rows, now=NOW, limit=10)
    top = result['top'][0]
    bottom = result['bottom'][0]
    assert '超过' in top['explanation']
    assert '低于' in bottom['explanation']


def test_analyze_insights_skips_comment_only_rows():
    rows = [
        make_row(
            video_id=str(i),
            publish_time=NOW - timedelta(days=i),
            play_count=0,
            like_count=0,
            comment_count=1,
            share_count=1,
            collect_count=0,
        )
        for i in range(1, 6)
    ]
    result = analyze_insights(rows, now=NOW)
    assert result['insufficient_sample'] is True
    assert result['sample_size'] == 0
    assert result['top'] == []
    assert result['bottom'] == []
