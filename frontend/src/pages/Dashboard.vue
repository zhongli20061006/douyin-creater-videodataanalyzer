<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BarChart } from 'echarts/charts'
import { GridComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import api from '../api'
import StatCard from '../components/StatCard.vue'
import { useApi } from '../composables/useApi'

use([BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

interface Stats {
  total_videos: number
  total_authors: number
  queue_length: number
  latest_crawl: string | null
}

const dateRange = ref<[string, string] | null>(null)

const dateShortcuts = [
  {
    text: '本月',
    value: () => {
      const now = new Date()
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [start, now]
    },
  },
]

const { data, loading, error, run } = useApi<Stats>(() =>
  api.get('/stats', {
    params: {
      start_date: dateRange.value ? dateRange.value[0] : undefined,
      end_date: dateRange.value ? dateRange.value[1] : undefined,
    },
  }).then((r) => r.data),
)

watch(dateRange, () => run())

interface AuthorDist {
  name: string
  value: number
}

const authors = useApi<{ authors: AuthorDist[] }>(() =>
  api.get('/stats/authors').then((r) => r.data),
)

const TOP_AUTHORS = 15
// 水平条形图：升序排列让视频数最多的作者显示在最上方
const authorBarData = computed(() =>
  (authors.data.value?.authors ?? []).slice(0, TOP_AUTHORS).sort((a, b) => a.value - b.value),
)

const authorBarOption = computed(() => ({
  title: {
    text: `作者贡献度（视频数 Top ${TOP_AUTHORS}）`,
    left: 'center',
    textStyle: { color: '#e5e7eb', fontSize: 14 },
  },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 100, right: 56, top: 44, bottom: 24 },
  xAxis: {
    type: 'value',
    axisLabel: { color: '#9ca3af' },
  },
  yAxis: {
    type: 'category',
    data: authorBarData.value.map((d) => d.name),
    axisLabel: { color: '#9ca3af' },
  },
  series: [
    {
      name: '视频数',
      type: 'bar',
      barMaxWidth: 18,
      itemStyle: { color: '#409eff', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: '#9ca3af', formatter: '{c}' },
      data: authorBarData.value.map((d) => d.value),
    },
  ],
}))

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
    <el-card shadow="never" class="chart-card">
      <v-chart :option="authorBarOption" autoresize style="height: 480px" />
    </el-card>
    <el-button v-if="loading" loading style="margin-top: 16px">加载中</el-button>
    <el-button v-else style="margin-top: 16px" @click="run">刷新</el-button>
    <el-date-picker
      v-model="dateRange"
      type="daterange"
      value-format="YYYY-MM-DD"
      range-separator="至"
      start-placeholder="开始日期"
      end-placeholder="结束日期"
      :shortcuts="dateShortcuts"
      style="max-width: 300px; margin-top: 16px"
      clearable
    />
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
