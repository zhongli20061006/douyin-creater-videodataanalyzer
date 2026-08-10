"""一键收集视频 ID：作者主页 URL → 抖音接口 → 视频预览列表。"""
import re

import requests


class CollectorError(Exception):
    """收集过程中的业务错误，携带用户可读的中文信息。"""


def extract_sec_user_id(url):
    """从作者主页链接提取 sec_user_id；格式不符返回 None。"""
    match = re.search(r'user/([^/?]+)', url or '')
    return match.group(1) if match else None


def build_cookie_header(cookies):
    """把 Cookie 字典拼成请求头字符串。"""
    return '; '.join(f'{k}={v}' for k, v in (cookies or {}).items())


def fetch_author_videos(sec_user_id, max_count=50, session=None, cookies=None):
    """分页拉取作者视频列表，返回预览字段（最多 max_count 条）。"""
    session = session or requests.Session()
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.douyin.com/',
        'Accept': 'application/json, text/plain, */*',
    }
    cookie = build_cookie_header(cookies)
    if cookie:
        headers['Cookie'] = cookie

    videos = []
    max_cursor = 0
    while len(videos) < max_count:
        params = {
            'aid': '6383',
            'device_platform': 'webapp',
            'cookie_enabled': 'true',
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': 'Chrome',
            'browser_version': '130.0.0.0',
            'sec_user_id': sec_user_id,
            'max_cursor': max_cursor,
            'count': 20,
        }
        try:
            resp = session.get(
                'https://www.douyin.com/aweme/v1/web/aweme/post/',
                params=params,
                headers=headers,
                timeout=15,
            )
            data = resp.json()
        except Exception as e:
            raise CollectorError(f'请求抖音接口失败: {e}') from e

        if data.get('status_code') != 0:
            raise CollectorError(f'抖音接口返回错误: {data.get("status_msg", "未知错误")}')

        aweme_list = data.get('aweme_list') or []
        for aweme in aweme_list:
            if len(videos) >= max_count:
                break
            videos.append({
                'video_id': str(aweme.get('aweme_id', '')),
                'video_title': aweme.get('desc', ''),
                'like_count': (aweme.get('statistics') or {}).get('digg_count', 0),
                'author_name': (aweme.get('author') or {}).get('nickname', ''),
            })

        has_more = data.get('has_more', False)
        max_cursor = data.get('max_cursor', 0)
        if not has_more or not aweme_list:
            break
    return videos


def collect_author_videos(author_url, max_count=50, session=None, cookies=None):
    """收集作者主页视频预览：返回 {author_name, total, videos}。"""
    sec_user_id = extract_sec_user_id(author_url)
    if not sec_user_id:
        raise CollectorError(
            '无法从链接中提取作者主页 ID，请检查链接格式（应形如 https://www.douyin.com/user/xxxx）'
        )
    videos = fetch_author_videos(
        sec_user_id,
        max_count=max_count,
        session=session,
        cookies=cookies,
    )
    return {
        'author_name': videos[0]['author_name'] if videos else '',
        'total': len(videos),
        'videos': videos,
    }
