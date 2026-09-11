import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/dashboard/Dashboard.vue'), meta: { title: '总览' } },
      { path: 'data/sources', name: 'data-sources', component: () => import('@/views/data/Sources.vue'), meta: { title: '数据源管理' } },
      { path: 'data/cache', name: 'data-cache', component: () => import('@/views/data/CacheBrowser.vue'), meta: { title: '缓存浏览' } },
      { path: 'data/cache/:symbol', name: 'data-cache-detail', component: () => import('@/views/data/BarDetail.vue'), meta: { title: 'K线详情' } },
      { path: 'factors/library', name: 'factor-library', component: () => import('@/views/factors/Library.vue'), meta: { title: '因子库' } },
      { path: 'factors/analysis', name: 'factor-analysis', component: () => import('@/views/factors/Analysis.vue'), meta: { title: '因子分析' } },
      { path: 'factors/scores', name: 'factor-scores', component: () => import('@/views/factors/ScoreBoard.vue'), meta: { title: '选股榜单' } },
      { path: 'strategies', name: 'strategies', component: () => import('@/views/strategy/List.vue'), meta: { title: '策略管理' } },
      { path: 'paper/accounts', name: 'paper-accounts', component: () => import('@/views/paper/Accounts.vue'), meta: { title: '模拟交易' } },
      { path: 'backtests', name: 'backtests', component: () => import('@/views/backtest/List.vue'), meta: { title: '回测列表' } },
      { path: 'backtests/new', name: 'backtest-new', component: () => import('@/views/backtest/New.vue'), meta: { title: '新建回测' } },
      { path: 'backtests/:id', name: 'backtest-report', component: () => import('@/views/backtest/Report.vue'), meta: { title: '回测报告' } },
      { path: 'system/jobs', name: 'system-jobs', component: () => import('@/views/system/Jobs.vue'), meta: { title: '任务管理' } },
      { path: 'system/logs', name: 'system-logs', component: () => import('@/views/system/Logs.vue'), meta: { title: '操作日志' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('conflex_token')
  if (!to.meta.public && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && token) {
    return { name: 'dashboard' }
  }
})

export default router
