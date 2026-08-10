"""SpiderManager 日志读取：混合编码字节解码与缺失文件处理。"""
from api import decode_log_bytes, read_log_tail


def test_decode_log_bytes_handles_utf8():
    assert '第一行正常' in decode_log_bytes('第一行正常\n'.encode('utf-8'))


def test_decode_log_bytes_falls_back_to_gbk():
    # 早期子进程用 GBK 写入的字节，UTF-8 解码失败时回退 GBK
    assert '第二行中文内容' in decode_log_bytes('第二行中文内容'.encode('gbk'))


def test_read_log_tail_missing_file_returns_empty():
    assert read_log_tail('C:/definitely/not/exist.log') == []


def test_spider_manager_has_get_log_method():
    from api import SpiderManager

    assert hasattr(SpiderManager, 'get_log')
