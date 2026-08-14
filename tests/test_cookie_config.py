"""cookie_config：Cookie 字符串解析、local_config.py 读写、过期提示。"""
import pytest

from cookie_config import (
    cookie_expiry_hint,
    mask_cookie,
    parse_cookie_string,
    read_cookies_from_config,
    replace_cookie_block,
    write_cookie_config,
)


class TestParseCookieString:
    def test_parses_name_value_pairs(self):
        d = parse_cookie_string('a=1; b=2; c=three')
        assert d == {'a': '1', 'b': '2', 'c': 'three'}

    def test_skips_non_pair_fragments(self):
        d = parse_cookie_string('stray; douyin.com; a=1; b=2')
        assert d == {'a': '1', 'b': '2'}

    def test_handles_fullwidth_semicolon(self):
        d = parse_cookie_string('a=1；b=2; c=3')
        assert d == {'a': '1', 'b': '2', 'c': '3'}

    def test_empty_input(self):
        assert parse_cookie_string('') == {}
        assert parse_cookie_string(None) == {}


class TestReplaceCookieBlock:
    SRC = (
        "DOUYIN_COOKIES = {\n"
        "    'old': '1',\n"
        "}\n"
        "EXTENSION_API_TOKEN = 'tok'\n"
    )

    def test_replaces_existing_block_preserving_others(self):
        out = replace_cookie_block(self.SRC, {'sessionid': 's1', 'ttwid': 't1'})
        assert "DOUYIN_COOKIES = {\n    'sessionid': 's1',\n    'ttwid': 't1',\n}" in out
        assert "EXTENSION_API_TOKEN = 'tok'" in out
        assert "'old'" not in out

    def test_appends_when_missing(self):
        out = replace_cookie_block("EXTENSION_API_TOKEN = 'tok'\n", {'a': 'b'})
        assert out.startswith("EXTENSION_API_TOKEN = 'tok'")
        assert "DOUYIN_COOKIES = {\n    'a': 'b',\n}" in out

    def test_escapes_quotes_and_backslashes(self):
        out = replace_cookie_block("", {'k': "a'b\\c"})
        assert "    'k': 'a\\'b\\\\c'," in out


class TestWriteReadRoundtrip:
    def test_roundtrip_and_preserves_other_keys(self, tmp_path):
        path = tmp_path / 'local_config.py'
        path.write_text(
            "MYSQL_PASSWORD = 'secret'\nDOUYIN_COOKIES = {\n    'old': '1',\n}\n",
            encoding='utf-8',
        )
        n = write_cookie_config({'sessionid': 's1', 'ttwid': 't1'}, str(path))
        assert n == 2
        text = path.read_text(encoding='utf-8')
        assert "MYSQL_PASSWORD = 'secret'" in text
        assert read_cookies_from_config(str(path)) == {'sessionid': 's1', 'ttwid': 't1'}

    def test_read_missing_file_returns_empty(self, tmp_path):
        assert read_cookies_from_config(str(tmp_path / 'nope.py')) == {}


class TestExpiryAndMask:
    def test_expiry_from_sid_guard(self):
        d = {
            'sid_guard': (
                'abc%7C1786361208%7C5184000%7CFri%2C+09-Oct-2026+11%3A26%3A48+GMT'
            )
        }
        assert cookie_expiry_hint(d) == '2026-10-09'

    def test_no_expiry_without_sid_guard(self):
        assert cookie_expiry_hint({'sessionid': 'x'}) is None

    def test_mask_hides_middle(self):
        d = {'sessionid': 'abcdefghijklmnop'}
        masked = mask_cookie(d)
        assert masked['sessionid'].startswith('abcdef')
        assert masked['sessionid'].endswith('nop')
        assert 'ghijklm' not in masked['sessionid']
