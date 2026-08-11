import json
import os
import subprocess
import pymysql
import redis
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

import quality as quality_service
import collector
import queue_service
import extension_receiver

os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'douyin_spider.settings')

try:
    from scrapy.utils.project import get_project_settings
    settings = get_project_settings()
    MYSQL_HOST = settings.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = settings.getint('MYSQL_PORT', 3307)
    MYSQL_USER = settings.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = settings.get('MYSQL_PASSWORD', '')
    MYSQL_DB = settings.get('MYSQL_DB', 'douyin_spider')
    REDIS_HOST = settings.get('REDIS_HOST', 'localhost')
    REDIS_PORT = settings.getint('REDIS_PORT', 6379)
    REDIS_PARAMS = settings.getdict('REDIS_PARAMS', {})
    REDIS_START_URLS_KEY = settings.get('REDIS_START_URLS_KEY', 'douyin:start_urls')
except Exception:
    MYSQL_HOST = 'localhost'
    MYSQL_PORT = 3307
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'douyin_spider'
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_PARAMS = {}
    REDIS_START_URLS_KEY = 'douyin:start_urls'

app = FastAPI(title='抖音爬虫管理面板', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def get_redis():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PARAMS.get('password'),
        db=REDIS_PARAMS.get('db', 0),
        decode_responses=True,
    )


def get_db():
    try:
        return pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
        )
    except pymysql.Error as e:
        raise HTTPException(status_code=503, detail=f'MySQL 连接失败: {e}')


def db_close(db):
    try:
        db.close()
    except Exception:
        pass


# ── Spider Process Manager ──

class SpiderManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.started_at: Optional[datetime] = None
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.venv_python = os.path.join(self.project_root, '.venv', 'Scripts', 'python.exe')
        self.log_path = os.path.join(self.project_root, 'spider_output.log')

    def start(self):
        if self.is_alive():
            return False, '爬虫已在运行'
        log_file = open(self.log_path, 'a', encoding='utf-8')
        log_file.write(f'\n=== Spider started at {datetime.now().isoformat()} ===\n')
        self.process = subprocess.Popen(
            [self.venv_python, 'start_spider.py', '--mode', 'start'],
            cwd=self.project_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        self.started_at = datetime.now()
        return True, '爬虫已启动'

    def stop(self):
        if not self.is_alive():
            return False, '爬虫未运行'
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
        self.started_at = None
        return True, '爬虫已停止'

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def get_status(self):
        return {
            'running': self.is_alive(),
            'pid': self.process.pid if self.process else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
        }

    def get_log(self, lines=50):
        return read_log_tail(self.log_path, lines)


spider_manager = SpiderManager()


def decode_log_bytes(raw):
    """日志字节解码：逐行处理，每行 UTF-8 优先，失败回退 GBK（兼容混合编码文件）。"""
    decoded = []
    for line in raw.splitlines():
        try:
            decoded.append(line.decode('utf-8'))
        except UnicodeDecodeError:
            decoded.append(line.decode('gbk', errors='replace'))
    return '\n'.join(decoded)


def read_log_tail(path, lines=50):
    """读取日志文件末尾 N 行；兼容混合编码。"""
    if not os.path.exists(path):
        return []
    with open(path, 'rb') as f:
        raw = f.read()
    return decode_log_bytes(raw).splitlines()[-lines:]


# ── Pydantic Models ──

class CrawlRequest(BaseModel):
    video_ids: list[str]
    task_type: str = 'video'


class CrawlResponse(BaseModel):
    pushed: int
    queue_length: int
    video_ids: list[str]


class VideoItem(BaseModel):
    video_id: str
    video_title: Optional[str] = None
    video_desc: Optional[str] = None
    author_name: Optional[str] = None
    author_id: Optional[str] = None
    publish_time: Optional[datetime] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    play_count: Optional[int] = None
    video_url: Optional[str] = None
    cover_url: Optional[str] = None
    crawl_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[VideoItem]


class StatsResponse(BaseModel):
    total_videos: int
    total_authors: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_plays: int
    latest_crawl: Optional[datetime] = None
    queue_length: int = 0


# ── API Endpoints ──

@app.get('/api/videos', response_model=PaginatedResponse)
def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query('', description='搜索视频标题/作者/ID'),
    sort_by: str = Query('crawl_time', description='排序字段'),
    order: str = Query('desc', pattern='^(asc|desc)$'),
):
    allowed_sort = {
        'video_id', 'video_title', 'author_name', 'publish_time',
        'like_count', 'comment_count', 'share_count', 'play_count',
        'crawl_time', 'update_time',
    }
    if sort_by not in allowed_sort:
        sort_by = 'crawl_time'

    order_clause = 'DESC' if order == 'desc' else 'ASC'
    offset = (page - 1) * page_size

    db = get_db()
    try:
        with db.cursor() as cursor:
            if search:
                search_param = f'%{search}%'
                count_sql = """
                    SELECT COUNT(*) AS total FROM video_info
                    WHERE video_id LIKE %s OR video_title LIKE %s OR author_name LIKE %s
                """
                cursor.execute(count_sql, (search_param, search_param, search_param))
                total = cursor.fetchone()['total']

                data_sql = f"""
                    SELECT * FROM video_info
                    WHERE video_id LIKE %s OR video_title LIKE %s OR author_name LIKE %s
                    ORDER BY {sort_by} {order_clause}
                    LIMIT %s OFFSET %s
                """
                cursor.execute(data_sql, (search_param, search_param, search_param, page_size, offset))
            else:
                cursor.execute('SELECT COUNT(*) AS total FROM video_info')
                total = cursor.fetchone()['total']

                data_sql = f"""
                    SELECT * FROM video_info
                    ORDER BY {sort_by} {order_clause}
                    LIMIT %s OFFSET %s
                """
                cursor.execute(data_sql, (page_size, offset))

            rows = cursor.fetchall()

        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
            data=[VideoItem(**row) for row in rows],
        )
    finally:
        db_close(db)


@app.get('/api/videos/{video_id}', response_model=VideoItem)
def get_video(video_id: str):
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info WHERE video_id = %s', (video_id,))
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='视频不存在')
        return VideoItem(**row)
    finally:
        db_close(db)


@app.get('/api/stats', response_model=StatsResponse)
def get_stats():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_videos,
                    COUNT(DISTINCT author_id) AS total_authors,
                    COALESCE(SUM(like_count), 0) AS total_likes,
                    COALESCE(SUM(comment_count), 0) AS total_comments,
                    COALESCE(SUM(share_count), 0) AS total_shares,
                    COALESCE(SUM(play_count), 0) AS total_plays,
                    MAX(crawl_time) AS latest_crawl
                FROM video_info
            """)
            row = cursor.fetchone()
    finally:
        db_close(db)

    try:
        r = get_redis()
        queue_length = r.llen(REDIS_START_URLS_KEY)
    except Exception:
        queue_length = 0

    return StatsResponse(
        total_videos=row['total_videos'] or 0,
        total_authors=row['total_authors'] or 0,
        total_likes=row['total_likes'] or 0,
        total_comments=row['total_comments'] or 0,
        total_shares=row['total_shares'] or 0,
        total_plays=row['total_plays'] or 0,
        latest_crawl=row['latest_crawl'],
        queue_length=queue_length,
    )


@app.get('/api/stats/authors')
def stats_authors():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT COALESCE(NULLIF(TRIM(author_name), ''), '未知') AS name, COUNT(*) AS value
                FROM video_info
                GROUP BY author_name
                ORDER BY value DESC
            """)
            rows = cursor.fetchall()
    finally:
        db_close(db)
    return {'authors': rows}


@app.post('/api/crawl', response_model=CrawlResponse)
def push_crawl(req: CrawlRequest):
    try:
        r = get_redis()
        count = 0
        valid_ids = []
        for vid in req.video_ids:
            vid = vid.strip()
            if vid:
                task = json.dumps({
                    'url': f'https://www.douyin.com/video/{vid}',
                    'type': req.task_type,
                })
                r.lpush(REDIS_START_URLS_KEY, task)
                count += 1
                valid_ids.append(vid)
        queue_length = r.llen(REDIS_START_URLS_KEY)
        return CrawlResponse(
            pushed=count,
            queue_length=queue_length,
            video_ids=valid_ids,
        )
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')


@app.delete('/api/videos/{video_id}')
def delete_video(video_id: str):
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('DELETE FROM video_info WHERE video_id = %s', (video_id,))
            affected = cursor.rowcount
            db.commit()
        if affected == 0:
            raise HTTPException(status_code=404, detail='视频不存在')
        return {'deleted': True, 'video_id': video_id}
    finally:
        db_close(db)


@app.get('/api/queue/length')
def get_queue_length():
    try:
        r = get_redis()
        return {'queue_length': r.llen(REDIS_START_URLS_KEY)}
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')


@app.get('/api/queue/items')
def get_queue_items(limit: int = Query(50, ge=1, le=200)):
    try:
        r = get_redis()
        raws = r.lrange(REDIS_START_URLS_KEY, 0, limit - 1)
        length = r.llen(REDIS_START_URLS_KEY)
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    items = [it for it in (queue_service.parse_queue_item(raw) for raw in raws) if it]
    return {'queue_length': length, 'items': items}


# ── Spider Control ──

@app.post('/api/spider/start')
def spider_start():
    ok, msg = spider_manager.start()
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    status = spider_manager.get_status()
    status['message'] = msg
    return status


@app.post('/api/spider/stop')
def spider_stop():
    ok, msg = spider_manager.stop()
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return {'message': msg, 'running': False}


@app.get('/api/spider/status')
def spider_status():
    return spider_manager.get_status()


@app.get('/api/spider/log')
def spider_log(lines: int = 50):
    return {'lines': spider_manager.get_log(lines)}


class QualityDeleteRequest(BaseModel):
    video_ids: list[str]


class CollectRequest(BaseModel):
    author_url: str
    max_count: int = 50


@app.post('/api/collect/author')
def collect_author(req: CollectRequest):
    if not req.author_url.strip():
        raise HTTPException(status_code=400, detail='请输入作者主页链接')
    if not (1 <= req.max_count <= 100):
        raise HTTPException(status_code=400, detail='max_count 需在 1-100 之间')
    try:
        from scrapy.utils.project import get_project_settings
        cookies = get_project_settings().getdict('DOUYIN_COOKIES', {}) or {}
    except Exception:
        cookies = {}
    try:
        result = collector.collect_author_videos(
            req.author_url.strip(),
            max_count=req.max_count,
            cookies=cookies,
        )
    except collector.CollectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'收集失败: {e}')
    return result


@app.get('/api/quality/report')
def quality_report():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info')
            rows = cursor.fetchall()
    finally:
        db_close(db)
    issues = [quality_service.issue_view(r) for r in rows if quality_service.classify_row(r)]
    return {'summary': quality_service.summarize(rows), 'issues': issues}


@app.post('/api/quality/fix')
def quality_fix():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT video_id, video_title FROM video_info')
            rows = cursor.fetchall()
            fixes = quality_service.collect_title_fixes(rows)
            for video_id, title in fixes:
                cursor.execute('UPDATE video_info SET video_title = %s WHERE video_id = %s', (title, video_id))
            db.commit()
    finally:
        db_close(db)
    return {
        'fixed': len(fixes),
        'details': [{'video_id': v, 'video_title': t} for v, t in fixes[:20]],
    }


@app.post('/api/quality/delete')
def quality_delete(req: QualityDeleteRequest):
    if len(req.video_ids) > quality_service.MAX_DELETE_IDS:
        raise HTTPException(status_code=400, detail=f'单次最多删除 {quality_service.MAX_DELETE_IDS} 条，请分批操作')
    db = get_db()
    try:
        deleted = 0
        rejected = []
        with db.cursor() as cursor:
            for video_id in req.video_ids:
                cursor.execute('SELECT * FROM video_info WHERE video_id = %s', (video_id,))
                row = cursor.fetchone()
                if not row:
                    rejected.append({'video_id': video_id, 'reason': '不存在'})
                    continue
                if not quality_service.is_deletable(row):
                    rejected.append({'video_id': video_id, 'reason': '当前数据已不再满足可删规则'})
                    continue
                cursor.execute('DELETE FROM video_info WHERE video_id = %s', (video_id,))
                deleted += 1
            db.commit()
    finally:
        db_close(db)
    return {'deleted': deleted, 'rejected': rejected}


@app.get('/api/quality/export')
def quality_export(
    scope: str = Query('all', pattern='^(all|issues)$'),
    format: str = Query('csv', pattern='^(csv|xlsx)$'),
):
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM video_info')
            rows = cursor.fetchall()
    finally:
        db_close(db)
    if scope == 'issues':
        rows = [r for r in rows if quality_service.classify_row(r)]
    if format == 'xlsx':
        return Response(
            content=quality_service.build_xlsx(rows),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename="douyin_data.xlsx"'},
        )
    return Response(
        content=quality_service.build_csv(rows).encode('utf-8'),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="douyin_data.csv"'},
    )


class ExtensionVideosRequest(BaseModel):
    source_url: str
    videos: list[dict]


@app.post('/api/extension/videos')
def extension_receive(req: ExtensionVideosRequest):
    """浏览器插件数据接收器：校验 → 批次内去重 → 部分更新 upsert。"""
    valid, rejected = extension_receiver.validate_batch(req.model_dump())
    if not valid and not rejected:
        raise HTTPException(status_code=400, detail='没有可处理的记录')
    records = extension_receiver.dedupe_records(valid)
    db = get_db()
    try:
        with db.cursor() as cursor:
            for record in records:
                sql, params = extension_receiver.build_upsert(record)
                cursor.execute(sql, params)
            db.commit()
    finally:
        db_close(db)
    return {
        'source_url': req.source_url,
        'accepted': len(valid),
        'upserted': len(records),
        'rejected': rejected,
    }


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
DIST_DIR = os.path.join(FRONTEND_DIR, 'dist')

if os.path.isdir(DIST_DIR):
    # Vue 应用：/app 子路径部署，history 路由刷新由 SPA 兜底
    app.mount('/app/assets', StaticFiles(directory=os.path.join(DIST_DIR, 'assets')), name='frontend-assets')

    @app.get('/app')
    @app.get('/app/{full_path:path}')
    def frontend_spa(full_path: str = ''):
        index = os.path.join(DIST_DIR, 'index.html')
        if full_path:
            target = os.path.abspath(os.path.join(DIST_DIR, full_path))
            if target.startswith(os.path.abspath(DIST_DIR)) and os.path.isfile(target):
                return FileResponse(target)
        return FileResponse(index)



@app.get('/', include_in_schema=False)
def root_redirect():
    """根路径重定向到 Vue 应用。"""
    return RedirectResponse('/app/')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('api:app', host='0.0.0.0', port=8001, reload=False)
