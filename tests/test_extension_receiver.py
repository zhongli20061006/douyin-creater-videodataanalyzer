"""浏览器插件接收器：字段校验/归一化/去重/部分更新 SQL。"""
from datetime import datetime

from extension_receiver import (
    MAX_BATCH,
    parse_count,
    parse_datetime,
    validate_source_url,
    validate_video_id,
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
