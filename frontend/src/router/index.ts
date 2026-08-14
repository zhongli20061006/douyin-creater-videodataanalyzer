import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'

export default createRouter({
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', name: 'dashboard', component: () => import('../pages/Dashboard.vue'), meta: { title: '数据总览' } },
        { path: 'queue', name: 'queue', component: () => import('../pages/Queue.vue'), meta: { title: '爬虫复核' } },
        { path: 'videos', name: 'videos', component: () => import('../pages/Videos.vue'), meta: { title: '视频数据' } },
        { path: 'collect', name: 'collect', component: () => import('../pages/Collect.vue'), meta: { title: '插件 ID 导入与管理' } },
        { path: 'quality', name: 'quality', component: () => import('../pages/Quality.vue'), meta: { title: '数据质量' } },
        { path: 'personal', name: 'personal', component: () => import('../pages/PersonalAnalyzer.vue'), meta: { title: '个人分析' } },
        { path: 'settings', name: 'settings', component: () => import('../pages/Settings.vue'), meta: { title: '设置' } },
      ],
    },
  ],
})
