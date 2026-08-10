"""一键收集视频 ID：作者主页 URL → 抖音接口 → 视频预览列表。"""
import pytest

from collector import (
    CollectorError,
    build_cookie_header,
    collect_author_videos,
    extract_sec_user_id,
    fetch_author_videos,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({'url': url, 'params': params, 'headers': headers})
        payload = self.payloads.pop(0) if self.payloads else {'aweme_list': [], 'has_more': False}
        return FakeResponse(payload)


def test_extract_sec_user_id_valid():
    assert extract_sec_user_id('https://www.douyin.com/user/MS4wLjABAAAA123') == 'MS4wLjABAAAA123'


def test_extract_sec_user_id_invalid():
    assert extract_sec_user_id('https://www.douyin.com/video/123') is None
    assert extract_sec_user_id('') is None


def test_build_cookie_header():
    assert build_cookie_header({'a': '1', 'b': '2'}) == 'a=1; b=2'
    assert build_cookie_header({}) == ''


def test_fetch_author_videos_parses_items_and_sends_cookie():
    session = FakeSession([
        {
            'status_code': 0,
            'has_more': False,
            'aweme_list': [
                {'aweme_id': '1', 'desc': '标题1', 'statistics': {'digg_count': 10}, 'author': {'nickname': '作者'}},
                {'aweme_id': '2', 'desc': '标题2', 'statistics': {'digg_count': 20}, 'author': {'nickname': '作者'}},
            ],
        }
    ])

    videos = fetch_author_videos('SEC', session=session, cookies={'sessionid': 'x'})

    assert len(videos) == 2
    assert videos[0] == {'video_id': '1', 'video_title': '标题1', 'like_count': 10, 'author_name': '作者'}
    assert 'Cookie' in session.calls[0]['headers']
    assert 'sec_user_id' in session.calls[0]['params']


def test_fetch_author_videos_raises_on_api_error():
    session = FakeSession([{'status_code': -1, 'status_msg': '风控拦截'}])

    with pytest.raises(CollectorError, match='风控拦截'):
        fetch_author_videos('SEC', session=session)


def test_collect_author_videos_invalid_url():
    with pytest.raises(CollectorError, match='主页'):
        collect_author_videos('https://www.douyin.com/video/123')


def test_collect_author_videos_returns_preview():
    session = FakeSession([
        {
            'status_code': 0,
            'has_more': False,
            'aweme_list': [
                {'aweme_id': '1', 'desc': '标题1', 'statistics': {'digg_count': 10}, 'author': {'nickname': '作者'}},
            ],
        }
    ])

    result = collect_author_videos('https://www.douyin.com/user/SEC', session=session)

    assert result['total'] == 1
    assert result['author_name'] == '作者'
    assert result['videos'][0]['video_id'] == '1'
