<template>
  <el-card header="缓存浏览">
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索代码 / 公司名称" clearable style="width: 240px"
                @clear="loadPage(1)" @keyup.enter="loadPage(1)" />
      <span style="color: #909399; font-size: 13px">
        共 {{ total }} 条 · 缓存占用 {{ storageMB }} MB · 双击行查看K线
      </span>
      <el-button @click="loadPage(page)">刷新</el-button>
    </div>
    <el-table :data="rows" size="small" v-loading="loading"
              highlight-current-row @row-dblclick="openDetail" class="cache-table">
      <el-table-column prop="symbol" label="代码" width="110" />
      <el-table-column label="公司名称" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" underline="never" @click="openDetail(row)">
            {{ row.name || '—' }}
          </el-link>
          <el-tag v-if="row.board && row.board !== 'main'" size="small" type="info"
                  effect="plain" style="margin-left: 6px">
            {{ boardLabel(row.board) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最新价" width="90" align="right">
        <template #default="{ row }">
          {{ row.last_close != null ? Number(row.last_close).toFixed(2) : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="涨跌幅" width="90" align="right">
        <template #default="{ row }">
          <span v-if="row.change_pct != null" :style="{ color: pctColor(row.change_pct) }">
            {{ row.change_pct > 0 ? '+' : '' }}{{ row.change_pct.toFixed(2) }}%
          </span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_date" label="最新交易日" width="110">
        <template #default="{ row }">{{ row.last_date || '—' }}</template>
      </el-table-column>
      <el-table-column prop="start_date" label="缓存起始" width="110" />
      <el-table-column prop="end_date" label="缓存截止" width="110" />
      <el-table-column label="封闭" width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_final ? 'success' : 'warning'" size="small">
            {{ row.is_final ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="数据源" width="90">
        <template #default="{ row }">{{ row.source || '—' }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="170" />
      <el-table-column label="操作" width="90" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">K线</el-button>
        </template>
      </el-table-column>
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
import { useRouter } from 'vue-router'
import { dataApi } from '@/api'

const router = useRouter()
const rows = ref<any[]>([])
const total = ref(0)
const storageBytes = ref(0)
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const keyword = ref('')

const storageMB = computed(() => ((storageBytes.value || 0) / 1024 / 1024).toFixed(1))

const BOARD_NAMES: Record<string, string> = {
  star: '科创板', chinext: '创业板', bjt: '北交所', main: '主板',
}
function boardLabel(b: string) {
  return BOARD_NAMES[b] || b
}

function pctColor(v: number) {
  if (v > 0) return '#f56c6c'
  if (v < 0) return '#67c23a'
  return '#909399'
}

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

function openDetail(row: any) {
  router.push({
    path: `/data/cache/${encodeURIComponent(row.symbol)}`,
    query: row.name ? { name: row.name } : {},
  })
}

onMounted(() => loadPage(1))
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.cache-table :deep(.el-table__row) {
  cursor: pointer;
}
</style>
