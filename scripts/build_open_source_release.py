"""从主仓库生成开源发布包（白名单复制 + 默认模式替换 + 构建前端）。

运行：python scripts/build_open_source_release.py
输出：release/open-source/（git 初始化，不自动 push）
"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'release', 'open-source')
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'

KEEP_FILES = [
    'api.py', 'analyzer.py', 'cleanup_service.py', 'export_service.py',
    'extension_receiver.py', 'time_filter.py', 'run_backend.ps1', 'stop_backend.ps1',
    'local_config.example.py', 'LICENSE', '.gitignore',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.ts',
    'frontend/tsconfig.json', 'frontend/index.html', 'frontend/src/',
    'extension/', 'tests/', 'requirements.txt',
]

EXCLUDE_FILES = [
    'frontend/src/pages/Dashboard.vue',
    'frontend/src/pages/Collect.vue',
    'frontend/src/pages/Quality.vue',
    'frontend/src/pages/Queue.vue',
    'frontend/src/components/PieChart.vue',
]


def replace_default_mode(text: str) -> str:
    return text.replace("'unlimited'", "'limited'").replace('"unlimited"', '"limited"')


def replace_cleanup_storage(text: str) -> str:
    return text.replace("CLEANUP_STORAGE = 'redis'", "CLEANUP_STORAGE = 'json'")


def fix_gitignore(text: str) -> str:
    """开源包需提交 frontend/dist（构建产物），只忽略 node_modules。"""
    return text.replace('frontend/dist/\n', '')


def _copy(path):
    src = os.path.join(ROOT, path)
    dst = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def _trim_frontend():
    """开源版前端只保留「视频数据」「个人分析」两个路由与菜单。"""
    router = os.path.join(OUT, 'frontend', 'src', 'router', 'index.ts')
    with open(router, 'w', encoding='utf-8') as f:
        f.write("""import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'

export default createRouter({
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', name: 'videos', component: () => import('../pages/Videos.vue'), meta: { title: '视频数据' } },
        { path: 'personal', name: 'personal', component: () => import('../pages/PersonalAnalyzer.vue'), meta: { title: '个人分析' } },
      ],
    },
  ],
})
""")
    layout = os.path.join(OUT, 'frontend', 'src', 'layouts', 'MainLayout.vue')
    with open(layout, 'r', encoding='utf-8') as f:
        text = f.read()
    text = text.replace(
        "  { index: '/', label: '数据总览' },\n"
        "  { index: '/queue', label: '爬虫复核' },\n"
        "  { index: '/videos', label: '视频数据' },\n"
        "  { index: '/collect', label: '爬虫任务导入' },\n"
        "  { index: '/quality', label: '数据质量' },\n"
        "  { index: '/personal', label: '个人分析' },\n",
        "  { index: '/', label: '视频数据' },\n"
        "  { index: '/personal', label: '个人分析' },\n",
    )
    with open(layout, 'w', encoding='utf-8') as f:
        f.write(text)


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for path in KEEP_FILES:
        if os.path.exists(os.path.join(ROOT, path)):
            _copy(path)
    for rel in EXCLUDE_FILES:
        p = os.path.join(OUT, rel)
        if os.path.exists(p):
            os.remove(p)
    # 覆盖为开源版 README 与精简 requirements
    shutil.copy2(os.path.join(ROOT, 'scripts', 'open_source_README.md'), os.path.join(OUT, 'README.md'))
    shutil.copy2(os.path.join(ROOT, 'scripts', 'open_source_requirements.txt'), os.path.join(OUT, 'requirements.txt'))
    shutil.copy2(os.path.join(ROOT, 'scripts', 'open_source_api.py'), os.path.join(OUT, 'api.py'))
    example = os.path.join(OUT, 'local_config.example.py')
    with open(example, 'r', encoding='utf-8') as f:
        text = f.read()
    with open(example, 'w', encoding='utf-8') as f:
        f.write(replace_cleanup_storage(text))
    gitignore = os.path.join(OUT, '.gitignore')
    with open(gitignore, 'r', encoding='utf-8') as f:
        text = f.read()
    with open(gitignore, 'w', encoding='utf-8') as f:
        f.write(fix_gitignore(text))
    _trim_frontend()
    for rel in ('extension/options/options.js', 'extension/content/collect.js'):
        p = os.path.join(OUT, rel)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                text = f.read()
            with open(p, 'w', encoding='utf-8') as f:
                f.write(replace_default_mode(text))
    frontend = os.path.join(OUT, 'frontend')
    subprocess.run([NPM, 'install'], cwd=frontend, check=True)
    subprocess.run([NPM, 'run', 'build'], cwd=frontend, check=True)
    subprocess.run(['git', 'init'], cwd=OUT, check=True)
    print(f'开源包已生成：{OUT}')
    print('请 review 后自行推送到开源仓库（脚本不自动 push）。')


if __name__ == '__main__':
    build()
