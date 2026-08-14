<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import api from '../api'

interface CookieStatus {
  configured: boolean
  count: number
  masked: Record<string, string>
  expiry_hint: string | null
}

const status = ref<CookieStatus | null>(null)
const cookieText = ref('')
const saving = ref(false)
const loading = ref(true)

async function loadStatus() {
  loading.value = true
  try {
    const res = await api.get<CookieStatus>('/config/cookie')
    status.value = res.data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function saveCookie() {
  if (!cookieText.value.trim()) {
    ElMessage.warning('请先粘贴 Cookie')
    return
  }
  saving.value = true
  try {
    const res = await api.post('/config/cookie', { cookie: cookieText.value.trim() })
    cookieText.value = ''
    const msg = `已保存 ${res.data.updated} 项 Cookie`
    ElMessage.success(res.data.expiry_hint ? `${msg}，预计 ${res.data.expiry_hint} 过期` : msg)
    await loadStatus()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="settings">
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="settings-header">
          <span>抖音 Cookie 设置</span>
          <el-button size="small" :loading="loading" @click="loadStatus">刷新状态</el-button>
        </div>
      </template>

      <el-descriptions v-if="status" :column="2" border size="small">
        <el-descriptions-item label="是否已配置">
          {{ status.configured ? '已配置' : '未配置' }}
        </el-descriptions-item>
        <el-descriptions-item label="Cookie 项数">{{ status.count }}</el-descriptions-item>
        <el-descriptions-item label="sessionid">
          {{ status.masked.sessionid || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="预计过期">
          {{ status.expiry_hint || '未知' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        type="info"
        :closable="false"
        title="爬虫与「作者收集」使用该 Cookie；约 2 个月过期，过期后抓取只拿到兜底数据，需重新复制。Cookie 仅保存在服务器 local_config.py（600 权限，不提交）。"
        style="margin-top: 12px"
      />

      <el-input
        v-model="cookieText"
        type="textarea"
        :rows="8"
        placeholder="粘贴抖音网页版完整 Cookie（k=v; k2=v2 ...）&#10;获取方法：F12 → Network → 刷新 douyin.com → 点任意请求 → Headers → Cookie 一栏整串复制"
        style="margin-top: 12px"
      />
      <div class="save-row">
        <el-button type="primary" :loading="saving" :disabled="!cookieText.trim()" @click="saveCookie">
          保存并立即生效
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.settings-card {
  background: var(--spider-surface);
  border: 1px solid var(--spider-border);
  border-radius: var(--radius-md);
}
.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.save-row {
  margin-top: 12px;
}
</style>
