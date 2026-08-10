"""队列工具：Redis 队列条目解析。"""
import json


def parse_queue_item(raw):
    """把 Redis 中的任务条目解析为 {url, type}；空/无法解析返回 None。"""
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    'url': data.get('url', ''),
                    'type': data.get('type', 'video'),
                }
        except (json.JSONDecodeError, TypeError):
            pass
        return {'url': raw, 'type': 'video'}
    return None
