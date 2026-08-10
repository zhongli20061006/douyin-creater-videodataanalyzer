# start_server.py
"""启动抖音爬虫管理面板 Web 服务"""
import os
import sys
import subprocess
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))


def install_deps():
    req = os.path.join(ROOT, 'requirements.txt')
    if os.path.exists(req):
        print('--- 检查依赖...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', req, '-q'])


def start_api(host='0.0.0.0', port=8000, reload=False):
    cmd = [sys.executable, '-m', 'uvicorn', 'api:app', '--host', host, '--port', str(port)]
    if reload:
        cmd.append('--reload')
    print('--- 启动管理面板: http://{}:{}'.format(host, port))
    os.chdir(ROOT)
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description='抖音爬虫管理面板启动器')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8001, help='监听端口 (默认: 8001)')
    parser.add_argument('--reload', action='store_true', help='启用热重载 (开发模式)')
    parser.add_argument('--install', action='store_true', help='安装依赖')
    args = parser.parse_args()

    if args.install:
        install_deps()

    start_api(args.host, args.port, args.reload)


if __name__ == '__main__':
    main()
