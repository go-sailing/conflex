<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon><TrendCharts /></el-icon>
        <span>Conflex</span>
      </div>
      <el-menu :default-active="$route.path" router background-color="#1f2d3d"
               text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/dashboard"><el-icon><DataLine /></el-icon><span>总览</span></el-menu-item>
        <el-sub-menu index="data">
          <template #title><el-icon><Coin /></el-icon><span>行情数据</span></template>
          <el-menu-item index="/data/sources">数据源管理</el-menu-item>
          <el-menu-item index="/data/jobs">更新任务</el-menu-item>
          <el-menu-item index="/data/cache">缓存浏览</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="factors">
          <template #title><el-icon><Histogram /></el-icon><span>因子研究</span></template>
          <el-menu-item index="/factors/library">因子库</el-menu-item>
          <el-menu-item index="/factors/analysis">因子分析</el-menu-item>
          <el-menu-item index="/factors/scores">选股榜单</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/strategies"><el-icon><Setting /></el-icon><span>策略管理</span></el-menu-item>
        <el-menu-item index="/paper/accounts"><el-icon><Wallet /></el-icon><span>模拟交易</span></el-menu-item>
        <el-sub-menu index="backtest">
          <template #title><el-icon><VideoPlay /></el-icon><span>回测</span></template>
          <el-menu-item index="/backtests/new">新建回测</el-menu-item>
          <el-menu-item index="/backtests">回测列表</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="system">
          <template #title><el-icon><Tools /></el-icon><span>系统设置</span></template>
          <el-menu-item index="/system/jobs">任务管理</el-menu-item>
          <el-menu-item index="/system/logs">操作日志</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="title">{{ $route.meta.title || '' }}</div>
        <div class="user">
          <el-icon><UserFilled /></el-icon>
          <span>{{ user.username || 'admin' }}</span>
          <el-button link type="primary" @click="logout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

function logout() {
  user.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100%;
}
.aside {
  background: #1f2d3d;
  overflow-y: auto;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
}
.aside :deep(.el-menu) {
  border-right: none;
}
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #ebeef5;
}
.title {
  font-size: 16px;
  font-weight: 600;
}
.user {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
}
.main {
  background: #f5f7fa;
  padding: 18px;
}
</style>
