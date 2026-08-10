<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '../api'

interface IssueRow {
  video_id: string
  video_title?: string | null
  author_name?: string | null
  update_time?: string | null
  issue_types: string[]
}

interface Report {
  summary: {
    total: number
    authors: number
    latest_update?: string | null
    issue_counts: Record<string, number>
  }
  issues: IssueRow[]
}

const MAX_SELECT = 200
const report = ref<Report | null>(null)
const issues = ref<IssueRow[]>([])
const selected = ref<IssueRow[]>([])
const loading = ref(false)
const fixing = ref(false)
const deleting = ref(false)

const LABELS: Record<string, string> = {
  empty: '疑似无效',
  placeholder: '占位页标题',
  stale: '陈旧未更新',
  missing_author: '作者缺失',
}

async function load() {
  loading.value = true
  try {
    const res = await api.get<Report>('/quality/report')
    report.value = res.data
    issues.value = res.data.issues
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载质量报告失败')
  } finally {
    loading.value = false
  }
}

function onSelectionChange(rows: IssueRow[]) {
  selected.value = rows
}

function tags(row: IssueRow) {
  return row.issue_types.map((t) => LABELS[t] || t).join('、')
}

function fmtTime(t?: string | null) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '--'
}

async function fixAll() {
  try {
    await ElMessageBox.confirm('确认执行安全修正（标题去空白/换行）？', '一键修正', { type: 'info' })
  } catch {
    return
  }
  fixing.value = true
  try {
    const res = await api.post('/quality/fix', {})
    ElMessage.success(`已修正 ${res.data.fixed} 条`)
    load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '修正失败')
  } finally {
    fixing.value = false
  }
}

async function deleteSelected() {
  const ids = selected.value.map((r) => r.video_id)
  if (!ids.length) {
    ElMessage.warning('请先勾选要删除的问题数据')
    return
  }
  if (ids.length > MAX_SELECT) {
    ElMessage.warning(`单次最多勾选 ${MAX_SELECT} 条，请分批操作`)
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除 ${ids.length} 条问题数据？此操作不可恢复。`, '确认删除', { type: 'warning' })
  } catch {
    return
  }
  deleting.value = true
  try {
    const res = await api.post('/quality/delete', { video_ids: ids })
    const extra = res.data.rejected.length ? `，拒绝 ${res.data.rejected.length} 条` : ''
    ElMessage.success(`已删除 ${res.data.deleted} 条${extra}`)
    load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deleting.value = false
  }
}

function exportCsv() {
  window.location.href = '/api/quality/export?scope=all'
}

function exportXlsx() {
  window.location.href = '/api/quality/export?scope=all&format=xlsx'
}

onMounted(load)
</script>

<template>
  <div class="quality">
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="never" class="q-card">
          <div class="q-label">视频总数</div>
          <div class="q-value">{{ report?.summary.total ?? '--' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="q-card">
          <div class="q-label">作者数</div>
          <div class="q-value">{{ report?.summary.authors ?? '--' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="q-card">
          <div class="q-label">问题总数</div>
          <div class="q-value" :style="{ color: issues.length ? 'var(--spider-warning)' : 'var(--spider-success)' }">
            {{ issues.length }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="q-card">
          <div class="q-label">最近更新</div>
          <div class="q-value small">{{ fmtTime(report?.summary.latest_update) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="q-card">
      <template #header>
        <div class="q-header">
          <span>问题清单</span>
          <div>
            <el-button :loading="fixing" @click="fixAll">一键修正</el-button>
            <el-button type="danger" :loading="deleting" @click="deleteSelected">删除选中</el-button>
            <el-button @click="exportCsv">导出 CSV</el-button>
            <el-button @click="exportXlsx">导出 Excel</el-button>
            <el-button :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="issues"
        size="small"
        max-height="480"
        v-loading="loading"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="46" :selectable="() => true" />
        <el-table-column prop="video_id" label="视频ID" width="200" />
        <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
        <el-table-column prop="author_name" label="作者" width="140" show-overflow-tooltip />
        <el-table-column label="问题类型" width="140">
          <template #default="{ row }">{{ tags(row) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.update_time) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="issues.length === 0 && !loading" description="暂无问题数据" :image-size="60" />
      <el-alert
        v-if="issues.length"
        type="warning"
        :title="`共 ${issues.length} 条问题（已勾选 ${selected.length} 条，单次上限 ${MAX_SELECT}）`"
        :closable="false"
        style="margin-top: 12px"
      />
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
  flex-wrap: wrap;
  gap: 8px;
}
</style>
