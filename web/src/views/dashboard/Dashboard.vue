<template>
  <div v-loading="loading">
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card class="page-card">
          <div class="metric-value">{{ card.value }}</div>
          <div class="label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card class="page-card" header="数据源健康">
          <el-table :data="data.sources" size="small">
            <el-table-column prop="name" label="数据源" width="120" />
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="熔断状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.state === 'closed' ? 'success' : 'danger'" size="small">
                  {{ row.state === 'closed' ? '正常' : row.state }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="调用成功/总数">
              <template #default="{ row }">{{ row.ok_calls }} / {{ row.total_calls }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="page-card" header="模拟账户">
          <el-table :data="data.accounts" size="small">
            <el-table-column prop="name" label="账户" />
            <el-table-column label="总资产">
              <template #default="{ row }">{{ fmt(row.total_equity) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!data.accounts?.length" description="暂无模拟账户" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
    <el-card header="最近任务">
      <el-table :data="data.recent_jobs" size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="kind" label="类型" width="160" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            <el-progress :percentage="Math.round((row.progress || 0) * 100)" :stroke-width="10" />
          </template>
        </el-table-column>
        <el-table-column prop="stage" label="阶段" min-width="140" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { systemApi } from '@/api'

const loading = ref(false)
const data = ref<any>({ sources: [], accounts: [], recent_jobs: [] })

const cards = computed(() => [
  { label: '本地股票数', value: data.value.symbol_count ?? 0 },
  { label: '最新交易日', value: data.value.latest_trade_date ?? '-' },
  { label: '缓存占用', value: `${((data.value.storage_bytes || 0) / 1024 / 1024).toFixed(1)} MB` },
  { label: '模拟账户数', value: data.value.accounts?.length ?? 0 },
])

function fmt(v: number) {
  return (v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function statusType(s: string) {
  return { succeeded: 'success', failed: 'danger', running: 'primary', queued: 'info' }[s] || 'info'
}

onMounted(async () => {
  loading.value = true
  try {
    data.value = await systemApi.dashboard()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.label {
  color: #909399;
  font-size: 13px;
  margin-top: 6px;
}
</style>
