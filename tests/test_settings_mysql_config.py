"""Task 2: douyin_spider/settings.py 的 MySQL 配置应从 local_config.py 覆盖（缺失时回退默认值）。

测试是 HERMETIC 的：通过向 sys.modules 注入假的 local_config 模块并 reload settings，
不读取仓库根目录真实的 local_config.py（含真实凭据）。
"""
import importlib
import sys
import types

import pytest

import douyin_spider.settings as settings

# settings.py 中的默认值（与 local_config.example.py 一致）
DEFAULT_MYSQL = {
    'MYSQL_HOST': 'localhost',
    'MYSQL_PORT': 3307,
    'MYSQL_USER': 'root',
    'MYSQL_DB': 'douyin_spider',
}


def _make_fake_local_config(**mysql_overrides):
    """构造一个假的 local_config 模块。

    默认只包含 DOUYIN_COOKIES / MYSQL_PASSWORD（对应 local_config.example.py 注释描述的
    「只填密码」场景），可选地通过关键字参数附加 MYSQL_* 字段。
    """
    fake = types.ModuleType('local_config')
    fake.DOUYIN_COOKIES = {'sessionid': 'fake-session'}
    fake.MYSQL_PASSWORD = 'fake-password'
    for name, value in mysql_overrides.items():
        setattr(fake, name, value)
    return fake


@pytest.fixture(autouse=True)
def _restore_real_settings():
    """每个用例结束后恢复 settings 的真实状态，避免污染其他测试。

    移除注入的 fake local_config 后重新加载 settings：真实 local_config.py 存在则恢复其值，
    不存在则恢复默认兜底——与正常导入路径一致。
    """
    yield
    sys.modules.pop('local_config', None)  # 让真实 local_config.py（若存在）重新生效
    importlib.reload(settings)


def test_mysql_config_overridden_when_local_config_defines_all(monkeypatch):
    """local_config 提供全部 MYSQL_* 时，settings 返回覆盖值（MYSQL_PORT 为 int）。"""
    fake = _make_fake_local_config(
        MYSQL_HOST='10.0.0.1',
        MYSQL_PORT=3306,
        MYSQL_USER='douyin',
        MYSQL_DB='douyin_app',
    )
    monkeypatch.setitem(sys.modules, 'local_config', fake)
    importlib.reload(settings)

    assert settings.MYSQL_HOST == '10.0.0.1'
    assert settings.MYSQL_PORT == 3306
    assert settings.MYSQL_USER == 'douyin'
    assert settings.MYSQL_DB == 'douyin_app'
    # 原有凭据导入行为不变
    assert settings.DOUYIN_COOKIES == {'sessionid': 'fake-session'}
    assert settings.MYSQL_PASSWORD == 'fake-password'


def test_mysql_config_partial_override_keeps_other_defaults(monkeypatch):
    """local_config 只覆盖 MYSQL_HOST 时，其余三项保持默认值（覆盖相互独立）。"""
    fake = _make_fake_local_config(MYSQL_HOST='192.168.1.10')
    monkeypatch.setitem(sys.modules, 'local_config', fake)
    importlib.reload(settings)

    assert settings.MYSQL_HOST == '192.168.1.10'
    assert settings.MYSQL_PORT == DEFAULT_MYSQL['MYSQL_PORT']
    assert settings.MYSQL_USER == DEFAULT_MYSQL['MYSQL_USER']
    assert settings.MYSQL_DB == DEFAULT_MYSQL['MYSQL_DB']


def test_mysql_config_falls_back_when_local_config_has_no_mysql_keys(monkeypatch):
    """local_config 存在但只定义了 DOUYIN_COOKIES/MYSQL_PASSWORD（只填密码场景）→ 全部走默认值。"""
    fake = _make_fake_local_config()
    monkeypatch.setitem(sys.modules, 'local_config', fake)
    importlib.reload(settings)

    for name, default in DEFAULT_MYSQL.items():
        assert getattr(settings, name) == default, name
    assert settings.MYSQL_PASSWORD == 'fake-password'
    assert settings.DOUYIN_COOKIES == {'sessionid': 'fake-session'}


def test_mysql_config_falls_back_when_local_config_absent(monkeypatch):
    """local_config 完全不存在时，四个 MYSQL_* 全部回退默认值，且原有兜底行为不变。

    将 sys.modules['local_config'] 置为 None 会使 import local_config 抛出 ImportError，
    等价于文件不存在（hermetic，不依赖真实文件）。
    """
    monkeypatch.setitem(sys.modules, 'local_config', None)
    importlib.reload(settings)

    for name, default in DEFAULT_MYSQL.items():
        assert getattr(settings, name) == default, name
    # 原有 ImportError 兜底行为保持不变
    assert settings.MYSQL_PASSWORD == ''
    assert settings.DOUYIN_COOKIES == {}
