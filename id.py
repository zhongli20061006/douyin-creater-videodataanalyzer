import requests
import re
import json
import time

# ========== 请替换为从浏览器抓包获取的真实数据 ==========
# 1. 完整的Cookie字符串（务必包含sessionid等核心字段）
# 注意：真实 Cookie 属于敏感凭据，请从浏览器抓包后填入，不要提交到 Git。
FULL_COOKIE = ""

# 2. 完整的请求参数（从抓包的Query String Parameters中复制）
BASE_PARAMS = {
    "aid": "6383",
    "device_platform": "webapp",
    "cookie_enabled": "true",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "114.0.0.0",
    # 其他参数请对照抓包结果补充完整
}
# =====================================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Referer': 'https://www.douyin.com/',
    'Cookie': FULL_COOKIE,
    'Accept': 'application/json, text/plain, */*',
}

def extract_sec_user_id(homepage_url):
    pattern = r'(?<=user/)[^/?]+'
    match = re.search(pattern, homepage_url)
    return match.group(0) if match else None

def get_video_ids(sec_user_id, max_count=50):
    video_ids = []
    max_cursor = 0
    has_more = True
    api_url = "https://www.douyin.com/aweme/v1/web/aweme/post/"

    while has_more and len(video_ids) < max_count:
        # 动态拼接参数
        params = BASE_PARAMS.copy()
        params.update({
            "sec_user_id": sec_user_id,
            "max_cursor": max_cursor,
            "count": 20,
        })

        try:
            response = requests.get(api_url, headers=HEADERS, params=params, timeout=10)
            # 调试：打印状态码和响应前200字符
            print(f"状态码: {response.status_code}, 响应预览: {response.text[:200]}")

            # 如果响应为空或非JSON，则提前终止
            if not response.text:
                print("响应为空，可能Cookie失效或被风控，请更新Cookie。")
                break

            data = response.json()

            if data.get('status_code') != 0:
                print(f"API错误: {data.get('status_msg', '未知错误')}")
                break

            aweme_list = data.get('aweme_list', [])
            for aweme in aweme_list:
                video_id = aweme.get('aweme_id')
                if video_id:
                    video_ids.append(str(video_id))
                    print(f"已获取视频ID: {video_id}")

            has_more = data.get('has_more', False)
            max_cursor = data.get('max_cursor', 0)
            time.sleep(3)

        except json.JSONDecodeError:
            print(f"JSON解析失败，响应内容: {response.text}")
            break
        except Exception as e:
            print(f"请求异常: {e}")
            break

    return video_ids


# ... existing code ...

if __name__ == '__main__':
    user_homepage_url = input('请输入抖音作者主页网址: ').strip()

    if not user_homepage_url:
        print("❌ 未输入URL，程序退出")
        exit(1)

    sec_id = extract_sec_user_id(user_homepage_url)
    if sec_id:
        print(f"✅ 成功提取sec_user_id: {sec_id}")
        all_ids = get_video_ids(sec_id, max_count=50)
        print(f"\n📊 采集完成，共获取到 {len(all_ids)} 个视频ID。")
        if all_ids:
            with open('video_ids.txt', 'w', encoding='utf-8') as f:
                for vid in all_ids:
                    f.write(vid + '\n')
            print(f"💾 视频ID已保存到 video_ids.txt")
    else:
        print("❌ 未能提取sec_user_id，请检查URL格式是否正确")
