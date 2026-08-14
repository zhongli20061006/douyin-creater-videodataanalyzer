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
