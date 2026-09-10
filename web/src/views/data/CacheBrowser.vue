<template>
  <el-card header="缓存浏览">
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索股票代码" clearable style="width: 200px"
                @clear="loadPage(1)" @keyup.enter="loadPage(1)" />
      <span style="color: #909399; font-size: 13px">
        共 {{ total }} 条 · 缓存占用 {{ storageMB }} MB
      </span>
      <el-button @click="loadPage(page)">刷新</el-button>
    </div>
    <el-table :data="rows" size="small" v-loading="loading">
      <el-table-column prop="symbol" label="股票代码" width="120" />
      <el-table-column prop="start_date" label="起始日期" width="120" />
      <el-table-column prop="end_date" label="截止日期" width="120" />
      <el-table-column label="是否完整" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_final ? 'success' : 'warning'" size="small">
            {{ row.is_final ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="数据源" width="100" />
      <el-table-column prop="updated_at" label="更新时间" width="180" />
    </el-table>
    <el-pagination v-if="total > 0" style="margin-top: 12px; justify-content: center"
                   layout="prev, pager, next, sizes, jumper"
                   :total="total" :page-size="size" :current-page="page"
                   :page-sizes="[20, 50, 100, 200]"
                   @current-change="loadPage" @size-change="handleSizeChange" />
    <el-empty v-if="!loading && !rows.length" description="暂无缓存数据" />
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { dataApi } from '@/api'

const rows = ref<any[]>([])
const total = ref(0)
const storageBytes = ref(0)
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const keyword = ref('')

const storageMB = computed(() => ((storageBytes.value || 0) / 1024 / 1024).toFixed(1))

async function loadPage(p: number) {
  page.value = p
  loading.value = true
  try {
    const res: any = await dataApi.coverage({ page: page.value, size: size.value, keyword: keyword.value })
    rows.value = res.rows || []
    total.value = res.total || 0
    storageBytes.value = res.storage_bytes || 0
  } finally {
    loading.value = false
  }
}

function handleSizeChange(s: number) {
  size.value = s
  loadPage(1)
}

onMounted(() => loadPage(1))
</script>
