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


def remove_items(raws: list[str], video_ids: list[str]) -> list[str]:
    """从队列原始条目中移除匹配目标 video_id 的条目，保序；空目标返回原列表。"""
    if not video_ids:
        return list(raws)
    targets = {str(v) for v in video_ids}
    result = []
    for raw in raws:
        item = parse_queue_item(raw)
        url = (item or {}).get('url', '') or ''
        vid = ''
        if '/video/' in url:
            vid = url.split('/video/', 1)[1].split('?')[0].split('/')[0]
        if vid in targets:
            continue
        result.append(raw)
    return result
