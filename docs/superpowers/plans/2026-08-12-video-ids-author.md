# video_ids.txt 作者归属 + 收集页表格（P2-B）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 文件行格式扩展为 `id|status|author_id`，插件上报记录作者；接口返回作者信息；收集页第三个 tab 表格化（状态/作者筛选、切状态、删行）。

**Architecture:** 纯逻辑 owner 为 `extension_receiver.py`（三列解析、带作者读写、批量设状态、历史补全函数），`api.py` 薄层接线，`Collect.vue` 表格化展示。

**Tech Stack:** Python 3 + pytest；Vue3 + Element Plus。

**Spec:** `docs/superpowers/specs/2026-08-12-video-ids-author-design.md`

---

### Task 1: 纯函数（extension_receiver.py，TDD）

**Files:**
- Modify: `tests/test_extension_receiver.py`
- Modify: `extension_receiver.py`

- [ ] **Step 1: 更新测试（含失败新用例）**

`tests/test_extension_receiver.py` import 追加 `backfill_authors`、`set_ids_status`：
```python
from extension_receiver import (
    MAX_BATCH,
    append_ids_file,
    backfill_authors,
    build_upsert,
    dedupe_records,
    evaluate_write_guard,
    filter_pending_ids,
    is_allowed_origin,
    is_valid_token,
    mark_ids_done,
    normalize_record,
    parse_count,
    parse_datetime,
    parse_id_line,
    read_ids_file,
    read_ids_with_status,
    set_ids_status,
    validate_batch,
    validate_source_url,
    validate_video_id,
    write_ids_file,
)
```

替换/新增以下测试：
```python
def test_parse_id_line():
    assert parse_id_line('123') == ('123', 'pending', '')
    assert parse_id_line('123|done') == ('123', 'done', '')
    assert parse_id_line('123|pending|authorA') == ('123', 'pending', 'authorA')
    assert parse_id_line('123|bad') == ('123', 'pending', '')
    assert parse_id_line('123|done|a|extra') == ('123', 'done', 'a')
    assert parse_id_line('') is None
    assert parse_id_line('|x') is None


def test_read_ids_with_status_parses_mixed_lines(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a\nb|done\nc|pending|authorC\n', encoding='utf-8')
    assert read_ids_with_status(str(path)) == [
        {'video_id': 'a', 'status': 'pending', 'author_id': ''},
        {'video_id': 'b', 'status': 'done', 'author_id': ''},
        {'video_id': 'c', 'status': 'pending', 'author_id': 'authorC'},
    ]


def test_append_ids_file_with_author(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|done|oldAuthor\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['a', 'b'], author_id='newAuthor')
    assert (added, total) == (1, 2)
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending|newAuthor', 'b|pending|newAuthor']


def test_append_ids_file_without_author_keeps_existing(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending|authorA\n', encoding='utf-8')
    added, total = append_ids_file(str(path), ['a'])
    assert (added, total) == (0, 1)
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending|authorA']


def test_set_ids_status_changes_and_appends(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending|authorA\nb|done\n', encoding='utf-8')
    changed = set_ids_status(str(path), ['a', 'b', 'c'], 'pending')
    assert changed == 2
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending|authorA', 'b|pending', 'c|pending']


def test_mark_ids_done_keeps_author(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending|authorA\n', encoding='utf-8')
    mark_ids_done(str(path), ['a'])
    assert path.read_text(encoding='utf-8').splitlines() == ['a|done|authorA']


def test_write_ids_file_preserves_status_and_author(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|done|authorA\nb|pending\n', encoding='utf-8')
    assert write_ids_file(str(path), ['b', 'c']) == 2
    assert path.read_text(encoding='utf-8').splitlines() == ['b|pending', 'c|pending']


def test_backfill_authors_fills_unknown_only(tmp_path):
    path = tmp_path / 'video_ids.txt'
    path.write_text('a|pending\nb|done|authorB\n', encoding='utf-8')
    changed = backfill_authors(str(path), {'a': 'authorA', 'b': 'other'})
    assert changed == 1
    assert path.read_text(encoding='utf-8').splitlines() == ['a|pending|authorA', 'b|done|authorB']
```

保留 `test_append_ids_file_merges_and_returns_counts` 等旧用例时注意其断言更新为三列格式（文件内容 `a|pending` 等不变，因为 author 为空）。

- [ ] **Step 2: 运行确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: FAIL（`parse_id_line` 返回 2 元组、`append_ids_file` 不接受 author_id、`set_ids_status`/`backfill_authors` 缺失）。

- [ ] **Step 3: 实现 extension_receiver.py**

3.1 `parse_id_line` 改为三元组：
```python
def parse_id_line(line: str):
    """解析一行：'id' / 'id|status' / 'id|status|author'；空行/空 id 返回 None。"""
    text = (line or '').strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split('|')]
    video_id = parts[0]
    if not video_id:
        return None
    status = parts[1] if len(parts) > 1 and parts[1] in ('pending', 'done') else 'pending'
    author = parts[2] if len(parts) > 2 else ''
    return video_id, status, author
```

3.2 `read_ids_with_status` 返回三列：
```python
def read_ids_with_status(path: str) -> list[dict]:
    """读取并解析每行，返回 [{video_id, status, author_id}]，保序。"""
    records = []
    for line in _read_ids(path):
        parsed = parse_id_line(line)
        if parsed:
            records.append({'video_id': parsed[0], 'status': parsed[1], 'author_id': parsed[2]})
    return records
```

3.3 `_write_ids_records` 按作者是否为空写两列或三列：
```python
def _write_ids_records(path: str, records: list[dict]) -> None:
    """按 'id|status[|author]' 原子写入。"""
    lines = []
    for r in records:
        line = f"{r['video_id']}|{r['status']}"
        if r.get('author_id'):
            line += f"|{r['author_id']}"
        lines.append(line)
    _write_ids_atomic(path, lines)
```

3.4 `append_ids_file` 加 author_id 参数：
```python
def append_ids_file(path: str, new_ids: list[str], author_id: str = '') -> tuple[int, int]:
    """合并插件采集 id：新行带作者；已存在重置 pending 且 author 非空时更新作者。返回 (新增数, 总行数)。"""
    author = (author_id or '').strip()
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            records = read_ids_with_status(path)
            existing = {r['video_id'] for r in records}
            added = 0
            for vid in new_ids:
                vid = (vid or '').strip()
                if not vid:
                    continue
                if vid not in existing:
                    records.append({'video_id': vid, 'status': 'pending', 'author_id': author})
                    existing.add(vid)
                    added += 1
                else:
                    for r in records:
                        if r['video_id'] == vid:
                            r['status'] = 'pending'
                            if author:
                                r['author_id'] = author
                            break
            _write_ids_records(path, records)
            return added, len(records)
        finally:
            _unlock_ids_file(fh)
```

3.5 `mark_ids_done` 改为走通用 `set_ids_status`，并新增 `set_ids_status`、`backfill_authors`：
```python
def set_ids_status(path: str, ids: list[str], status: str) -> int:
    """批量设状态（pending/done）；不存在的追加。返回实际变化行数。"""
    if status not in ('pending', 'done'):
        raise ValueError('status 必须是 pending 或 done')
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            records = read_ids_with_status(path)
            by_id = {r['video_id']: r for r in records}
            changed = 0
            for vid in ids:
                vid = (vid or '').strip()
                if not vid:
                    continue
                record = by_id.get(vid)
                if record is None:
                    records.append({'video_id': vid, 'status': status, 'author_id': ''})
                    by_id[vid] = records[-1]
                    changed += 1
                elif record['status'] != status:
                    record['status'] = status
                    changed += 1
            if changed:
                _write_ids_records(path, records)
            return changed
        finally:
            _unlock_ids_file(fh)


def mark_ids_done(path: str, ids: list[str]) -> int:
    return set_ids_status(path, ids, 'done')
```

3.6 `write_ids_file` 保留状态+作者：
```python
def write_ids_file(path: str, ids: list[str]) -> int:
    """前端纯 id 全量覆盖：保留已有状态+作者，新 id 记 (pending, 空作者)。返回写入条数。"""
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            old = {r['video_id']: (r['status'], r['author_id']) for r in read_ids_with_status(path)}
            records = []
            seen = set()
            for vid in ids:
                vid = (vid or '').strip()
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                status, author = old.get(vid, ('pending', ''))
                records.append({'video_id': vid, 'status': status, 'author_id': author})
            _write_ids_records(path, records)
            return len(records)
        finally:
            _unlock_ids_file(fh)
```

3.7 新增 `backfill_authors`（放在 `filter_pending_ids` 之前）：
```python
def backfill_authors(path: str, author_map: dict) -> int:
    """把 unknown（author 空）行的作者按 map 补全；已有作者不动。返回更新行数。"""
    with _IDS_FILE_LOCK:
        fh = _lock_ids_file(path)
        try:
            records = read_ids_with_status(path)
            changed = 0
            for r in records:
                if not r['author_id'] and r['video_id'] in author_map:
                    r['author_id'] = author_map[r['video_id']]
                    changed += 1
            if changed:
                _write_ids_records(path, records)
            return changed
        finally:
            _unlock_ids_file(fh)
```

- [ ] **Step 4: 运行确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_extension_receiver.py -q`
Expected: 全部 PASS。

---

### Task 2: api.py 接线

**Files:**
- Modify: `api.py`

- [ ] **Step 1: POST /api/extension/ids 传作者**

`extension_save_ids` 中调用改为：
```python
    added, total = extension_receiver.append_ids_file(
        VIDEO_IDS_PATH, cleaned, author_id=(req.author_id or '').strip(),
    )
```

- [ ] **Step 2: GET /api/extension/ids 返回 items**

```python
@app.get('/api/extension/ids')
def extension_list_ids():
    """返回 video_ids.txt 的数量、纯 id 列表与带状态/作者明细，供前端查看/导入爬虫队列。"""
    records = extension_receiver.read_ids_with_status(VIDEO_IDS_PATH)
    return {
        'total': len(records),
        'video_ids': [r['video_id'] for r in records],
        'items': records,
    }
```

- [ ] **Step 3: 新增 POST /api/extension/ids/status**

在 `extension_replace_ids` 之后追加：
```python
class ExtensionIdsStatusRequest(BaseModel):
    video_ids: list[str]
    status: str


@app.post('/api/extension/ids/status', dependencies=[Depends(verify_write_guard)])
def extension_set_ids_status(req: ExtensionIdsStatusRequest):
    """批量切换 id 状态（pending/done），供前端强制重爬/标记。"""
    if req.status not in ('pending', 'done'):
        raise HTTPException(status_code=400, detail='status 必须是 pending 或 done')
    cleaned: list[str] = []
    rejected: list[str] = []
    for vid in req.video_ids:
        vid = (vid or '').strip()
        if extension_receiver.validate_video_id(vid):
            cleaned.append(vid)
        else:
            rejected.append(vid)
    if not cleaned:
        raise HTTPException(status_code=400, detail='没有合法的 video_id')
    updated = extension_receiver.set_ids_status(VIDEO_IDS_PATH, cleaned, req.status)
    return {'updated': updated, 'rejected': rejected}
```

- [ ] **Step 4: 运行回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS。

---

### Task 3: 前端 Collect.vue 表格化

**Files:**
- Modify: `frontend/src/pages/Collect.vue`

- [ ] **Step 1: script 部分**

`import { nextTick, ref, watch } from 'vue'` 改为：
```ts
import { computed, nextTick, ref, watch } from 'vue'
```

把「标签三」整段（`// ---------- 标签三：video_ids.txt 直接编辑 ----------` 起，到 `copyIdsFile` 结束）替换为：
```ts
// ---------- 标签三：video_ids.txt 管理（表格） ----------
interface IdsItem {
  video_id: string
  status: 'pending' | 'done'
  author_id: string
}

const idsItems = ref<IdsItem[]>([])
const idsCount = ref(0)
const idsLoading = ref(false)
const idsSaving = ref(false)
const idsImporting = ref(false)
const statusFilter = ref('all')
const authorFilter = ref('all')
const newIdsText = ref('')

const authorOptions = computed(() => {
  const set = new Set<string>(idsItems.value.map((i) => i.author_id || ''))
  return Array.from(set).map((a) => ({ value: a, label: a || '未知' }))
})

const filteredItems = computed(() => {
  return idsItems.value.filter((i) => {
    if (statusFilter.value !== 'all' && i.status !== statusFilter.value) return false
    if (authorFilter.value !== 'all' && (i.author_id || '') !== authorFilter.value) return false
    return true
  })
})

const pendingCount = computed(() => idsItems.value.filter((i) => i.status === 'pending').length)
const doneCount = computed(() => idsItems.value.length - pendingCount.value)

async function loadIdsFile() {
  idsLoading.value = true
  try {
    const res = await api.get<{ total: number; video_ids: string[]; items?: IdsItem[] }>('/extension/ids')
    idsItems.value = res.data.items ?? []
    idsCount.value = res.data.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    idsLoading.value = false
  }
}

async function toggleStatus(row: IdsItem) {
  const next = row.status === 'pending' ? 'done' : 'pending'
  try {
    await api.post('/extension/ids/status', { video_ids: [row.video_id], status: next })
    row.status = next
    ElMessage.success(`已标记为${next === 'pending' ? '待采集' : '已采集'}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '切换失败')
  }
}

function removeRow(row: IdsItem) {
  idsItems.value = idsItems.value.filter((i) => i.video_id !== row.video_id)
}

function addNewIds() {
  const all = newIdsText.value
    .split(/[\n,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const seen = new Set(idsItems.value.map((i) => i.video_id))
  let added = 0
  for (const id of all) {
    if (/^\d{15,20}$/.test(id) && !seen.has(id)) {
      seen.add(id)
      idsItems.value.push({ video_id: id, status: 'pending', author_id: '' })
      added++
    }
  }
  newIdsText.value = ''
  ElMessage.success(`新增 ${added} 条` + (all.length - added > 0 ? `，忽略 ${all.length - added} 条` : ''))
}

async function saveIdsFile() {
  const videoIds = idsItems.value.map((i) => i.video_id)
  if (!videoIds.length) {
    ElMessage.warning('文件为空')
    return
  }
  idsSaving.value = true
  try {
    await api.put('/extension/ids', { video_ids: videoIds, author_id: '' })
    await loadIdsFile()
    ElMessage.success(`已保存 ${videoIds.length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    idsSaving.value = false
  }
}

async function importIdsFile() {
  const videoIds = idsItems.value.map((i) => i.video_id)
  if (!videoIds.length) {
    ElMessage.warning('没有可导入的 ID')
    return
  }
  idsImporting.value = true
  try {
    const res = await api.post('/crawl', { video_ids: videoIds, task_type: 'video' })
    await loadIdsFile()
    ElMessage.success(
      `已导入 ${res.data.pushed} 条（跳过已采集 ${res.data.skipped ?? 0}），当前队列 ${res.data.queue_length} 条`,
    )
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '导入失败')
  } finally {
    idsImporting.value = false
  }
}

async function copyIdsFile() {
  try {
    await navigator.clipboard.writeText(idsItems.value.map((i) => i.video_id).join('\n'))
    ElMessage.success('已复制全部 ID')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}
```

- [ ] **Step 2: 模板部分**

把 `el-tab-pane label="video_ids.txt" name="idsfile"` 内的内容（从 `<el-card shadow="never" class="collect-card">` 到对应 `</el-card>`）替换为：
```html
        <el-card shadow="never" class="collect-card">
          <div class="paste-actions">
            <span class="ids-count">共 {{ idsCount }} 条（待采集 {{ pendingCount }} / 已采集 {{ doneCount }}）</span>
            <el-select v-model="authorFilter" size="small" style="width: 160px" placeholder="按作者筛选">
              <el-option label="全部作者" value="all" />
              <el-option v-for="opt in authorOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <el-select v-model="statusFilter" size="small" style="width: 120px" placeholder="按状态筛选">
              <el-option label="全部状态" value="all" />
              <el-option label="待采集" value="pending" />
              <el-option label="已采集" value="done" />
            </el-select>
            <el-button size="small" :loading="idsLoading" @click="loadIdsFile">刷新</el-button>
            <el-button size="small" type="primary" :loading="idsSaving" :disabled="!idsItems.length" @click="saveIdsFile">
              保存到文件
            </el-button>
            <el-button size="small" type="success" :loading="idsImporting" :disabled="!idsItems.length" @click="importIdsFile">
              导入爬虫队列
            </el-button>
            <el-button size="small" :disabled="!idsItems.length" @click="copyIdsFile">复制全部</el-button>
          </div>
          <div class="paste-actions" style="margin-top: 12px">
            <el-input
              v-model="newIdsText"
              size="small"
              placeholder="粘贴新增 ID（每行/逗号/空格分隔）"
              clearable
              style="max-width: 420px"
            />
            <el-button size="small" @click="addNewIds">新增</el-button>
          </div>
          <el-table :data="filteredItems" size="small" max-height="480" style="margin-top: 12px">
            <el-table-column prop="video_id" label="视频ID" width="210" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'done' ? 'success' : 'warning'" size="small">
                  {{ row.status === 'done' ? '已采集' : '待采集' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="作者" width="140">
              <template #default="{ row }">{{ row.author_id || '未知' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="toggleStatus(row)">
                  {{ row.status === 'done' ? '改为待采集' : '标记已采集' }}
                </el-button>
                <el-button size="small" link type="danger" @click="removeRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-alert
            type="info"
            :closable="false"
            title="插件采集自动追加 ID（带作者）到该文件；「保存到文件」覆盖写入并保留状态/作者；「导入爬虫队列」只推待采集 ID；「改为待采集」可强制重爬。"
            style="margin-top: 12px"
          />
        </el-card>
```

- [ ] **Step 3: build 验证**

Run（`frontend/`）: `npm run build`
Expected: 构建成功（vue-tsc 类型检查通过）。

---

### Task 4: README + 全量回归

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README 补充**

在「video_ids.txt 同步状态」小节补一行：
```markdown
- 行格式 `video_id|status|author_id`：插件上报的新 ID 带作者；作者为空显示「未知」；
  收集页可按作者/状态筛选，支持「改为待采集」强制重爬。
```

- [ ] **Step 2: 全量回归**

Run: `.\.venv\Scripts\python.exe -m pytest -q` → 全部 PASS；
Run（`extension/`）: `node --test` → 20 passed；
Run（`frontend/`）: `npm run build` → 构建成功。

---

### Task 5: 提交（需用户确认）

```bash
git -c safe.directory=D:/DjangoProject/PythonProject11 add extension_receiver.py api.py frontend/src/pages/Collect.vue tests/test_extension_receiver.py README.md docs/superpowers/specs/2026-08-12-video-ids-author-design.md docs/superpowers/plans/2026-08-12-video-ids-author.md
git -c safe.directory=D:/DjangoProject/PythonProject11 commit -m "feat: video_ids.txt 记录作者归属，收集页表格化管理（状态/作者筛选）"
```
