<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'

import api from '../api'

interface PreviewVideo {
  video_id: string
  video_title: string
  like_count: number
  author_name: string
}

const url = ref('')
const loading = ref(false)
const pushing = ref(false)
const videos = ref<PreviewVideo[]>([])
const selected = ref<PreviewVideo[]>([])
const queueLength = ref<number | null>(null)
const tableRef = ref<{ toggleAllSelection: () => void } | null>(null)

async function collect() {
  if (!url.value.trim()) {
    ElMessage.warning('请输入作者主页链接')
    return
  }
  loading.value = true
  try {
    const res = await api.post('/collect/author', { author_url: url.value.trim() })
    videos.value = res.data.videos
    queueLength.value = null
    await nextTick()
    tableRef.value?.toggleAllSelection()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '收集失败')
  } finally {
    loading.value = false
  }
}

function onSelectionChange(rows: PreviewVideo[]) {
  selected.value = rows
}

function fmtLike(n: number) {
  if (!n) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return String(n)
}

async function pushToQueue() {
  const ids = selected.value.map((v) => v.video_id)
  if (!ids.length) {
    ElMessage.warning('请先勾选要加入队列的视频')
    return
  }
  pushing.value = true
  try {
    const res = await api.post('/crawl', { video_ids: ids, task_type: 'video' })
    queueLength.value = res.data.queue_length
    ElMessage.success(`已加入 ${res.data.pushed} 条，当前队列 ${res.data.queue_length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加入队列失败')
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <div class="collect">
    <el-card shadow="never" class="collect-card flex">
      <el-input
        v-model="url"
        placeholder="粘贴抖音作者主页链接，如 https://www.douyin.com/user/xxxx"
        clearable
        style="max-width: 640px"
        @keyup.enter="collect"
      />
      <el-button type="primary" :loading="loading" @click="collect">收集</el-button>
    </el-card>

    <el-card v-if="videos.length" shadow="never" class="collect-card">
      <template #header>
        <div class="collect-header">
          <span>共 {{ videos.length }} 条（默认全选，可取消勾选）</span>
          <el-button type="success" :loading="pushing" @click="pushToQueue">
            加入队列（{{ selected.length }} 条）
          </el-button>
        </div>
      </template>
      <el-table
        ref="tableRef"
        :data="videos"
        size="small"
        max-height="480"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column prop="video_id" label="视频ID" width="200" />
        <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
        <el-table-column prop="author_name" label="作者" width="140" />
        <el-table-column label="点赞" width="100">
          <template #default="{ row }">{{ fmtLike(row.like_count) }}</template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="queueLength !== null"
        type="success"
        :title="'当前队列长度: ' + queueLength"
        :closable="false"
        style="margin-top: 12px"
      />
    </el-card>

    <el-empty v-else-if="!loading" description="输入作者主页链接后点击「收集」，可预览视频并加入队列" />
  </div>
</template>

<style scoped>
.collect-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
.collect-card.flex :deep(.el-card__body) {
  display: flex;
  gap: 12px;
  align-items: center;
}
.collect-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
