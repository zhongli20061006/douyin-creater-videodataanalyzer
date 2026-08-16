"""GET /api/analyze/insights 路由逻辑测试。"""
import pytest
from fastapi import HTTPException

import api


class FakeCursor:
    def __init__(self):
        self.last_sql = None
        self.last_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.last_sql = sql
        self.last_params = params

    def fetchall(self):
        return [{'author_name': '测试作者', 'video_id': '1'}]


class FakeDb:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _patch_route(monkeypatch, db, rows=None):
    monkeypatch.setattr(api, 'get_db', lambda: db)
    monkeypatch.setattr(api, 'db_close', lambda db: None)
    monkeypatch.setattr(api, 'apply_publish_filter', lambda start, end: ('', []))
    monkeypatch.setattr(api.extension_receiver, 'build_author_filter', lambda allowed: ('', []))


def _fake_analyze(calls, result=None):
    result = result or {
        'sample_size': 1,
        'insufficient_sample': False,
        'top': [],
        'bottom': [],
        'generated_at': '2026-08-16T12:00:00',
    }

    def fake(rows, limit=10):
        calls['rows'] = rows
        calls['limit'] = limit
        return result

    return fake


def test_empty_author_id_rejected():
    with pytest.raises(HTTPException) as exc:
        api.analyze_insights_endpoint(author_id='   ', limit=10)
    assert exc.value.status_code == 400
    assert exc.value.detail == 'author_id 不能为空'


def test_limit_0_rejected():
    with pytest.raises(HTTPException) as exc:
        api.analyze_insights_endpoint(author_id='A1', limit=0)
    assert exc.value.status_code == 400


def test_limit_51_rejected():
    with pytest.raises(HTTPException) as exc:
        api.analyze_insights_endpoint(author_id='A1', limit=51)
    assert exc.value.status_code == 400


def test_endpoint_builds_base_query_and_forwards_limit(monkeypatch):
    db = FakeDb()
    _patch_route(monkeypatch, db)
    calls = {}
    monkeypatch.setattr(api.analyzer, 'analyze_insights', _fake_analyze(calls))

    result = api.analyze_insights_endpoint(author_id='A1', start_date='', end_date='', limit=10)

    assert result['author_id'] == 'A1'
    assert result['author_name'] == '测试作者'
    assert result['sample_size'] == 1
    assert result['top'] == []
    assert result['bottom'] == []
    assert db.cursor_obj.last_sql == 'SELECT * FROM video_info WHERE author_id = %s'
    assert db.cursor_obj.last_params == ('A1',)
    assert calls['rows'] == [{'author_name': '测试作者', 'video_id': '1'}]
    assert calls['limit'] == 10


def test_endpoint_appends_date_and_author_clauses(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(api, 'get_db', lambda: db)
    monkeypatch.setattr(api, 'db_close', lambda db: None)
    monkeypatch.setattr(api, 'apply_publish_filter', lambda start, end: ('publish_time >= %s', ['2026-01-01']))
    monkeypatch.setattr(api.extension_receiver, 'build_author_filter', lambda allowed: ('author_id IN (%s)', ['allowed']))
    calls = {}
    monkeypatch.setattr(api.analyzer, 'analyze_insights', _fake_analyze(calls))

    api.analyze_insights_endpoint(author_id='A1', start_date='2026-01-01', end_date='', limit=10)

    assert db.cursor_obj.last_sql == (
        'SELECT * FROM video_info WHERE author_id = %s AND publish_time >= %s AND author_id IN (%s)'
    )
    assert db.cursor_obj.last_params == ('A1', '2026-01-01', 'allowed')


def test_limit_boundaries_are_accepted(monkeypatch):
    for limit in (1, 50):
        db = FakeDb()
        _patch_route(monkeypatch, db)
        calls = {}
        monkeypatch.setattr(api.analyzer, 'analyze_insights', _fake_analyze(calls))

        result = api.analyze_insights_endpoint(author_id='A1', limit=limit)

        assert result['sample_size'] == 1
        assert calls['limit'] == limit
