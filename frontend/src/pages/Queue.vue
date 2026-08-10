<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

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
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <el-table :data="items" size="small" max-height="360">
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
