<script setup lang="ts">
import { computed } from 'vue'

import api from '../api'
import StatCard from '../components/StatCard.vue'
import PieChart from '../components/PieChart.vue'
import { useApi } from '../composables/useApi'

interface Stats {
  total_videos: number
  total_authors: number
  queue_length: number
  latest_crawl: string | null
}

const { data, loading, error, run } = useApi<Stats>(() =>
  api.get('/stats').then((r) => r.data),
)

interface AuthorDist {
  name: string
  value: number
}

const authors = useApi<{ authors: AuthorDist[] }>(() =>
  api.get('/stats/authors').then((r) => r.data),
)

interface QualityReport {
  summary: {
    issue_counts: Record<string, number>
  }
}

const ISSUE_LABELS: Record<string, string> = {
  empty: '疑似无效',
  placeholder: '占位页',
  stale: '陈旧未更新',
  missing_author: '作者缺失',
}

const quality = useApi<QualityReport>(() => api.get('/quality/report').then((r) => r.data))

const authorPieData = computed(() => authors.data.value?.authors ?? [])
const qualityPieData = computed(() => {
  const counts = quality.data.value?.summary.issue_counts ?? {}
  return Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: ISSUE_LABELS[k] || k, value: v }))
})

function fmtTime(t: string | null) {
  if (!t) return '--'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="dashboard">
    <el-alert v-if="error" type="error" :title="'加载失败: ' + error" :closable="false" />
    <el-row :gutter="16">
      <el-col :span="6">
        <StatCard title="视频总数" :value="data?.total_videos ?? '--'" status="info" />
      </el-col>
      <el-col :span="6">
        <StatCard title="作者数" :value="data?.total_authors ?? '--'" status="info" />
      </el-col>
      <el-col :span="6">
        <StatCard title="队列长度" :value="data?.queue_length ?? '--'" status="success" />
      </el-col>
      <el-col :span="6">
        <StatCard title="最近爬取" :value="fmtTime(data?.latest_crawl ?? null)" status="info" />
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <PieChart title="作者视频分布" :data="authorPieData" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="chart-card">
          <PieChart title="数据质量问题分布" :data="qualityPieData" />
        </el-card>
      </el-col>
    </el-row>
    <el-button v-if="loading" loading style="margin-top: 16px">加载中</el-button>
    <el-button v-else style="margin-top: 16px" @click="run">刷新</el-button>
  </div>
</template>

<style scoped>
.chart-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
</style>
