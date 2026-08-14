"""Task 1: 爬虫无头模式 —— PLAYWRIGHT_HEADLESS 配置读取。

云上必须以 headless=True 运行（安全），本地开发可通过配置切换有头模式。
"""
import inspect

import douyin_spider.middlewares as mw
from collector import fetch_author_videos_browser


class _FakeSettings:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class _FakeCrawler:
    def __init__(self, values=None):
        self.settings = _FakeSettings(values or {})
        self.signals = _FakeSignals()


class _FakeSignals:
    def connect(self, *args, **kwargs):
        pass


class _FakeBrowser:
    def close(self):
        pass


class _FakePlaywright:
    def __init__(self):
        self.launch_kwargs = None

    def start(self):
        return self

    @property
    def chromium(self):
        return self

    def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return _FakeBrowser()

    def stop(self):
        pass


def test_playwright_middleware_defaults_to_headless():
    middleware = mw.PlaywrightMiddleware()
    assert middleware.headless is True


def test_playwright_middleware_from_crawler_reads_headless_false_setting():
    crawler = _FakeCrawler({'PLAYWRIGHT_HEADLESS': False})
    middleware = mw.PlaywrightMiddleware.from_crawler(crawler)
    assert middleware.headless is False


def test_playwright_middleware_from_crawler_defaults_to_headless_true():
    middleware = mw.PlaywrightMiddleware.from_crawler(_FakeCrawler({}))
    assert middleware.headless is True


def test_spider_opened_launches_browser_with_headless_from_setting(monkeypatch):
    fake = _FakePlaywright()
    monkeypatch.setattr(mw, 'sync_playwright', lambda: fake)
    crawler = _FakeCrawler({'PLAYWRIGHT_HEADLESS': False})
    middleware = mw.PlaywrightMiddleware.from_crawler(crawler)

    middleware.spider_opened(spider=None)

    assert fake.launch_kwargs['headless'] is False


def test_fetch_author_videos_browser_defaults_headless_true():
    params = inspect.signature(fetch_author_videos_browser).parameters
    assert params['headless'].default is True
