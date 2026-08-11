<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import api from '../api'
import StatCard from '../components/StatCard.vue'

use([BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

interface AuthorOption {
  author_id: string
  author_name: string
  count: number
}

interface PersonalData {
  author_id: string
  author_name: string
  summary: {
    total_videos: number
    total_likes: number
    total_comments: number
    total_shares: number
    total_plays: number
    latest_sync: string | null
  }
  trend: { month: string; count: number }[]
  top_videos: Array<{
    video_id: string
    video_title?: string | null
    like_count?: number
    comment_count?: number
    share_count?: number
    publish_time?: string | null
    crawl_time?: string | null
  }>
}

const authors = ref<AuthorOption[]>([])
const authorId = ref('')
const loading = ref(false)
const data = ref<PersonalData | null>(null)
const error = ref('')

const interactionData = computed(() => {
  const s = data.value?.summary
  if (!s) return []
  return [
    { name: '点赞', value: s.total_likes },
    { name: '评论', value: s.total_comments },
    { name: '分享', value: s.total_shares },
  ]
})

const trendOption = computed(() => ({
  title: {
    text: '月度发布趋势',
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 16, top: 44, bottom: 28 },
  xAxis: {
    type: 'category',
    data: (data.value?.trend ?? []).map((t) => t.month),
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      name: '视频数',
      type: 'bar',
      barMaxWidth: 28,
      itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
      data: (data.value?.trend ?? []).map((t) => t.count),
    },
  ],
}))

const interactionOption = computed(() => ({
  title: {
    text: '互动总量',
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'axis' },
  grid: { left: 64, right: 16, top: 44, bottom: 28 },
  xAxis: {
    type: 'category',
    data: interactionData.value.map((d) => d.name),
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      name: '总数',
      type: 'bar',
      barMaxWidth: 48,
      itemStyle: { color: '#67c23a', borderRadius: [4, 4, 0, 0] },
      data: interactionData.value.map((d) => d.value),
    },
  ],
}))

async function loadAuthors() {
  try {
    const res = await api.get<{ authors: AuthorOption[] }>('/analyze/authors')
    authors.value = res.data.authors ?? []
    if (authors.value.length) {
      authorId.value = authors.value[0].author_id
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载作者列表失败')
  }
}

async function loadPersonal() {
  if (!authorId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.get<PersonalData>('/analyze/personal', {
      params: { author_id: authorId.value },
    })
    data.value = res.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载分析数据失败'
  } finally {
    loading.value = false
  }
}

watch(authorId, loadPersonal)
onMounted(loadAuthors)

function fmtNum(n?: number) {
  if (!n) return '0'
  if (n >= 100000000) return (n / 100000000).toFixed(1) + '亿'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return String(n)
}

function fmtTime(t?: string | null) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '--'
}
</script>

<template>
  <div class="personal">
    <el-alert v-if="error" type="error" :title="error" :closable="false" style="margin-bottom: 12px" />
    <el-card shadow="never" class="p-card toolbar">
      <span class="label">作者：</span>
      <el-select v-model="authorId" filterable style="width: 280px" :disabled="loading">
        <el-option
          v-for="a in authors"
          :key="a.author_id"
          :label="`${a.author_name || a.author_id}（${a.count} 条）`"
          :value="a.author_id"
        />
      </el-select>
      <el-button :loading="loading" @click="loadPersonal">刷新</el-button>
    </el-card>

    <el-empty
      v-if="!loading && !data && !error"
      description="还没有数据，请先用浏览器插件在自己主页采集"
      style="margin-top: 40px"
    />

    <template v-if="data">
      <el-row :gutter="16">
        <el-col :span="5">
          <StatCard title="视频数" :value="data.summary.total_videos" status="info" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总点赞" :value="fmtNum(data.summary.total_likes)" status="success" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总评论" :value="fmtNum(data.summary.total_comments)" status="warning" />
        </el-col>
        <el-col :span="5">
          <StatCard title="总分享" :value="fmtNum(data.summary.total_shares)" status="info" />
        </el-col>
        <el-col :span="4">
          <StatCard title="最近同步" :value="fmtTime(data.summary.latest_sync)" status="info" />
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="trendOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never" class="p-card">
            <v-chart :option="interactionOption" autoresize style="height: 300px" />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="p-card">
        <template #header>Top 10 视频（按点赞）</template>
        <el-table :data="data.top_videos" size="small" max-height="460">
          <el-table-column prop="video_id" label="视频ID" width="190" />
          <el-table-column prop="video_title" label="标题" show-overflow-tooltip />
          <el-table-column label="点赞" width="100">
            <template #default="{ row }">{{ fmtNum(row.like_count) }}</template>
          </el-table-column>
          <el-table-column label="评论" width="90">
            <template #default="{ row }">{{ fmtNum(row.comment_count) }}</template>
          </el-table-column>
          <el-table-column label="分享" width="90">
            <template #default="{ row }">{{ fmtNum(row.share_count) }}</template>
          </el-table-column>
          <el-table-column label="发布时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.publish_time) }}</template>
          </el-table-column>
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.crawl_time) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.p-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-section);
}
.toolbar :deep(.el-card__body) {
  display: flex;
  gap: 12px;
  align-items: center;
}
.label {
  color: var(--spider-text-secondary);
  font-size: 14px;
}
</style>
