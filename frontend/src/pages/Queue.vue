<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '../api'

interface QueueItem {
  url: string
  type: string
}

interface SpiderStatus {
  running: boolean
  pid?: number | null
  started_at?: string | null
}

const queueLength = ref(0)
const items = ref<QueueItem[]>([])
const spider = ref<SpiderStatus | null>(null)
const logs = ref<string[]>([])
const loading = ref(false)
const starting = ref(false)
const stopping = ref(false)
const selectedItems = ref<QueueItem[]>([])
let timer: number | null = null

async function load() {
  try {
    const [q, s, l] = await Promise.all([
      api.get('/queue/items'),
      api.get('/spider/status'),
      api.get('/spider/log', { params: { lines: 30 } }),
    ])
    queueLength.value = q.data.queue_length
    items.value = q.data.items
    spider.value = s.data
    logs.value = l.data.lines || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载队列失败')
  } finally {
    loading.value = false
  }
}

function videoId(url: string) {
  const m = url.match(/\/video\/(\d+)/)
  return m ? m[1] : url
}

async function startSpider() {
  starting.value = true
  try {
    await api.post('/spider/start')
    ElMessage.success('爬虫已启动')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '启动失败')
  } finally {
    starting.value = false
  }
}

async function stopSpider() {
  stopping.value = true
  try {
    await api.post('/spider/stop')
    ElMessage.success('爬虫已停止')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '停止失败')
  } finally {
    stopping.value = false
  }
}

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

onMounted(() => {
  loading.value = true
  load()
  timer = window.setInterval(load, 5000)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<template>
  <div class="queue">
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never" class="q-card">
          <div class="q-label">队列长度</div>
          <div class="q-value" :style="{ color: queueLength ? 'var(--spider-success)' : undefined }">
            {{ queueLength }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="q-card">
          <div class="q-label">爬虫状态</div>
          <div class="q-value">
            <el-tag :type="spider?.running ? 'success' : 'info'">
              {{ spider?.running ? '运行中' : '已停止' }}
            </el-tag>
          </div>
          <div class="q-actions">
            <el-button
              type="success"
              size="small"
              :loading="starting"
              :disabled="spider?.running"
              @click="startSpider"
            >
              启动爬虫
            </el-button>
            <el-button
              type="danger"
              size="small"
              :loading="stopping"
              :disabled="!spider?.running"
              @click="stopSpider"
            >
              停止爬虫
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="q-card">
          <div class="q-label">PID / 启动时间</div>
          <div class="q-value small">{{ spider?.pid ?? '--' }}<template v-if="spider?.started_at"> · {{ new Date(spider.started_at).toLocaleString('zh-CN', { hour12: false }) }}</template></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="q-card">
      <template #header>
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
      </template>
      <el-table :data="items" size="small" max-height="360" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="46" />
        <el-table-column type="index" label="#" width="50" />
        <el-table-column label="视频ID" width="220">
          <template #default="{ row }">{{ videoId(row.url) }}</template>
        </el-table-column>
        <el-table-column prop="url" label="任务 URL" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="90" />
      </el-table>
      <el-empty v-if="items.length === 0" description="队列为空" :image-size="60" />
    </el-card>

    <el-card shadow="never" class="q-card">
      <template #header><span>爬虫日志（最近 30 行）</span></template>
      <pre class="q-log">{{ logs.length ? logs.join('\n') : '暂无日志' }}</pre>
    </el-card>
  </div>
</template>

<style scoped>
.q-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
.q-label {
  font-size: 12px;
  color: var(--spider-text-secondary);
}
.q-value {
  font-size: 24px;
  font-weight: 600;
  margin-top: 6px;
}
.q-value.small {
  font-size: 13px;
  font-weight: 400;
}
.q-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}
.q-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.q-log {
  margin: 0;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--spider-text-secondary);
}
</style>
