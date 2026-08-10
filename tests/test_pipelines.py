"""修复 1：兜底（页面异常）数据缺字段时也能安全构造入库参数。"""
from datetime import datetime

from douyin_spider.items import DouyinVideoItem
from douyin_spider.pipelines import build_insert_params, should_insert_ignore


def test_build_insert_params_fills_defaults_for_incomplete_item():
    """页面异常兜底产生的 item（只有 video_id/title/desc/url）不应触发 KeyError。"""
    item = DouyinVideoItem(
        video_id='123',
        video_title='标题',
        video_desc='描述',
        video_url='https://www.douyin.com/video/123',
    )

    params = build_insert_params(item)

    assert params['video_id'] == '123'
    assert params['video_title'] == '标题'
    assert params['video_desc'] == '描述'
    assert params['author_name'] == ''
    assert params['author_id'] == ''
    assert params['publish_time'] is None
    assert params['like_count'] == 0
    assert params['comment_count'] == 0
    assert params['share_count'] == 0
    assert params['play_count'] == 0
    assert params['video_url'] == 'https://www.douyin.com/video/123'
    assert params['cover_url'] == ''
    assert isinstance(params['crawl_time'], datetime)


def test_build_insert_params_keeps_provided_values():
    """完整 item 的值原样保留。"""
    item = DouyinVideoItem(
        video_id='1',
        video_title='t',
        video_desc='d',
        author_name='a',
        author_id='2',
        like_count=3,
        comment_count=4,
        share_count=5,
        play_count=6,
        video_url='u',
        cover_url='c',
        publish_time=datetime(2026, 1, 1),
    )

    params = build_insert_params(item)

    assert params['author_name'] == 'a'
    assert params['author_id'] == '2'
    assert params['like_count'] == 3
    assert params['comment_count'] == 4
    assert params['share_count'] == 5
    assert params['play_count'] == 6
    assert params['video_url'] == 'u'
    assert params['cover_url'] == 'c'
    assert params['publish_time'] == datetime(2026, 1, 1)


def test_incomplete_item_should_use_insert_ignore():
    """兜底产生的『不完整』数据只能 INSERT IGNORE，不能覆盖已有记录。"""
    item = DouyinVideoItem(video_id='x', incomplete=True)
    assert should_insert_ignore(item) is True


def test_complete_item_should_use_upsert():
    """完整数据继续走 ON DUPLICATE KEY UPDATE 更新。"""
    item = DouyinVideoItem(video_id='x', author_name='a', like_count=1)
    assert should_insert_ignore(item) is False
