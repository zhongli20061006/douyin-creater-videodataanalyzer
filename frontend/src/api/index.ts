import axios, { type InternalAxiosRequestConfig } from 'axios'

/** 统一的 API 客户端：开发时由 Vite 代理 /api 到后端 8001，生产由同源提供 */
const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

/**
 * 公网只读鉴权：所有请求附带 X-API-Token。
 * 令牌由用户在布局头部输入并存入 localStorage（键 apiToken，与扩展端 options 页共用）。
 * 令牌为空时不附加任何头，避免污染无鉴权请求。
 */
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('apiToken')
  if (token) {
    config.headers.set('X-API-Token', token)
  }
  return config
})

export default api

export interface InsightItem {
  video_id: string
  video_title?: string | null
  publish_time?: string | null
  days_since_publish: number
  maturity_bucket: string
  play_count: number
  engage_rate: number | null
  collect_rate: number | null
  score: number
  percentiles: { play: number | null; engage: number | null; collect: number | null }
  explanation: string
}

export interface InsightData {
  author_id: string
  author_name: string
  sample_size: number
  insufficient_sample: boolean
  top: InsightItem[]
  bottom: InsightItem[]
  generated_at: string
}

export function getAnalyzeInsights(params: {
  author_id: string
  start_date?: string
  end_date?: string
  limit?: number
}) {
  return api.get<InsightData>('/analyze/insights', { params })
}

