<script setup lang="ts">
import api from '../api'
import StatCard from '../components/StatCard.vue'
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
    <el-button v-if="loading" loading style="margin-top: 16px">加载中</el-button>
    <el-button v-else style="margin-top: 16px" @click="run">刷新</el-button>
  </div>
</template>
