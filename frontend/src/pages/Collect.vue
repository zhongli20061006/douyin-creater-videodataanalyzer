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

const activeTab = ref('paste')

// ---------- 标签一：粘贴 / 导入（正式入口） ----------
const rawInput = ref('')
const parsed = ref<{ valid: string[]; duplicates: number; invalid: number } | null>(null)
const pushing = ref(false)
const queueLength = ref<number | null>(null)

function parseIds() {
  const all = rawInput.value
    .split(/[\n,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const seen = new Set<string>()
  const valid: string[] = []
  let invalid = 0
  for (const id of all) {
    if (/^\d{15,20}$/.test(id)) {
      if (!seen.has(id)) {
        seen.add(id)
        valid.push(id)
      }
    } else {
      invalid++
    }
  }
  parsed.value = {
    valid,
    duplicates: all.length - valid.length - invalid,
    invalid,
  }
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    rawInput.value = String(reader.result || '')
    parseIds()
  }
  reader.readAsText(file)
  input.value = ''
}

async function pushIds() {
  if (!parsed.value || parsed.value.valid.length === 0) {
    ElMessage.warning('没有有效的视频 ID')
    return
  }
  pushing.value = true
  try {
    const res = await api.post('/crawl', { video_ids: parsed.value.valid, task_type: 'video' })
    queueLength.value = res.data.queue_length
    ElMessage.success(`已加入 ${res.data.pushed} 条，当前队列 ${res.data.queue_length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加入队列失败')
  } finally {
    pushing.value = false
  }
}

// ---------- 标签二：作者主页收集（受平台限制） ----------
const url = ref('')
const loading = ref(false)
const videos = ref<PreviewVideo[]>([])
const selected = ref<PreviewVideo[]>([])
const collectQueueLength = ref<number | null>(null)
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
    collectQueueLength.value = null
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
    collectQueueLength.value = res.data.queue_length
    ElMessage.success(`已加入 ${res.data.pushed} 条，当前队列 ${res.data.queue_length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加入队列失败')
  } finally {
    pushing.value = false
  }
}

// ---------- 标签三：video_ids.txt 直接编辑 ----------
const idsText = ref('')
const idsCount = ref(0)
const idsLoading = ref(false)
const idsSaving = ref(false)
const idsImporting = ref(false)

async function loadIdsFile() {
  idsLoading.value = true
  try {
    const res = await api.get<{ total: number; video_ids: string[] }>('/extension/ids')
    idsText.value = (res.data.video_ids ?? []).join('\n')
    idsCount.value = res.data.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    idsLoading.value = false
  }
}

function parseIdsText() {
  const seen = new Set<string>()
  const valid: string[] = []
  let invalid = 0
  for (const raw of idsText.value.split(/\r?\n/)) {
    const id = raw.trim()
    if (!id) continue
    if (/^\d{15,20}$/.test(id) && !seen.has(id)) {
      seen.add(id)
      valid.push(id)
    } else {
      invalid++
    }
  }
  return { valid, invalid }
}

async function saveIdsFile() {
  const { valid, invalid } = parseIdsText()
  if (!valid.length) {
    ElMessage.warning('没有合法的视频 ID')
    return
  }
  idsSaving.value = true
  try {
    const res = await api.put('/extension/ids', { video_ids: valid, author_id: '' })
    idsText.value = valid.join('\n')
    idsCount.value = res.data.total
    ElMessage.success(
      `已保存 ${res.data.total} 条` + (invalid ? `，忽略非法行 ${invalid} 条` : ''),
    )
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    idsSaving.value = false
  }
}

async function importIdsFile() {
  const { valid } = parseIdsText()
  if (!valid.length) {
    ElMessage.warning('没有可导入的 ID')
    return
  }
  idsImporting.value = true
  try {
    const res = await api.post('/crawl', { video_ids: valid, task_type: 'video' })
    ElMessage.success(`已导入 ${res.data.pushed} 条，当前队列 ${res.data.queue_length} 条`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '导入失败')
  } finally {
    idsImporting.value = false
  }
}

async function copyIdsFile() {
  try {
    await navigator.clipboard.writeText(idsText.value)
    ElMessage.success('已复制全部 ID')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}
</script>

<template>
  <div class="collect">
    <el-tabs v-model="activeTab">
      <!-- 正式入口：粘贴 / 导入 -->
      <el-tab-pane label="粘贴 / 导入视频 ID" name="paste">
        <el-card shadow="never" class="collect-card">
          <el-input
            v-model="rawInput"
            type="textarea"
            :rows="8"
            placeholder="每行一个视频 ID，或用逗号/空格分隔，例如：&#10;7234567890123456789&#10;7234567890123456790"
            @input="parseIds"
          />
          <div class="paste-actions">
            <input id="id-file" type="file" accept=".txt" hidden @change="onFileChange" />
            <label for="id-file" class="el-button">从文件导入</label>
            <el-button @click="rawInput = ''; parsed = null">清空</el-button>
          </div>
          <el-alert
            v-if="parsed"
            :type="parsed.valid.length ? 'success' : 'warning'"
            :title="`有效 ${parsed.valid.length} 条，去重 ${parsed.duplicates} 条，无效 ${parsed.invalid} 条`"
            :closable="false"
            style="margin-top: 12px"
          />
          <el-button
            type="primary"
            :loading="pushing"
            :disabled="!parsed || parsed.valid.length === 0"
            style="margin-top: 12px"
            @click="pushIds"
          >
            加入队列（{{ parsed?.valid.length ?? 0 }} 条）
          </el-button>
          <el-alert
            v-if="queueLength !== null"
            type="success"
            :title="'当前队列长度: ' + queueLength"
            :closable="false"
            style="margin-top: 12px"
          />
        </el-card>
      </el-tab-pane>

      <!-- 受限功能：作者主页收集 -->
      <el-tab-pane label="作者主页收集（受限）" name="author">
        <el-alert
          type="warning"
          title="抖音对作者作品列表接口有平台风控限制，自动收集可能失败；建议使用「粘贴 / 导入」方式"
          :closable="false"
          style="margin-bottom: 12px"
        />
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
            v-if="collectQueueLength !== null"
            type="success"
            :title="'当前队列长度: ' + collectQueueLength"
            :closable="false"
            style="margin-top: 12px"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="video_ids.txt" name="idsfile">
        <el-card shadow="never" class="collect-card">
          <div class="paste-actions">
            <span class="ids-count">共 {{ idsCount }} 条</span>
            <el-button size="small" :loading="idsLoading" @click="loadIdsFile">刷新</el-button>
            <el-button size="small" type="primary" :loading="idsSaving" :disabled="!idsText.trim()" @click="saveIdsFile">
              保存到文件
            </el-button>
            <el-button size="small" type="success" :loading="idsImporting" :disabled="!idsCount" @click="importIdsFile">
              导入爬虫队列
            </el-button>
            <el-button size="small" :disabled="!idsText" @click="copyIdsFile">复制全部</el-button>
          </div>
          <el-input
            v-model="idsText"
            type="textarea"
            :rows="16"
            placeholder="每行一个视频 ID，可编辑后「保存到文件」覆盖写入 video_ids.txt"
            style="margin-top: 12px"
          />
          <el-alert
            type="info"
            :closable="false"
            title="插件采集会自动去重追加 ID 到该文件；编辑保存会覆盖整个文件；「导入爬虫队列」把全部 ID 送进 Redis 队列供爬虫消费。"
            style="margin-top: 12px"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>
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
.paste-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}
.collect-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
