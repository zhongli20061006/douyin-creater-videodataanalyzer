"""API 守卫依赖：Origin 白名单或 X-API-Token；未配置令牌时 fail-closed。"""
import pytest
from fastapi import HTTPException

import api


@pytest.fixture(autouse=True)
def _configured_token(monkeypatch):
    monkeypatch.setattr(api, 'EXTENSION_API_TOKEN', 'test-token')
    yield


def _call_guard(origin, token):
    api.verify_write_guard(origin=origin, x_api_token=token)


def _call_read_guard(origin, token):
    api.verify_read_guard(origin=origin, x_api_token=token)


def test_whitelist_origin_passes_without_token():
    _call_guard('http://127.0.0.1:8001', None)


def test_cloud_origin_in_allowed_origins():
    assert 'http://47.120.36.73' in api.ALLOWED_ORIGINS


def test_valid_token_passes_from_other_origin():
    _call_guard('https://www.douyin.com', 'test-token')


def test_missing_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', None)
    assert exc.value.status_code == 403


def test_wrong_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', 'bad')
    assert exc.value.status_code == 401


def test_fail_closed_when_token_unconfigured(monkeypatch):
    monkeypatch.setattr(api, 'EXTENSION_API_TOKEN', '')
    with pytest.raises(HTTPException) as exc:
        _call_guard('https://www.douyin.com', 'test-token')
    assert exc.value.status_code == 503


# ── 只读接口守卫（verify_read_guard）：语义与写守卫一致 ──


def test_read_guard_whitelist_origin_passes_without_token():
    _call_read_guard('http://127.0.0.1:8001', None)


def test_read_guard_valid_token_passes_from_other_origin():
    _call_read_guard('https://www.douyin.com', 'test-token')


def test_read_guard_missing_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_read_guard('https://www.douyin.com', None)
    assert exc.value.status_code == 403


def test_read_guard_wrong_token_rejected():
    with pytest.raises(HTTPException) as exc:
        _call_read_guard('https://www.douyin.com', 'bad')
    assert exc.value.status_code == 401


def test_read_guard_fail_closed_when_token_unconfigured(monkeypatch):
    monkeypatch.setattr(api, 'EXTENSION_API_TOKEN', '')
    with pytest.raises(HTTPException) as exc:
        _call_read_guard('https://www.douyin.com', 'test-token')
    assert exc.value.status_code == 503


# ── 路由接线：所有 GET /api/* 都挂 read guard，静态/根路由不挂 ──

NOT_GUARDED_PATHS = ['/app', '/app/{full_path:path}', '/']


def _route_dependency_calls(path, methods=None):
    """返回匹配路径（可选方法过滤）的路由依赖 call 列表；无匹配返回 None。"""
    for route in api.app.routes:
        if getattr(route, 'path', None) != path:
            continue
        if methods is not None:
            route_methods = getattr(route, 'methods', None) or set()
            if not (route_methods & set(methods)):
                continue
        dependant = getattr(route, 'dependant', None)
        if dependant is None:
            return []
        return [d.call for d in getattr(dependant, 'dependencies', []) or []]
    return None


def test_all_get_api_routes_carry_read_guard():
    api_get_routes = [
        route for route in api.app.routes
        if getattr(route, 'path', '').startswith('/api')
        and (getattr(route, 'methods', None) or set()) & {'GET'}
    ]
    assert api_get_routes, '未找到任何 GET /api 路由'
    for route in api_get_routes:
        path = route.path
        calls = _route_dependency_calls(path, methods={'GET'})
        assert calls is not None, f'路由未注册: {path}'
        assert api.verify_read_guard in calls, f'{path} 缺少 verify_read_guard 依赖'


def test_static_and_root_routes_not_read_guarded():
    for path in NOT_GUARDED_PATHS:
        calls = _route_dependency_calls(path)
        assert calls is not None, f'路由未注册: {path}'
        assert api.verify_read_guard not in calls, f'{path} 不应挂 verify_read_guard'
