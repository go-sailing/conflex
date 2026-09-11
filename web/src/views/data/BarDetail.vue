<template>
  <el-card v-loading="loading">
    <template #header>
      <div class="header">
        <el-button :icon="ArrowLeft" link @click="router.back()">返回</el-button>
        <span class="title">{{ info.name || symbol }}</span>
        <span class="symbol">{{ symbol }}</span>
        <el-tag v-if="info.board" size="small" type="info" effect="plain">
          {{ boardLabel(info.board) }}
        </el-tag>
        <el-tag v-if="info.is_st" size="small" type="danger">ST</el-tag>
        <span v-if="last.close != null" class="last-price" :style="{ color: pctColor(lastPct) }">
          {{ Number(last.close).toFixed(2) }}
          <span class="last-pct">
            {{ lastPct > 0 ? '+' : '' }}{{ lastPct.toFixed(2) }}%
          </span>
        </span>
      </div>
    </template>

    <div class="toolbar">
      <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
                      start-placeholder="开始日期" end-placeholder="结束日期"
                      value-format="YYYY-MM-DD" size="default"
                      :disabled-date="disabledDate" :shortcuts="shortcuts" />
      <el-select v-model="adjust" style="width: 120px">
        <el-option label="前复权" value="qfq" />
        <el-option label="不复权" value="none" />
        <el-option label="后复权" value="hfq" />
      </el-select>
      <el-button type="primary" @click="loadBars">查询</el-button>
    </div>

    <div class="stat-row">
      <div class="stat"><label>区间涨幅</label>
        <b :style="{ color: pctColor(stats.rangePct) }">{{ fmtPct(stats.rangePct) }}</b></div>
      <div class="stat"><label>区间最高</label><b>{{ fmtNum(stats.high) }}</b></div>
      <div class="stat"><label>区间最低</label><b>{{ fmtNum(stats.low) }}</b></div>
      <div class="stat"><label>区间成交额</label><b>{{ fmtAmount(stats.amount) }}</b></div>
      <div class="stat"><label>日均成交额</label><b>{{ fmtAmount(stats.avgAmount) }}</b></div>
      <div class="stat"><label>交易日数</label><b>{{ bars.length }}</b></div>
    </div>

    <el-table :data="pagedRows" size="small" stripe border v-loading="loading">
      <el-table-column prop="trade_date" label="日期" width="110" sortable :default-sort="{ order: 'descending' }" />
      <el-table-column label="开盘" width="90" align="right">
        <template #default="{ row }">{{ fmtNum(row.open) }}</template>
      </el-table-column>
      <el-table-column label="最高" width="90" align="right">
        <template #default="{ row }">{{ fmtNum(row.high) }}</template>
      </el-table-column>
      <el-table-column label="最低" width="90" align="right">
        <template #default="{ row }">{{ fmtNum(row.low) }}</template>
      </el-table-column>
      <el-table-column label="收盘" width="90" align="right">
        <template #default="{ row }">{{ fmtNum(row.close) }}</template>
      </el-table-column>
      <el-table-column label="涨跌幅" width="100" align="right">
        <template #default="{ row }">
          <span :style="{ color: pctColor(row.change_pct) }">{{ fmtPct(row.change_pct) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成交量(手)" width="130" align="right">
        <template #default="{ row }">{{ fmtInt(row.volume) }}</template>
      </el-table-column>
      <el-table-column label="成交额(元)" width="160" align="right">
        <template #default="{ row }">{{ fmtInt(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="换手率%" width="100" align="right">
        <template #default="{ row }">{{ row.turnover != null ? Number(row.turnover).toFixed(2) : '—' }}</template>
      </el-table-column>
    </el-table>

    <div v-if="!loading && !bars.length" style="padding: 40px; text-align: center; color: #909399">
      该区间暂无 K 线数据，可在「因子分析」中选择该股票所在股票池触发自动拉取
    </div>

    <div class="pagination-bar">
      <el-pagination layout="total, sizes, prev, pager, next, jumper"
                     :total="bars.length"
                     :page-sizes="[20, 50, 100, 200]"
                     :page-size="tableSize"
                     :current-page="tablePage"
                     @current-change="(p: number) => (tablePage = p)"
                     @size-change="handleSizeChange" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { dataApi } from '@/api'

const route = useRoute()
const router = useRouter()
const symbol = decodeURIComponent(String(route.params.symbol || ''))

const info = ref<any>({})
const bars = ref<any[]>([])        // 后端按日期升序返回
const loading = ref(false)
const dateRange = ref<[string, string] | null>(null)
const adjust = ref('qfq')
const tablePage = ref(1)
const tableSize = ref(50)

const BOARD_NAMES: Record<string, string> = {
  star: '科创板', chinext: '创业板', bjt: '北交所', main: '主板',
}
function boardLabel(b: string) { return BOARD_NAMES[b] || b }
function pctColor(v: number | null | undefined) {
  if (v == null) return '#909399'
  if (v > 0) return '#f56c6c'
  if (v < 0) return '#67c23a'
  return '#909399'
}
function fmtNum(v: any) { return v == null ? '—' : Number(v).toFixed(2) }
function fmtPct(v: any) {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}
function fmtInt(v: any) { return v == null ? '—' : Math.round(Number(v)).toLocaleString() }
function fmtAmount(v: number | null) {
  if (v == null) return '—'
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)} 万`
  return v.toFixed(0)
}

const shortcuts = [
  { text: '近3个月', value: () => rangeOf(90) },
  { text: '近半年', value: () => rangeOf(180) },
  { text: '近1年', value: () => rangeOf(365) },
  { text: '近3年', value: () => rangeOf(365 * 3) },
]
function rangeOf(days: number): [Date, Date] {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - days)
  return [start, end]
}
function disabledDate(d: Date) {
  if (info.value.cache_start && d < new Date(info.value.cache_start)) return true
  if (info.value.cache_end && d > new Date(info.value.cache_end + 'T23:59:59')) return true
  return false
}
function fmtDate(d: Date) {
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}
function defaultRange(cacheStart: string, cacheEnd: string): [string, string] {
  const end = new Date(cacheEnd + 'T00:00:00')
  const start = new Date(end)
  start.setFullYear(start.getFullYear() - 1)
  const minStart = new Date(cacheStart + 'T00:00:00')
  if (start < minStart) start.setTime(minStart.getTime())
  return [fmtDate(start), fmtDate(end)]
}

// ---- 统计 ----
const last = computed(() => bars.value[bars.value.length - 1] || {})
const lastPct = computed(() => last.value.change_pct ?? null)
const stats = computed(() => {
  const arr = bars.value
  if (!arr.length) return { rangePct: null, high: null, low: null, amount: null, avgAmount: null }
  const firstClose = Number(arr[0].close)
  const endClose = Number(arr[arr.length - 1].close)
  const amount = arr.reduce((s, r) => s + (Number(r.amount) || 0), 0)
  return {
    rangePct: firstClose ? (endClose / firstClose - 1) * 100 : null,
    high: Math.max(...arr.map((r) => Number(r.high))),
    low: Math.min(...arr.map((r) => Number(r.low))),
    amount,
    avgAmount: amount / arr.length,
  }
})

// ---- 明细表：降序（新→旧）+ 分页 ----
const pagedRows = computed(() => {
  const desc = [...bars.value].reverse()
  const start = (tablePage.value - 1) * tableSize.value
  return desc.slice(start, start + tableSize.value)
})
function handleSizeChange(s: number) {
  tableSize.value = s
  tablePage.value = 1
}
// 数据刷新后自动回到第 1 页
watch(() => bars.value.length, () => { tablePage.value = 1 })

async function loadInfo() {
  try {
    const res: any = await dataApi.instrument(symbol)
    info.value = res
    if (res.cache_start && res.cache_end) {
      dateRange.value = defaultRange(res.cache_start, res.cache_end)
    } else {
      dateRange.value = rangeOf(365).map((d) => fmtDate(d)) as [string, string]
    }
  } catch {
    dateRange.value = rangeOf(365).map((d) => fmtDate(d)) as [string, string]
  }
}

async function loadBars() {
  loading.value = true
  tablePage.value = 1
  try {
    const range = dateRange.value || rangeOf(365).map((d) => fmtDate(d))
    const [start, end] = range
    const res: any = await dataApi.bars({ symbol, start, end, adjust: adjust.value })
    const list: any[] = res || []
    // 后端按日期升序；补算每日涨跌幅（pre_close 缺失时用前一行收盘兜底）
    list.forEach((r, i) => {
      const base = r.pre_close != null ? +r.pre_close : (i > 0 ? +list[i - 1].close : null)
      r.change_pct = base ? (+r.close / base - 1) * 100 : null
    })
    bars.value = list
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if ((route.query.name as string)) info.value = { name: route.query.name }
  await loadInfo()
  await loadBars()
})
</script>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.title {
  font-size: 16px;
  font-weight: 600;
}
.symbol { color: #909399; font-size: 13px; }
.last-price { margin-left: auto; font-size: 20px; font-weight: 700; }
.last-pct { font-size: 14px; margin-left: 8px; }
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.stat-row {
  display: flex;
  gap: 28px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: #f7f9fc;
  border-radius: 6px;
  flex-wrap: wrap;
}
.stat label {
  display: block;
  color: #909399;
  font-size: 12px;
  margin-bottom: 2px;
}
.stat b { font-size: 16px; }
.pagination-bar {
  display: flex;
  justify-content: center;
  padding: 16px 0 4px;
}
</style>
