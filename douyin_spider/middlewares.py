# douyin_spider/middlewares.py
import json  # 新增这一行
import logging
import random
import time
from fake_useragent import UserAgent
from scrapy import signals
from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware
from scrapy.http import HtmlResponse
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


class RandomUserAgentMiddleware(UserAgentMiddleware):
    """随机 User-Agent 中间件"""
    def __init__(self, user_agent=''):
        super().__init__(user_agent)
        self.ua = UserAgent()
        self.mobile_ua_list = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
        ]

    def process_request(self, request, spider):
        ua = random.choice(self.mobile_ua_list) if random.random() > 0.3 else self.ua.random
        request.headers.setdefault('User-Agent', ua)


class RequestDelayMiddleware:
    """请求延迟中间件"""
    def __init__(self, delay=3):
        self.delay = delay
        self.last_request_time = 0

    @classmethod
    def from_crawler(cls, crawler):
        delay = crawler.settings.get('DOWNLOAD_DELAY', 3)
        return cls(delay)

    def process_request(self, request, spider):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        self.last_request_time = time.time()


class DouyinDownloaderMiddleware:
    """抖音专用下载器中间件，处理 Cookie 和请求头"""
    def __init__(self, cookies):
        if isinstance(cookies, dict):
            self.cookies = cookies
        else:
            self.cookies = {}
            logger.warning("DOUYIN_COOKIES 格式错误，应为字典，已忽略")

    @classmethod
    def from_crawler(cls, crawler):
        cookies = crawler.settings.get('DOUYIN_COOKIES', {})
        return cls(cookies)

    def process_request(self, request, spider):
        if self.cookies:
            cookie_str = '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
            request.headers.setdefault('Cookie', cookie_str)
        request.headers.setdefault('Accept', 'application/json, text/plain, */*')
        request.headers.setdefault('Accept-Language', 'zh-CN,zh;q=0.9')
        request.headers.setdefault('Referer', 'https://www.douyin.com/')
        request.headers.setdefault('Origin', 'https://www.douyin.com')


class PlaywrightMiddleware:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self._init_failed = False

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider):
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
            )
            logger.info("✅ Playwright 浏览器启动成功")
        except Exception as e:
            logger.error(f"❌ Playwright 初始化失败: {e}")
            self._init_failed = True
            self.browser = None
            raise RuntimeError(
                f"Playwright 浏览器不可用（{e}），请先执行: python -m playwright install chromium"
            ) from e

    def spider_closed(self, spider):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def process_request(self, request, spider):
        if not request.meta.get('playwright'):
            return None
        if self._init_failed or not self.browser:
            logger.warning("Playwright 不可用，跳过")
            return None

        page = None
        intercepted_data = {}

        try:
            page = self.browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 800})

            def handle_response(response):
                if '/aweme/v1/web/aweme/detail/' in response.url:
                    try:
                        body = response.body()
                        data = json.loads(body)
                        if data.get('aweme_detail'):
                            intercepted_data['aweme_detail'] = data['aweme_detail']
                            logger.info("🎯 成功拦截视频详情API响应")
                    except Exception as e:
                        logger.error(f"拦截响应解析失败: {e}")

            page.on('response', handle_response)

            page.goto(request.url, wait_until='domcontentloaded', timeout=60000)
            # 等待页面中出现视频元素，但不强求 networkidle，避免超时
            try:
                page.wait_for_selector('video, .xgplayer video, [data-e2e="video-player"]', timeout=10000)
            except Exception:
                logger.warning("等待视频元素超时，但继续获取内容")
            page.wait_for_timeout(3000)

            # 将拦截到的数据存入 meta
            if intercepted_data:
                request.meta['intercepted_data'] = intercepted_data

            body = page.content()
            logger.info(f"✅ Playwright 成功渲染页面，长度: {len(body)}")
            return HtmlResponse(
                url=request.url,
                body=body,
                encoding='utf-8',
                request=request
            )
        except Exception as e:
            logger.error(f"Playwright 渲染失败: {e}")
            # 返回一个空 HTML 响应，避免后续处理崩溃
            return HtmlResponse(
                url=request.url,
                body=b'<html></html>',
                encoding='utf-8',
                request=request
            )
        finally:
            if page:
                page.close()
