<template>
  <el-card header="异步任务">
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="jobs" size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="kind" label="类型" width="160" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="180">
        <template #default="{ row }">
          <el-progress :percentage="Math.round((row.progress || 0) * 100)" :stroke-width="10" />
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" min-width="140" />
      <el-table-column prop="error" label="错误" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { jobApi } from '@/api'

const jobs = ref<any[]>([])
const loading = ref(false)
function statusType(s: string) {
  return { succeeded: 'success', failed: 'danger', running: 'primary', queued: 'info' }[s] || 'info'
}
async function load() {
  loading.value = true
  try {
    jobs.value = await jobApi.list(100)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
