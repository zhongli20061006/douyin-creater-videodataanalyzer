# douyin_spider/spiders/douyin_video.py
import json
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import scrapy
import redis
from jsonpath import jsonpath

from douyin_spider.items import DouyinVideoItem


class DouyinVideoSpider(scrapy.Spider):
    name = 'douyin_video'
    allowed_domains = ['douyin.com', 'iesdouyin.com', 'snssdk.com']
    redis_key = 'douyin:start_urls'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.api_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.douyin.com/',
            'Origin': 'https://www.douyin.com',
            'Connection': 'keep-alive',
        }

        self.video_detail_api = 'https://www.douyin.com/aweme/v1/web/aweme/detail/'
        self.user_post_api = 'https://www.douyin.com/aweme/v1/web/aweme/post/'

        self.redis_client = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)

        spider.redis_client = redis.Redis(
            host=crawler.settings.get('REDIS_HOST', 'localhost'),
            port=crawler.settings.get('REDIS_PORT', 6379),
            password=crawler.settings.getdict('REDIS_PARAMS', {}).get('password'),
            db=crawler.settings.getdict('REDIS_PARAMS', {}).get('db', 0),
            decode_responses=True
        )
        return spider

    def start_requests(self):
        """
        从 Redis 逐条取任务；队列为空则正常结束。
        """
        request = self._pop_task()
        if request is None:
            self.logger.info("Redis 队列为空，本次没有可爬取的任务")
            return
        yield request

    def _pop_task(self):
        """从 Redis 队首取出一条任务并生成请求；队列为空返回 None。"""
        try:
            data = self.redis_client.lpop(self.redis_key)
        except Exception as e:
            self.logger.error(f"从 Redis 取任务失败: {e}")
            return None
        if not data:
            return None
        return self.make_request_from_data(data)

    def _chain_next(self):
        """当前请求处理完后取下一条任务，用于接力消费直到队列清空。"""
        request = self._pop_task()
        if request:
            yield request

    def make_request_from_data(self, data):
        try:
            if isinstance(data, str):
                task_data = json.loads(data)
            else:
                task_data = data
        except (json.JSONDecodeError, TypeError):
            url = data if isinstance(data, str) else data.get('url', data)
            task_data = {'url': url, 'type': 'video'}

        url = task_data.get('url')
        task_type = task_data.get('type', 'video')

        if not url:
            return None

        if task_type == 'user':
            return self.parse_user_page(url, task_data)
        elif task_type == 'search':
            return self.parse_search_page(url, task_data)
        else:
            # ========== 关键修改：为视频页面请求添加 Playwright 标记 ==========
            return scrapy.Request(
                url=url,
                headers=self.api_headers,
                callback=self.parse_video_page,
                meta={
                    'task_data': task_data,
                    'playwright': True,          # 启用 Playwright 渲染
                    'playwright_page_method': 'wait_for_selector',
                    'playwright_page_args': ['video'],  # 等待视频元素出现
                },
                dont_filter=True
            )

    def extract_universal_data(self, html):
        """从 __UNIVERSAL_DATA_FOR_REHYDRATION__ 提取 JSON"""
        pattern = r'<script[^>]*>window\.__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*({.*?});</script>'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        return None

    def extract_json_by_regex(self, html):
        """正则搜索含有 aweme_id 和 statistics 的 JSON 对象"""
        # 寻找类似 {"aweme_id":"123","statistics":{...}} 的结构
        pattern = r'\{[^{]*"aweme_id"[^{]*"statistics"[^{]*\}'
        matches = re.finditer(pattern, html)
        for match in matches:
            try:
                # 尝试解析匹配到的 JSON 片段
                # 由于正则可能截断，尝试寻找完整的 JSON 对象
                start = match.start()
                # 从起始位置向后找到配对的 }
                depth = 0
                end = start
                for i, ch in enumerate(html[start:], start):
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                json_str = html[start:end + 1]
                data = json.loads(json_str)
                if 'aweme_id' in data and 'statistics' in data:
                    # 包装成类似结构供 parse_video_data_from_page 使用
                    return {'aweme_detail': data}
            except:
                continue
        return None

    def extract_video_id(self, response):
        """从响应 URL 或页面内容中提取视频 ID"""
        # 从 URL 提取
        video_id_match = re.search(r'/video/(\d+)', response.url)
        if video_id_match:
            return video_id_match.group(1)
        # 从页面内容提取
        id_match = re.search(r'"aweme_id"\s*:\s*"(\d+)"', response.text)
        if id_match:
            return id_match.group(1)
        return None

    def parse_video_page(self, response):
        # 优先使用拦截到的 API 数据
        intercepted = response.meta.get('intercepted_data', {})
        if intercepted and intercepted.get('aweme_detail'):
            aweme_detail = intercepted['aweme_detail']
            self.logger.info("🎉 使用拦截到的API数据")
            item = self.parse_video_data(aweme_detail)
            if item:
                yield item
                yield from self._chain_next()
                return

        # 降级：检查响应是否为文本类型，再尝试保存和解析
        try:
            html_text = response.text
        except AttributeError:
            self.logger.error("响应内容不是文本，无法解析")
            yield from self._chain_next()
            return

        # 保存页面
        with open('douyinpage.html', 'w', encoding='utf-8') as f:
            f.write(html_text)
        self.logger.info("页面已保存至 douyinpage.html")

        # 尝试从 HTML 中提取视频 ID
        video_id = self.extract_video_id(response)
        if not video_id:
            self.logger.error("无法提取视频 ID，跳过")
            yield from self._chain_next()
            return

        # 原有的 HTML 解析逻辑（RENDER_DATA、正则等）...
        # （此处可以保留之前的提取代码，但优先级低于拦截数据）
        self.logger.warning(
            f"页面异常，仅保存基础信息: {video_id}（可能已删除/私密，或 Cookie 已失效）"
        )
        # 简单构建一个只有视频ID和标题的 item
        title = response.css('title::text').get() or ''
        item = DouyinVideoItem()
        item['video_id'] = video_id
        item['video_title'] = title.strip()
        item['video_desc'] = title.strip()
        item['video_url'] = response.url
        item['incomplete'] = True  # 兜底数据标记为不完整，入库时不得覆盖已有完整记录
        yield item
        yield from self._chain_next()
    def parse_count(self, text):
        """将抖音的计数文本转换为整数"""
        if not text:
            return 0
        text = text.strip()
        try:
            if 'w' in text or '万' in text:
                num = float(re.sub(r'[^\d.]', '', text))
                return int(num * 10000)
            else:
                return int(re.sub(r'[^\d]', '', text))
        except:
            return 0

    def extract_json_from_html(self, html):
        json_pattern = r'<script[^>]*id="RENDER_DATA"[^>]*>(.*?)</script>'
        match = re.search(json_pattern, html, re.DOTALL)
        if match:
            try:
                import urllib.parse
                decoded = urllib.parse.unquote(match.group(1))
                return json.loads(decoded)
            except Exception:
                pass
        return None

    def parse_video_data_from_page(self, json_data):
        """从页面内嵌的 JSON 数据中提取视频信息（增强版）"""
        try:
            # 递归查找包含 aweme_id 和 statistics 的字典
            def find_aweme_detail(obj, depth=0):
                if depth > 20:
                    return None
                if isinstance(obj, dict):
                    if 'aweme_id' in obj and 'statistics' in obj:
                        return obj
                    # 如果字典包含 aweme_detail 键
                    if 'aweme_detail' in obj:
                        return obj['aweme_detail']
                    for v in obj.values():
                        res = find_aweme_detail(v, depth + 1)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = find_aweme_detail(item, depth + 1)
                        if res:
                            return res
                return None

            aweme_detail = find_aweme_detail(json_data)
            if aweme_detail:
                self.logger.info("✅ 从页面 JSON 中成功提取到视频详情")
                return self.parse_video_data(aweme_detail)
        except Exception as e:
            self.logger.error(f"递归提取失败: {e}")
        return None
    def request_video_detail(self, video_id, task_data=None):
        params = {
            'aweme_id': video_id,
            'aid': '1128',
            'version_name': '23.5.0',
            'device_platform': 'android',
            'os_version': '13',
            '_': str(int(time.time() * 1000)),
        }
        url = f"{self.video_detail_api}?{urlencode(params)}"

        return scrapy.Request(
            url=url,
            headers=self.api_headers,
            callback=self.parse_video_detail,
            meta={'video_id': video_id, 'task_data': task_data},
            dont_filter=True
        )

    def parse_video_detail(self, response):
        try:
            data = response.json()

            if data.get('status_code') != 0:
                self.logger.warning(f"API 返回错误: {data.get('status_msg')}")
            else:
                aweme_detail = data.get('aweme_detail', {})
                if not aweme_detail:
                    self.logger.warning("未获取到视频详情数据")
                else:
                    item = self.parse_video_data(aweme_detail)
                    if item:
                        yield item

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析失败: {e}")
        except Exception as e:
            self.logger.error(f"解析视频详情失败: {e}")
        yield from self._chain_next()

    def parse_video_data(self, aweme_data):
        item = DouyinVideoItem()

        try:
            item['video_id'] = str(aweme_data.get('aweme_id', ''))
            item['video_title'] = aweme_data.get('desc', '')
            item['video_desc'] = aweme_data.get('desc', '')

            author = aweme_data.get('author', {})
            item['author_name'] = author.get('nickname', '')
            item['author_id'] = str(author.get('uid', ''))

            create_time = aweme_data.get('create_time', 0)
            if create_time:
                item['publish_time'] = datetime.fromtimestamp(create_time)

            statistics = aweme_data.get('statistics', {})
            item['like_count'] = statistics.get('digg_count', 0)
            item['comment_count'] = statistics.get('comment_count', 0)
            item['share_count'] = statistics.get('share_count', 0)
            item['play_count'] = statistics.get('play_count', 0)
            item['collect_count'] = statistics.get('collect_count', 0)

            video = aweme_data.get('video', {})
            play_addr = video.get('play_addr', {})
            item['video_url'] = play_addr.get('url_list', [''])[0] if play_addr.get('url_list') else ''

            cover = video.get('cover', {})
            item['cover_url'] = cover.get('url_list', [''])[0] if cover.get('url_list') else ''

            self.logger.info(f"成功提取视频信息: {item['video_id']} - {item['video_title'][:30]}")
            return item

        except Exception as e:
            self.logger.error(f"解析视频数据失败: {e}")
            return None

    def parse_user_page(self, url, task_data):
        return scrapy.Request(
            url=url,
            headers=self.api_headers,
            callback=self.parse_user_videos,
            meta={'task_data': task_data},
            dont_filter=True
        )

    def parse_user_videos(self, response):
        try:
            data = response.json()
            aweme_list = data.get('aweme_list', [])

            for aweme in aweme_list:
                item = self.parse_video_data(aweme)
                if item:
                    yield item

                video_id = aweme.get('aweme_id')
                if video_id:
                    yield self.request_video_detail(video_id)

        except Exception as e:
            self.logger.error(f"解析用户作品列表失败: {e}")
        json_data = self.extract_json_from_html(response.text)
        if not json_data:
            json_data = self.extract_universal_data(response.text)  # 需实现该方法

        if json_data:
            item = self.parse_video_data_from_page(json_data)
            if item:
                yield item
        yield from self._chain_next()
    def parse_search_page(self, url, task_data):
        return scrapy.Request(
            url=url,
            headers=self.api_headers,
            callback=self.parse_search_results,
            meta={'task_data': task_data},
            dont_filter=True
        )

    def parse_search_results(self, response):
        try:
            data = response.json()
            items = jsonpath(data, '$..aweme_info') or []

            for aweme in items:
                item = self.parse_video_data(aweme)
                if item:
                    yield item
        except Exception as e:
            self.logger.error(f"解析搜索结果失败: {e}")
        yield from self._chain_next()
