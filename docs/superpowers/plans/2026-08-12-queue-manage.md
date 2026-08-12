# 爬虫队列管理功能 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端新增清空/批量移除队列接口，前端队列监控页支持「移除选中」「清空队列」。

**Architecture:** `queue_service.remove_items` 纯函数筛选（保序）；`api.py` 薄层接线（DEL + RPUSH 重建）；`Queue.vue` 表格多选与管理按钮。

**Tech Stack:** Python 3 + pytest；Vue3 + Element Plus；Redis。

**Spec:** `docs/superpowers/specs/2026-08-12-queue-manage-design.md`

---

### Task 1: remove_items 纯函数（TDD）

**Files:**
- Modify: `tests/test_queue.py`
- Modify: `queue_service.py`

- [ ] **Step 1: 写失败测试**

`tests/test_queue.py` 追加：
```python
import json

from queue_service import parse_queue_item, remove_items


def test_remove_items_removes_matching_video_ids():
    raws = [
        json.dumps({'url': 'https://www.douyin.com/video/111', 'type': 'video'}),
        json.dumps({'url': 'https://www.douyin.com/video/222', 'type': 'video'}),
        json.dumps({'url': 'https://www.douyin.com/video/333', 'type': 'video'}),
    ]
    kept = remove_items(raws, ['222'])
    assert len(kept) == 2
    assert all('222' not in x for x in kept)


def test_remove_items_empty_targets_keeps_all():
    raws = ['a', 'b']
    assert remove_items(raws, []) == ['a', 'b']


def test_remove_items_preserves_order():
    raws = ['a', 'b', 'c']
    assert remove_items(raws, ['b']) == ['a', 'c']
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_queue.py -q`
Expected: FAIL（`cannot import name 'remove_items'`）。

- [ ] **Step 3: 实现 queue_service.py**

追加：
```python
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
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_queue.py -q`
Expected: 全部 PASS。

---

### Task 2: api.py 队列管理接口

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 新增接口**

在 `get_queue_items` 之后追加：
```python
class QueueRemoveRequest(BaseModel):
    video_ids: list[str]


@app.post('/api/queue/clear', dependencies=[Depends(verify_write_guard)])
def queue_clear():
    """清空 Redis 爬虫队列。"""
    try:
        r = get_redis()
        r.delete(REDIS_START_URLS_KEY)
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {'cleared': True}


@app.post('/api/queue/remove', dependencies=[Depends(verify_write_guard)])
def queue_remove(req: QueueRemoveRequest):
    """按 video_id 批量移除队列条目（保序重建）。"""
    cleaned = [vid.strip() for vid in req.video_ids if vid and vid.strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail='没有合法的 video_id')
    try:
        r = get_redis()
        raws = r.lrange(REDIS_START_URLS_KEY, 0, -1)
        kept = queue_service.remove_items(raws, cleaned)
        removed = len(raws) - len(kept)
        if removed:
            r.delete(REDIS_START_URLS_KEY)
            if kept:
                r.rpush(REDIS_START_URLS_KEY, *kept)
        queue_length = r.llen(REDIS_START_URLS_KEY)
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail='Redis 服务不可用')
    return {'removed': removed, 'queue_length': queue_length}
```

- [ ] **Step 2: 运行回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS。

---

### Task 3: 前端 Queue.vue

**Files:**
- Modify: `frontend/src/pages/Queue.vue`

- [ ] **Step 1: script**

`import { ElMessage } from 'element-plus'` 改为：
```ts
import { ElMessage, ElMessageBox } from 'element-plus'
```

在 `const stopping = ref(false)` 之后追加：
```ts
const selectedItems = ref<QueueItem[]>([])

function onSelectionChange(rows: QueueItem[]) {
  selectedItems.value = rows
}

async function removeSelected() {
  const ids = selectedItems.value.map((i) => videoId(i.url))
  if (!ids.length) {
    ElMessage.warning('请先勾选要移除的任务')
    return
  }
  try {
    await api.post('/queue/remove', { video_ids: ids })
    ElMessage.success(`已移除 ${ids.length} 条`)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '移除失败')
  }
}

async function clearQueue() {
  try {
    await ElMessageBox.confirm('确定清空整个爬虫队列吗？该操作不可恢复。', '清空队列', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.post('/queue/clear')
    ElMessage.success('队列已清空')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '清空失败')
  }
}
```

- [ ] **Step 2: 模板**

2.1 队列卡片 header 追加按钮：
```html
        <div class="q-header">
          <span>队列内容（每 5 秒自动刷新）</span>
          <div>
            <el-button size="small" :disabled="!selectedItems.length" @click="removeSelected">
              移除选中
            </el-button>
            <el-button size="small" type="danger" :disabled="!queueLength" @click="clearQueue">
              清空队列
            </el-button>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
```

2.2 表格加多选列：
```html
      <el-table :data="items" size="small" max-height="360" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="46" />
        <el-table-column type="index" label="#" width="50" />
```

- [ ] **Step 3: build 验证**

Run（`frontend/`）: `npm run build`
Expected: 构建成功。

---

### Task 4: 重启后端 + 实测 + 全量回归

- [ ] **Step 1: 重启后端**

Run: `.\stop_backend.ps1` 后 `.\run_backend.ps1`。

- [ ] **Step 2: 实测（用户已授权可动队列）**

带令牌调用：
- `POST /api/queue/clear` → `{cleared: true}`，队列长度 0；
- 重新推入几条测试任务（`POST /api/crawl` 或 Redis LPUSH）→ `POST /api/queue/remove {video_ids: [...]}` → `{removed, queue_length}` 正确；
- 测试后清空队列。

- [ ] **Step 3: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 全部 PASS；
Run（`extension/`）: `node --test` → 全部 PASS；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add queue_service.py api.py frontend/src/pages/Queue.vue tests/test_queue.py docs/superpowers/specs/2026-08-12-queue-manage-design.md docs/superpowers/plans/2026-08-12-queue-manage.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 爬虫队列管理（清空/批量移除）"
```
