<template>
  <el-card header="操作日志">
    <el-table :data="logs" size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column prop="user_id" label="用户" width="80" />
      <el-table-column prop="action" label="操作" width="180" />
      <el-table-column prop="target" label="对象" min-width="180" />
      <el-table-column prop="ip" label="IP" width="140" />
      <el-table-column prop="detail_json" label="详情" min-width="200" show-overflow-tooltip />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { systemApi } from '@/api'

const logs = ref<any[]>([])
const loading = ref(false)
onMounted(async () => {
  loading.value = true
  try {
    logs.value = await systemApi.logs(200)
  } finally {
    loading.value = false
  }
})
</script>
