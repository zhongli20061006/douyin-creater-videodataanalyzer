# 作者昵称映射 + 收集页批量管理 id 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收集页作者列显示昵称（库映射），表格支持多选批量标记状态与批量删除。

**Architecture:** `extension_receiver.attach_author_names` 纯函数附加昵称；`api.py` GET ids 查库构建映射；`Collect.vue` 加多选与批量操作。

**Tech Stack:** Python 3 + pytest；Vue3 + Element Plus。

**Spec:** `docs/superpowers/specs/2026-08-12-ids-author-name-batch-design.md`

---

### Task 1: attach_author_names 纯函数（TDD）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 写失败测试**

`tests/test_extension_receiver.py` import 追加 `attach_author_names`，文件末尾追加：
```python
def test_attach_author_names():
    items = [
        {'video_id': 'a', 'status': 'pending', 'author_id': 'A'},
        {'video_id': 'b', 'status': 'done', 'author_id': ''},
    ]
    result = attach_author_names(items, {'A': '平原公子'})
    assert result[0]['author_name'] == '平原公子'
    assert result[1]['author_name'] == ''
    assert 'author_name' not in items[0]
```

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: FAIL（`cannot import name 'attach_author_names'`）。

- [ ] **Step 3: 最小实现**

`extension_receiver.py` 末尾（`filter_pending_ids` 之后）追加：
```python
def attach_author_names(items: list[dict], author_map: dict) -> list[dict]:
    """给 items 每项附加 author_name（来自 author_map，缺失保持空串）；不修改原列表。"""
    result = []
    for item in items:
        row = dict(item)
        row['author_name'] = author_map.get(row.get('author_id') or '', '')
        result.append(row)
    return result
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: 全部 PASS。

---

### Task 2: api.py GET ids 昵称映射

**Files:**
- Modify: `api.py`

- [ ] **Step 1: 改造 extension_list_ids**

```python
@app.get('/api/extension/ids')
def extension_list_ids():
    """返回 video_ids.txt 的数量、纯 id 列表与带状态/作者/昵称明细。"""
    records = extension_receiver.read_ids_with_status(VIDEO_IDS_PATH)
    author_ids = {r['author_id'] for r in records if r['author_id']}
    author_map: dict = {}
    if author_ids:
        db = get_db()
        try:
            with db.cursor() as cursor:
                placeholders = ', '.join(['%s'] * len(author_ids))
                cursor.execute(
                    f'SELECT DISTINCT author_id, author_name FROM video_info '
                    f'WHERE author_id IN ({placeholders})',
                    tuple(author_ids),
                )
                for row in cursor.fetchall():
                    author_map[row['author_id']] = row['author_name'] or ''
        finally:
            db_close(db)
    items = extension_receiver.attach_author_names(records, author_map)
    return {
        'total': len(records),
        'video_ids': [r['video_id'] for r in records],
        'items': items,
    }
```

- [ ] **Step 2: 运行回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS。

---

### Task 3: 前端 Collect.vue 批量管理 + 昵称显示

**Files:**
- Modify: `frontend/src/pages/Collect.vue`

- [ ] **Step 1: script 部分**

`IdsItem` 接口加昵称字段，新增选中与批量方法（在 `removeRow` 之前插入）：
```ts
interface IdsItem {
  video_id: string
  status: 'pending' | 'done'
  author_id: string
  author_name?: string
}
```

```ts
const selectedIds = ref<IdsItem[]>([])

function onIdsSelectionChange(rows: IdsItem[]) {
  selectedIds.value = rows
}

async function batchSetStatus(status: 'pending' | 'done') {
  const ids = selectedIds.value.map((i) => i.video_id)
  if (!ids.length) {
    ElMessage.warning('请先勾选要操作的 ID')
    return
  }
  try {
    await api.post('/extension/ids/status', { video_ids: ids, status })
    await loadIdsFile()
    ElMessage.success(`已批量标记为${status === 'pending' ? '待采集' : '已采集'} ${ids.length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
  }
}

async function batchDelete() {
  const ids = new Set(selectedIds.value.map((i) => i.video_id))
  if (!ids.size) {
    ElMessage.warning('请先勾选要删除的 ID')
    return
  }
  try {
    const remain = idsItems.value.filter((i) => !ids.has(i.video_id)).map((i) => i.video_id)
    await api.put('/extension/ids', { video_ids: remain, author_id: '' })
    await loadIdsFile()
    ElMessage.success(`已删除 ${ids.size} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}
```

- [ ] **Step 2: 模板部分**

2.1 第二行操作栏（新增 ID 那行）末尾追加三个批量按钮：
```html
            <el-button size="small" :disabled="!selectedIds.length" @click="batchSetStatus('pending')">
              批量待采集
            </el-button>
            <el-button size="small" :disabled="!selectedIds.length" @click="batchSetStatus('done')">
              批量已采集
            </el-button>
            <el-button size="small" type="danger" :disabled="!selectedIds.length" @click="batchDelete">
              批量删除
            </el-button>
```

2.2 表格加多选列并绑定选择事件：
```html
          <el-table
            :data="filteredItems"
            size="small"
            max-height="480"
            style="margin-top: 12px"
            @selection-change="onIdsSelectionChange"
          >
            <el-table-column type="selection" width="46" />
            <el-table-column prop="video_id" label="视频ID" width="210" />
```

2.3 作者列改为显示昵称：
```html
            <el-table-column label="作者" width="140">
              <template #default="{ row }">{{ row.author_name || row.author_id || '未知' }}</template>
            </el-table-column>
```

- [ ] **Step 3: build 验证**

Run（`frontend/`）: `npm run build`
Expected: 构建成功。

---

### Task 4: 重启后端真库验证 + 全量回归

- [ ] **Step 1: 重启后端**

Run: `.\stop_backend.ps1` 后 `.\run_backend.ps1`（用户已授权重启）。

- [ ] **Step 2: 真库验证 GET ids**

`GET http://127.0.0.1:8001/api/extension/ids` → items 含 `author_name`（如作者 4358913414407163 对应昵称非空）。

- [ ] **Step 3: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 全部 PASS；
Run（`extension/`）: `node --test` → 全部 PASS；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py api.py frontend/src/pages/Collect.vue tests/test_extension_receiver.py docs/superpowers/specs/2026-08-12-ids-author-name-batch-design.md docs/superpowers/plans/2026-08-12-ids-author-name-batch.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: 收集页作者昵称映射 + 批量管理 id"
```
