import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'

export default createRouter({
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', name: 'dashboard', component: () => import('../pages/Dashboard.vue'), meta: { title: '看板' } },
        { path: 'queue', name: 'queue', component: () => import('../pages/Queue.vue'), meta: { title: '队列监控' } },
        { path: 'videos', name: 'videos', component: () => import('../pages/Videos.vue'), meta: { title: '视频数据' } },
        { path: 'collect', name: 'collect', component: () => import('../pages/Collect.vue'), meta: { title: '收集任务' } },
        { path: 'quality', name: 'quality', component: () => import('../pages/Quality.vue'), meta: { title: '数据质量' } },
      ],
    },
  ],
})
