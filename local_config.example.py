# 本地敏感配置示例
# 使用方法：复制本文件为 local_config.py，填入你的真实值。
# local_config.py 已在 .gitignore 中，不会提交到 Git。

DOUYIN_COOKIES = {
    'sessionid': '你的 sessionid',
    'ttwid': '你的 ttwid',
    # 其他抖音 Cookie 字段按需添加
}

MYSQL_PASSWORD = '你的 MySQL 密码'

# 扩展写接口鉴权令牌（extension 选项页需填写同一令牌）
# 留空 = fail-closed：扩展上报会被后端拒绝（503）
EXTENSION_API_TOKEN = '请设置一段随机字符串'
