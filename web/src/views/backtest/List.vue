<template>
  <el-card header="回测列表">
    <div class="toolbar">
      <el-button type="primary" @click="$router.push('/backtests/new')">新建回测</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="runs" size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column label="区间" min-width="200">
        <template #default="{ row }">{{ row.start_date }} ~ {{ row.end_date }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'succeeded' ? 'success' : 'warning'" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="总收益" width="110">
        <template #default="{ row }">
          <span v-if="row.metrics" :style="{ color: pctColor(row.metrics.total_return) }">
            {{ pct(row.metrics.total_return) }}
          </span>
          -
        </template>
      </el-table-column>
      <el-table-column label="夏普" width="90">
        <template #default="{ row }">{{ row.metrics?.sharpe?.toFixed(2) ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="最大回撤" width="110">
        <template #default="{ row }">{{ row.metrics ? pct(-row.metrics.max_drawdown) : '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" size="small"
                     @click="$router.push(`/backtests/${row.id}`)">报告</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { backtestApi } from '@/api'

const runs = ref<any[]>([])
const loading = ref(false)
function pct(v: number) {
  return (v * 100).toFixed(2) + '%'
}
function pctColor(v: number) {
  return v >= 0 ? '#ec0000' : '#00a854'
}
async function load() {
  loading.value = true
  try {
    runs.value = await backtestApi.list()
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
