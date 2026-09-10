<template>
  <el-card header="数据源管理">
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="sources" size="small" v-loading="loading">
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
      <el-table-column prop="priority" label="优先级" width="80" />
      <el-table-column prop="qps" label="QPS" width="80" />
      <el-table-column prop="daily_quota" label="每日配额" width="90" />
      <el-table-column prop="used_today" label="今日已用" width="90" />
      <el-table-column label="调用成功/总数" width="130">
        <template #default="{ row }">{{ row.ok_calls }} / {{ row.total_calls }}</template>
      </el-table-column>
      <el-table-column prop="avg_latency_ms" label="平均延迟(ms)" width="110" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="testSource(row.name)"
                     :loading="testing === row.name">
            测试
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { dataApi } from '@/api'

const sources = ref<any[]>([])
const loading = ref(false)
const testing = ref('')

async function load() {
  loading.value = true
  try {
    sources.value = await dataApi.sources()
  } finally {
    loading.value = false
  }
}

async function testSource(name: string) {
  testing.value = name
  try {
    const res: any = await dataApi.testSource(name)
    if (res.ok) {
      ElMessage.success(`${name} 连接正常 (${res.latency_ms}ms)`)
    } else {
      ElMessage.error(`${name} 连接失败`)
    }
  } catch {
    ElMessage.error(`${name} 测试出错`)
  } finally {
    testing.value = ''
  }
}

onMounted(load)
</script>
