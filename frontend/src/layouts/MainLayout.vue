<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

const route = useRoute()

const menus = [
  { index: '/', label: '数据总览' },
  { index: '/queue', label: '爬虫复核' },
  { index: '/videos', label: '视频数据' },
  { index: '/collect', label: '爬虫任务导入' },
  { index: '/quality', label: '数据质量' },
  { index: '/personal', label: '个人分析' },
]

const apiToken = ref('')

onMounted(() => {
  apiToken.value = localStorage.getItem('apiToken') || ''
})

function saveToken() {
  const trimmed = apiToken.value.trim()
  if (trimmed) {
    localStorage.setItem('apiToken', trimmed)
  } else {
    localStorage.removeItem('apiToken')
  }
  ElMessage.success('已保存')
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="200px" class="layout-aside">
      <div class="brand">抖音创作者数据分析器</div>
      <el-menu :default-active="route.path" router class="layout-menu">
        <el-menu-item v-for="m in menus" :key="m.index" :index="m.index">{{ m.label }}</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="layout-header">
        <span class="page-title">{{ route.meta.title || '看板' }}</span>
        <div class="token-control">
          <el-input
            v-model="apiToken"
            type="password"
            placeholder="访问令牌"
            show-password
            size="small"
            class="token-input"
          />
          <el-button type="primary" size="small" @click="saveToken">保存</el-button>
        </div>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.layout-aside {
  background: var(--spider-surface);
  border-right: 1px solid var(--spider-border);
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-card);
  font-weight: 600;
  font-size: 16px;
}
.layout-menu {
  border-right: none;
  background: transparent;
}
.layout-header {
  background: var(--spider-surface);
  border-bottom: 1px solid var(--spider-border);
  display: flex;
  align-items: center;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
}
.token-control {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-card);
}
.token-input {
  width: 220px;
}
.layout-main {
  padding: var(--space-page);
}
</style>
