<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import api from '../api'

const ids = ref<string[]>([])
const total = ref(0)
const loading = ref(false)
const importing = ref(false)
const queueLength = ref<number | null>(null)

const idsText = computed(() => ids.value.join('\n'))

async function load() {
  loading.value = true
  try {
    const res = await api.get<{ total: number; video_ids: string[] }>('/extension/ids')
    ids.value = res.data.video_ids ?? []
    total.value = res.data.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function importToQueue() {
  if (!ids.value.length) {
    ElMessage.warning('没有可导入的 ID')
    return
  }
  importing.value = true
  try {
    const res = await api.post('/crawl', { video_ids: ids.value, task_type: 'video' })
    queueLength.value = res.data.queue_length
    ElMessage.success(`已导入 ${res.data.pushed} 条，当前队列 ${res.data.queue_length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(idsText.value)
    ElMessage.success('已复制全部 ID')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

onMounted(load)
</script>

<template>
  <div class="video-ids">
    <el-card shadow="never" class="v-card toolbar">
      <span class="label">视频 ID 总数：</span>
      <b class="count">{{ total }}</b>
      <span class="hint">来自 video_ids.txt（插件采集后自动去重写入），可导入爬虫队列刷新数据</span>
      <div class="actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :loading="importing" :disabled="!ids.length" @click="importToQueue">
          导入爬虫队列
        </el-button>
        <el-button :disabled="!ids.length" @click="copyAll">复制全部</el-button>
      </div>
    </el-card>

    <el-alert
      v-if="queueLength !== null"
      type="success"
      :title="'导入成功，当前爬虫队列长度：' + queueLength"
      :closable="false"
      style="margin-bottom: 12px"
    />

    <el-card shadow="never" class="v-card">
      <el-input
        v-model="idsText"
        type="textarea"
        :rows="18"
        readonly
        placeholder="暂无 ID，先去插件采集一次"
      />
      <div class="tip">每行一个视频 ID；用途：让爬虫按这些 ID 刷新 video_info 数据。</div>
    </el-card>
  </div>
</template>

<style scoped>
.v-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
.toolbar :deep(.el-card__body) {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.label {
  color: var(--spider-text-secondary);
  font-size: 14px;
}
.count {
  color: var(--spider-text);
  font-size: 16px;
}
.hint {
  color: var(--spider-text-secondary);
  font-size: 12px;
}
.actions {
  margin-left: auto;
}
.tip {
  color: var(--spider-text-secondary);
  font-size: 12px;
  margin-top: 8px;
}
</style>
