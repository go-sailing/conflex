<template>
  <el-card header="因子库">
    <el-table :data="factors" size="small" v-loading="loading">
      <el-table-column prop="name" label="因子名" width="200" />
      <el-table-column prop="category" label="类别" width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="依赖字段" width="180">
        <template #default="{ row }">{{ (row.deps || []).join(', ') }}</template>
      </el-table-column>
      <el-table-column prop="description" label="说明" />
      <el-table-column label="默认参数" width="180">
        <template #default="{ row }">{{ JSON.stringify(row.params) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" size="small"
                     @click="$router.push({ name: 'factor-analysis', query: { factor: row.name } })">
            IC 分析
          </el-button>
          <el-button link type="primary" size="small"
                     @click="$router.push({ name: 'factor-scores', query: { factors: row.name } })">
            加入选股
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { factorApi } from '@/api'

const factors = ref<any[]>([])
const loading = ref(false)
onMounted(async () => {
  loading.value = true
  try {
    factors.value = await factorApi.list()
  } finally {
    loading.value = false
  }
})
</script>
