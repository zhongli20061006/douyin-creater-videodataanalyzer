"""定时清理服务：开关/间隔判断、待删选择、备份生成（纯逻辑）。"""
from datetime import datetime, timedelta

from cleanup_service import (
    CLEANUP_BATCH_SIZE,
    CLEANUP_INTERVAL_DAYS,
    build_backup_csv,
    select_stale_ids,
    should_run_cleanup,
)


def test_constants():
    assert CLEANUP_INTERVAL_DAYS == 30
    assert CLEANUP_BATCH_SIZE == 200


def test_should_run_cleanup_disabled():
    assert should_run_cleanup(False, None, datetime(2026, 8, 12)) is False


def test_should_run_cleanup_first_time_enabled():
    assert should_run_cleanup(True, None, datetime(2026, 8, 12)) is True


def test_should_run_cleanup_not_due():
    now = datetime(2026, 8, 12)
    assert should_run_cleanup(True, now - timedelta(days=29), now) is False


def test_should_run_cleanup_due():
    now = datetime(2026, 8, 12)
    assert should_run_cleanup(True, now - timedelta(days=30), now) is True


def test_select_stale_ids_asc_order():
    rows = [
        {'video_id': 'c', 'update_time': datetime(2026, 8, 12)},
        {'video_id': 'a', 'update_time': datetime(2026, 8, 1)},
        {'video_id': 'b', 'update_time': datetime(2026, 8, 10)},
    ]
    assert select_stale_ids(rows, batch_size=2) == ['a', 'b']


def test_select_stale_ids_less_than_batch():
    rows = [{'video_id': 'x', 'update_time': None}]
    assert select_stale_ids(rows, batch_size=5) == ['x']


def test_select_stale_ids_missing_time_sorted_first():
    rows = [
        {'video_id': 'n', 'update_time': None},
        {'video_id': 'y', 'update_time': datetime(2026, 8, 12)},
    ]
    assert select_stale_ids(rows, batch_size=1) == ['n']


def test_build_backup_csv_header_and_rows():
    rows = [
        {'video_id': '1', 'video_title': '标题', 'like_count': 3, 'collect_count': 5,
         'update_time': datetime(2026, 8, 12)},
    ]
    text = build_backup_csv(rows)
    assert 'video_id' in text
    assert 'collect_count' in text
    assert '1' in text
