"""一键收集视频 ID：作者主页 URL → Playwright 拦截接口 → 视频预览列表。

抖音 web 接口对无签名的直接请求返回空 JSON（反爬），因此收集与爬虫一致，
使用浏览器渲染 + 拦截页面内真实接口响应来获取数据。
"""
import re


class CollectorError(Exception):
    """收集过程中的业务错误，携带用户可读的中文信息。"""


def extract_sec_user_id(url):
    """从作者主页链接提取 sec_user_id；格式不符返回 None。"""
    match = re.search(r'user/([^/?]+)', url or '')
    return match.group(1) if match else None


def build_cookie_header(cookies):
    """把 Cookie 字典拼成请求头字符串。"""
    return '; '.join(f'{k}={v}' for k, v in (cookies or {}).items())


def parse_aweme_list(data):
    """从拦截到的接口 JSON 中提取视频预览字段。"""
    aweme_list = data.get('aweme_list') or []
    videos = []
    for aweme in aweme_list:
        videos.append({
            'video_id': str(aweme.get('aweme_id', '')),
            'video_title': aweme.get('desc', ''),
            'like_count': (aweme.get('statistics') or {}).get('digg_count', 0),
            'author_name': (aweme.get('author') or {}).get('nickname', ''),
        })
    return videos


def dedupe_videos(videos):
    """按 video_id 去重（分页滚动可能重复返回）。"""
    seen = set()
    result = []
    for video in videos:
        if video['video_id'] not in seen:
            seen.add(video['video_id'])
            result.append(video)
    return result


def fetch_author_videos_browser(sec_user_id, max_count=50, headless=True):
    """用 Playwright 打开作者主页并拦截 aweme/post 接口响应。

    headless=True 为云上安全默认值；本地开发可传 headless=False 观察浏览器。
    """
    from playwright.sync_api import sync_playwright

    url = f'https://www.douyin.com/user/{sec_user_id}'
    payloads = []
    scrolls = max(1, min(5, (max_count + 19) // 20))

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled'],
        )
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})

            def handle_response(response):
                if '/aweme/v1/web/aweme/post/' in response.url:
                    try:
                        data = response.json()
                        if data.get('aweme_list'):
                            payloads.append(data)
                    except Exception:
                        pass

            page.on('response', handle_response)
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(4000)
            for _ in range(scrolls):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)
        except Exception as e:
            raise CollectorError(f'打开作者主页失败: {e}') from e
        finally:
            browser.close()

    videos = dedupe_videos(
        [v for data in payloads for v in parse_aweme_list(data)]
    )[:max_count]
    if not videos:
        raise CollectorError(
            '未能获取到作者视频列表：抖音对自动化访问该接口返回空数据（平台风控限制）。'
            '建议改用「粘贴视频 ID」或「文件导入」方式添加任务。'
        )
    return videos


def collect_author_videos(author_url, max_count=50, session=None, cookies=None):
    """收集作者主页视频预览：返回 {author_name, total, videos}。"""
    sec_user_id = extract_sec_user_id(author_url)
    if not sec_user_id:
        raise CollectorError(
            '无法从链接中提取作者主页 ID，请检查链接格式（应形如 https://www.douyin.com/user/xxxx）'
        )
    videos = fetch_author_videos_browser(sec_user_id, max_count=max_count)[:max_count]
    return {
        'author_name': videos[0]['author_name'] if videos else '',
        'total': len(videos),
        'videos': videos,
    }
