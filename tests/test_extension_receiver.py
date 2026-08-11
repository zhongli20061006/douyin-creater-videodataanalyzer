"""浏览器插件接收器：字段校验/归一化/去重/部分更新 SQL。"""
from datetime import datetime

from extension_receiver import (
    MAX_BATCH,
    append_ids_file,
    build_upsert,
    dedupe_records,
    merge_ids,
    normalize_record,
    parse_count,
    parse_datetime,
    read_ids_file,
    validate_batch,
    validate_source_url,
    validate_video_id,
    write_ids_file,
)


def test_validate_video_id():
    assert validate_video_id('7638884656238410714') is True
    assert validate_video_id(' 7638884656238410714 ') is True
    assert validate_video_id('123') is False
    assert validate_video_id('abc12345678901234') is False
    assert validate_video_id('') is False
    assert validate_video_id(None) is False
    assert validate_video_id(7638884656238410714) is False


def test_validate_source_url():
    assert validate_source_url('https://www.douyin.com/user/MS4wLjABAAAA123') is True
    assert validate_source_url('https://www.douyin.com/user/self') is True
    assert validate_source_url('https://www.douyin.com/video/123') is False
    assert validate_source_url('https://evil.com/user/MS4wLjABAAAA123') is False
    assert validate_source_url('') is False


def test_parse_datetime_accepts_iso_and_space_formats():
    assert isinstance(parse_datetime('2026-05-12T14:13:52'), datetime)
    assert isinstance(parse_datetime('2026-05-12 14:13:52'), datetime)
    assert isinstance(parse_datetime('2026-05-12'), datetime)
    assert parse_datetime('垃圾数据') is None
    assert parse_datetime(None) is None
    assert parse_datetime('') is None


def test_parse_count_accepts_int_and_digit_string():
    assert parse_count(236) == 236
    assert parse_count('236') == 236
    assert parse_count(0) == 0
    assert parse_count('4.0') == 4


def test_parse_count_rejects_negative_and_non_numeric():
    assert parse_count(-1) is None
    assert parse_count('4.0万') is None
    assert parse_count('abc') is None
    assert parse_count(2.5) is None
    assert parse_count(None) is None


def test_max_batch_constant():
    assert MAX_BATCH == 100


def test_normalize_record_defaults():
    record, reason = normalize_record({'video_id': '7638884656238410714'})
    assert reason is None
    assert record['video_id'] == '7638884656238410714'
    assert record['video_title'] == ''
    assert record['author_name'] == ''
    assert record['publish_time'] is None
    assert record['like_count'] is None
    assert record['play_count'] is None


def test_normalize_record_strips_and_limits_text():
    record, _ = normalize_record({
        'video_id': '7638884656238410714',
        'video_title': '  标题  ',
        'author_name': 'a' * 200,
    })
    assert record is None
    record, _ = normalize_record({
        'video_id': '7638884656238410714',
        'video_title': '  标题  ',
    })
    assert record['video_title'] == '标题'


def test_normalize_record_rejects_bad_counts():
    record, reason = normalize_record({
        'video_id': '7638884656238410714',
        'like_count': -5,
    })
    assert record is None and reason


def test_validate_batch_requires_valid_source_url():
    payload = {'source_url': 'https://www.douyin.com/video/123', 'videos': []}
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert rejected and rejected[0]['reason']


def test_validate_batch_enforces_batch_limit():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [{'video_id': '7638884656238410714'} for _ in range(101)],
    }
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert rejected[0]['reason']


def test_validate_batch_rejects_mixed_authors():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [
            {'video_id': '7638884656238410714', 'author_id': 'A'},
            {'video_id': '7638884656238410715', 'author_id': 'B'},
        ],
    }
    valid, rejected = validate_batch(payload)
    assert valid == []
    assert any('author_id' in r['reason'] for r in rejected)


def test_validate_batch_passes_clean_batch():
    payload = {
        'source_url': 'https://www.douyin.com/user/MS4wLjABAAAA123',
        'videos': [
            {
                'video_id': '7638884656238410714',
                'video_title': '标题A',
                'like_count': 40000,
                'author_id': 'A',
            },
            {
                'video_id': '7638884656238410715',
                'video_title': '标题B',
                'author_id': 'A',
            },
        ],
    }
    valid, rejected = validate_batch(payload)
    assert rejected == []
    assert len(valid) == 2
    assert valid[0]['like_count'] == 40000
    assert valid[1]['like_count'] is None


def test_dedupe_records_keeps_first_by_video_id():
    records = [
        {'video_id': '1', 'play_count': 10},
        {'video_id': '2', 'play_count': 20},
        {'video_id': '1', 'play_count': 99},
    ]
    result = dedupe_records(records)
    assert [r['video_id'] for r in result] == ['1', '2']
    assert result[0]['play_count'] == 10


def test_build_upsert_skips_none_fields():
    record = {
        'video_id': '7638884656238410714',
        'video_title': '标题',
        'video_desc': '',
        'author_name': '我',
        'author_id': 'A',
        'publish_time': None,
        'like_count': None,
        'comment_count': None,
        'share_count': None,
        'play_count': 236,
        'video_url': '',
        'cover_url': '',
    }
    sql, params = build_upsert(record)
    assert 'like_count=VALUES(like_count)' not in sql
    assert 'play_count=VALUES(play_count)' in sql
    assert 'crawl_time=NOW()' in sql
    assert params[0] == '7638884656238410714'
    assert params[9] == 236


def test_build_upsert_includes_present_count_fields():
    record = {
        'video_id': '7638884656238410714',
        'video_title': '标题',
        'video_desc': '',
        'author_name': '我',
        'author_id': 'A',
        'publish_time': None,
        'like_count': 40000,
        'comment_count': 481,
        'share_count': 1150,
        'play_count': None,
        'video_url': '',
        'cover_url': '',
    }
    sql, _ = build_upsert(record)
    assert 'like_count=VALUES(like_count)' in sql
    assert 'play_count=VALUES(play_count)' not in sql


def test_merge_ids_keeps_existing_order_and_appends_new():
    merged = merge_ids(['a', 'b'], ['c', 'a', 'd'])
    assert merged == ['a', 'b', 'c', 'd']


def test_merge_ids_removes_duplicates_in_existing():
    merged = merge_ids(['a', 'a', 'b'], ['b', 'c'])
    assert merged == ['a', 'b', 'c']


def test_merge_ids_empty_inputs():
    assert merge_ids([], []) == []
    assert merge_ids(['a'], []) == ['a']
    assert merge_ids([], ['a', 'b']) == ['a', 'b']


def test_append_ids_file_merges_and_returns_counts(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['b', 'c'])
    assert (added, total) == (1, 3)
    assert path.read_text(encoding='utf-8').splitlines() == ['a', 'b', 'c']


def test_append_ids_file_creates_missing_file(tmp_path):
    path = tmp_path / 'video_ids.txt'
    added, total = append_ids_file(str(path), ['x', 'y'])
    assert (added, total) == (2, 2)
    assert path.read_text(encoding='utf-8').splitlines() == ['x', 'y']


def test_append_ids_file_no_tmp_leftover(tmp_path):
    path = tmp_path / 'video_ids.txt'
    append_ids_file(str(path), ['a'])
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')]
    assert leftovers == []


def test_read_ids_file_reads_lines_and_skips_blanks(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\n\nb\n', encoding='utf-8')
    assert read_ids_file(str(path)) == ['a', 'b']


def test_read_ids_file_missing_returns_empty(tmp_path):
    assert read_ids_file(str(tmp_path / 'missing.txt')) == []


def test_write_ids_file_overwrites(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb\n', encoding='utf-8')
    assert write_ids_file(str(path), ['x', 'y']) == 2
    assert path.read_text(encoding='utf-8').splitlines() == ['x', 'y']


def test_write_ids_file_empty_clears(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb\n', encoding='utf-8')
    assert write_ids_file(str(path), []) == 0
    assert path.read_text(encoding='utf-8') == ''
