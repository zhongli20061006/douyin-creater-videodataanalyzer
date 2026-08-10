import json
import redis
import argparse
import os


def batch_push(video_file, redis_host='localhost', redis_port=6379):
    if not os.path.exists(video_file):
        print(f"❌ 文件不存在: {video_file}")
        print(f"💡 当前目录下的文件:")
        for f in os.listdir('.'):
            if f.endswith('.txt'):
                print(f"   - {f}")
        return

    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    key = 'douyin:start_urls'
    count = 0
    with open(video_file, 'r', encoding='utf-8') as f:
        for line in f:
            vid = line.strip()
            if vid:
                task = json.dumps({'url': f'https://www.douyin.com/video/{vid}', 'type': 'video'})
                r.lpush(key, task)
                count += 1
                print(f"✅ 已推送: {vid}")
    print(f"\n 共推送 {count} 个视频任务，当前队列长度: {r.llen(key)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default='video_ids.txt', help='视频ID列表文件，每行一个ID（默认：video_ids.txt）')
    parser.add_argument('--redis-host', default='localhost')
    parser.add_argument('--redis-port', type=int, default=6379)
    args = parser.parse_args()
    batch_push(args.file, args.redis_host, args.redis_port)
