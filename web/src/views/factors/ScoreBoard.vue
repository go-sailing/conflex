<template>
  <el-card header="每日选股榜单">
    <div class="toolbar">
      <el-select v-model="selected" multiple filterable collapse-tags collapse-tags-tooltip
                 placeholder="选择因子（可多选等权合成）" style="min-width: 340px">
        <el-option v-for="f in factors" :key="f.name" :label="f.name" :value="f.name" />
      </el-select>
      <el-date-picker v-model="date" type="date" value-format="YYYY-MM-DD"
                      placeholder="选股日期（默认最新）" />
      <el-input-number v-model="top" :min="1" :max="100" controls-position="right"
                       style="width: 120px" placeholder="Top N" />
      <el-radio-group v-model="weighting">
        <el-radio-button value="equal">等权</el-radio-button>
        <el-radio-button value="ic">IC加权</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :loading="loading" @click="query">生成榜单</el-button>
    </div>

    <el-table :data="board" size="small" v-loading="loading">
      <el-table-column prop="rank" label="排名" width="80" />
      <el-table-column prop="symbol" label="股票代码" width="140" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column label="综合得分">
        <template #default="{ row }">{{ Number(row.score).toFixed(4) }}</template>
      </el-table-column>
      <el-table-column prop="quantile" label="分位" width="90" />
      <el-table-column label="操作" width="170">
        <template #default="{ row }">
          <el-button link type="primary" size="small"
                     @click="$router.push({ name: 'data-cache' })">查看K线</el-button>
          <el-button link type="success" size="small"
                     @click="$router.push({ name: 'paper-accounts', query: { symbol: row.symbol } })">
            模拟买入
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { factorApi } from '@/api'

const route = useRoute()
const factors = ref<any[]>([])
const selected = ref<string[]>(
  route.query.factors ? String(route.query.factors).split(',') : ['price_mom_20'],
)
const date = ref('')
const top = ref(20)
const weighting = ref('equal')
const board = ref<any[]>([])
const loading = ref(false)

async function query() {
  if (!selected.value.length) {
    ElMessage.warning('请至少选择一个因子')
    return
  }
  loading.value = true
  try {
    board.value = await factorApi.scores({
      factors: selected.value.join(','),
      date: date.value || null,
      top: top.value,
      weighting: weighting.value,
    })
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  factors.value = await factorApi.list()
  await query()
})
</script>
