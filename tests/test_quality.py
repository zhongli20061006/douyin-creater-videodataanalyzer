"""数据质量模块单元测试。"""
from datetime import datetime, timedelta

from quality import (
    STALE_DAYS,
    classify_row,
    summarize,
)


def make_row(**over):
    row = {
        'video_id': '1',
        'video_title': '标题',
        'video_desc': '描述',
        'author_name': '作者',
        'author_id': 'A1',
        'publish_time': datetime(2026, 1, 1),
        'like_count': 1,
        'comment_count': 1,
        'share_count': 1,
        'play_count': 0,
        'video_url': 'u',
        'cover_url': 'c',
        'crawl_time': datetime(2026, 5, 20),
        'update_time': datetime(2026, 8, 10),
    }
    row.update(over)
    return row


def test_classify_empty_record():
    row = make_row(video_title='', author_name='')
    assert 'empty' in classify_row(row)


def test_classify_placeholder():
    row = make_row(video_title='在抖音记录美好生活 - 抖音')
    assert 'placeholder' in classify_row(row)


def test_classify_stale():
    row = make_row(update_time=datetime.now() - timedelta(days=STALE_DAYS + 1))
    assert 'stale' in classify_row(row)


def test_classify_missing_author_only():
    row = make_row(author_name='')
    issues = classify_row(row)
    assert 'missing_author' in issues
    assert 'empty' not in issues


def test_classify_clean_row_has_no_issues():
    assert classify_row(make_row()) == []


def test_summarize_counts():
    rows = [
        make_row(video_id='1'),
        make_row(video_id='2', video_title='', author_name=''),
    ]
    summary = summarize(rows)
    assert summary['total'] == 2
    assert summary['distinct_video_ids'] == 2
    assert summary['authors'] == 1
    assert summary['issue_counts']['empty'] == 1
