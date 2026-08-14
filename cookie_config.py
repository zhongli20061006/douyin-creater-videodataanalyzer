# cookie_config.py — 抖音 Cookie 的解析、读写与过期提示（面板「设置」页使用）
"""纯函数 + 本地配置读写；local_config.py 为 gitignored 敏感文件，仅本模块触碰 DOUYIN_COOKIES。"""
import ast
import os
import re
from datetime import datetime
from urllib.parse import unquote

COOKIE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_config.py')


def parse_cookie_string(raw: str) -> dict:
    """把浏览器复制的 'k=v; k2=v2' 字符串解析为字典；跳过非「名=值」片段与空值。"""
    cookies: dict = {}
    if not raw:
        return cookies
    for chunk in str(raw).replace('；', ';').split(';'):
        chunk = chunk.strip()
        if not chunk or '=' not in chunk:
            continue
        key, _, value = chunk.partition('=')
        key = key.strip()
        value = value.strip()
        if key and value:
            cookies[key] = value
    return cookies


def read_cookies_from_config(path: str = COOKIE_CONFIG_PATH) -> dict:
    """读取 local_config.py 中的 DOUYIN_COOKIES 字典；文件缺失或解析失败返回 {}。"""
    try:
        with open(path, encoding='utf-8') as f:
            src = f.read()
    except OSError:
        return {}
    m = re.search(r'DOUYIN_COOKIES\s*=\s*(\{.*?\})', src, re.DOTALL)
    if not m:
        return {}
    try:
        data = ast.literal_eval(m.group(1))
        return data if isinstance(data, dict) else {}
    except (ValueError, SyntaxError):
        return {}


def replace_cookie_block(src: str, cookies: dict) -> str:
    """把 src 中的 DOUYIN_COOKIES 赋值块整体替换为 cookies；不存在则在末尾追加。"""
    block = _format_cookie_block(cookies)
    m = re.search(r'DOUYIN_COOKIES\s*=\s*\{', src)
    if not m:
        return src.rstrip() + '\n\n' + block + '\n'
    start = m.start()
    i = src.index('{', m.start())
    depth = 0
    j = i
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    end = j + 1
    return src[:start] + block + src[end:]


def _format_cookie_block(cookies: dict) -> str:
    lines = ['DOUYIN_COOKIES = {']
    for k, v in cookies.items():
        ek = str(k).replace('\\', '\\\\').replace("'", "\\'")
        ev = str(v).replace('\\', '\\\\').replace("'", "\\'")
        lines.append(f"    '{ek}': '{ev}',")
    lines.append('}')
    return '\n'.join(lines)


def write_cookie_config(cookies: dict, path: str = COOKIE_CONFIG_PATH) -> int:
    """把 cookies 写回 local_config.py（保留其它配置项）；返回写入条数。"""
    with open(path, encoding='utf-8') as f:
        src = f.read()
    new_src = replace_cookie_block(src, cookies)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_src)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows 上 chmod 无实际意义
    return len(cookies)


def cookie_expiry_hint(cookies: dict):
    """从 sid_guard 的第 4 段（过期时间）提取 'YYYY-MM-DD'；无则返回 None。"""
    sg = cookies.get('sid_guard')
    if not sg:
        return None
    parts = unquote(str(sg)).split('|')
    if len(parts) < 4:
        return None
    m = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', parts[3])
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%d-%b-%Y').strftime('%Y-%m-%d')
    except ValueError:
        return None


def mask_cookie(cookies: dict) -> dict:
    """脱敏摘要：只保留首尾少量字符，用于页面回显。"""
    out = {}
    for k in ('sessionid', 'ttwid', 'sid_tt', 'uid_tt', 'odin_tt', 'passport_csrf_token'):
        v = cookies.get(k)
        if v:
            v = str(v)
            out[k] = v[:6] + '…' + v[-4:] if len(v) > 12 else v[:8] + '…'
    return out
