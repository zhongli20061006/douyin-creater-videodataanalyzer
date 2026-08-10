"""队列工具：Redis 队列条目解析。"""
import pytest

from queue_service import parse_queue_item


def test_parse_queue_item_valid_json():
    item = parse_queue_item('{"url": "https://www.douyin.com/video/1", "type": "video"}')
    assert item == {'url': 'https://www.douyin.com/video/1', 'type': 'video'}


def test_parse_queue_item_plain_url_fallback():
    item = parse_queue_item('https://www.douyin.com/video/2')
    assert item == {'url': 'https://www.douyin.com/video/2', 'type': 'video'}


def test_parse_queue_item_empty_or_invalid():
    assert parse_queue_item('') is None
    assert parse_queue_item(None) is None


def test_parse_queue_item_non_dict_json_uses_defaults():
    item = parse_queue_item('{"url": "https://www.douyin.com/video/3"}')
    assert item['type'] == 'video'
