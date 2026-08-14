"""修复 2：启动爬虫前自检 Playwright，不可用时清晰报错退出。"""
import os

import pytest

from api import SpiderManager
from start_spider import check_playwright_browser, ensure_playwright_ok


class _OkBrowser:
    def close(self):
        pass


class _OkLauncher:
    class chromium:
        @staticmethod
        def launch(headless=True):
            return _OkBrowser()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FailLauncher:
    def __enter__(self):
        raise RuntimeError('boom')

    def __exit__(self, *args):
        return False


def test_check_playwright_browser_returns_ok_when_launch_succeeds():
    ok, err = check_playwright_browser(launcher=_OkLauncher)
    assert ok is True
    assert err == ''


def test_check_playwright_browser_reports_error_when_launch_fails():
    ok, err = check_playwright_browser(launcher=_FailLauncher)
    assert ok is False
    assert 'boom' in err


def test_ensure_playwright_ok_exits_with_clear_message_on_failure(capsys):
    with pytest.raises(SystemExit) as exc:
        ensure_playwright_ok(check_func=lambda: (False, 'boom'))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert 'playwright install chromium' in out


def test_ensure_playwright_ok_passes_when_available():
    ensure_playwright_ok(check_func=lambda: (True, ''))


def test_spider_manager_venv_python_matches_platform():
    """SpiderManager 的子进程解释器路径必须随平台变化（Windows Scripts/，Linux bin/）。"""
    mgr = SpiderManager()
    if os.name == 'nt':
        assert mgr.venv_python.endswith(os.path.join('.venv', 'Scripts', 'python.exe'))
    else:
        assert mgr.venv_python.endswith(os.path.join('.venv', 'bin', 'python'))
    assert os.path.exists(mgr.venv_python), f'{mgr.venv_python} 应存在'
