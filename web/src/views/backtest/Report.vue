<template>
  <div v-loading="loading">
    <div v-if="run" class="toolbar">
      <el-button @click="$router.push('/backtests')">返回列表</el-button>
      <el-button type="primary" @click="$router.push('/backtests/new')">再跑一次</el-button>
      <el-tag>{{ run.name }} #{{ run.id }}</el-tag>
      <span class="muted">{{ run.start_date }} ~ {{ run.end_date }}</span>
    </div>

    <el-row v-if="run?.metrics" :gutter="12">
      <el-col :span="4" v-for="card in cards" :key="card.label">
        <el-card class="page-card">
          <div class="metric-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="label">{{ card.label }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="page-card">
          <div class="metric-value">{{ run.metrics.trade_count }}</div>
          <div class="label">成交笔数</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="run" class="page-card" header="净值曲线 vs 基准">
      <EChart :option="equityOption" height="380px" />
    </el-card>
    <el-card v-if="run" class="page-card" header="回撤曲线">
      <EChart :option="drawdownOption" height="240px" />
    </el-card>
    <el-card v-if="run" class="page-card" header="月度收益热力图（%）">
      <div v-if="!monthly.length" class="muted">数据不足</div>
      <table v-else class="heatmap">
        <thead>
          <tr><th>年份</th><th v-for="m in 12" :key="m">{{ m }}月</th><th>全年</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in monthly" :key="row.year">
            <td class="year">{{ row.year }}</td>
            <td v-for="m in 12" :key="m" :style="cellStyle(row.values[m - 1])">
              {{ row.values[m - 1] != null ? row.values[m - 1] : '' }}
            </td>
            <td class="year" :style="cellStyle(row.yearRet)">{{ row.yearRet }}</td>
          </tr>
        </tbody>
      </table>
    </el-card>

    <el-card v-if="run" header="交易明细">
      <el-table :data="run.trades" size="small" height="380">
        <el-table-column prop="trade_date" label="成交日" width="120" />
        <el-table-column prop="symbol" label="股票" width="140" />
        <el-table-column prop="side" label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.side === 'buy' ? 'danger' : 'success'" size="small">
              {{ row.side === 'buy' ? '买入' : '卖出' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="qty" label="数量" width="100" />
        <el-table-column prop="price" label="价格" width="100" />
        <el-table-column label="费用" width="120">
          <template #default="{ row }">{{ (row.fee || 0).toFixed(2) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { backtestApi } from '@/api'
import EChart from '@/components/EChart.vue'

const route = useRoute()
const run = ref<any>(null)
const loading = ref(false)

const cards = computed(() => {
  const m = run.value.metrics
  const pct = (v: number) => (v * 100).toFixed(2) + '%'
  const num = (v: number, d = 2) => (v ?? 0).toFixed(d)
  return [
    { label: '总收益', value: pct(m.total_return), color: m.total_return >= 0 ? '#ec0000' : '#00a854' },
    { label: '年化收益', value: pct(m.annual_return), color: m.annual_return >= 0 ? '#ec0000' : '#00a854' },
    { label: '年化波动', value: pct(m.annual_volatility), color: '#303133' },
    { label: '夏普比率', value: num(m.sharpe), color: '#409eff' },
    { label: '最大回撤', value: pct(-m.max_drawdown), color: '#00a854' },
    { label: '卡玛比率', value: num(m.calmar), color: '#409eff' },
  ]
})

const equityOption = computed(() => {
  const rows = run.value.equity || []
  const dates = rows.map((r: any) => r.trade_date)
  const series: any[] = [
    { name: '策略净值', type: 'line', showSymbol: false, data: rows.map((r: any) => r.equity),
      lineStyle: { width: 2 } },
  ]
  if (rows.some((r: any) => r.benchmark != null)) {
    series.push({ name: '基准', type: 'line', showSymbol: false,
      data: rows.map((r: any) => r.benchmark), lineStyle: { width: 1, type: 'dashed' } })
  }
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 80, right: 30, top: 40, bottom: 50 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series,
  }
})

const drawdownOption = computed(() => {
  const rows = run.value.equity || []
  let peak = -Infinity
  const dd = rows.map((r: any) => {
    peak = Math.max(peak, r.equity)
    return Number(((r.equity / peak - 1) * 100).toFixed(2))
  })
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => v + '%' },
    grid: { left: 80, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: rows.map((r: any) => r.trade_date) },
    yAxis: { type: 'value' },
    dataZoom: [{ type: 'inside' }],
    series: [{ type: 'line', data: dd, showSymbol: false, areaStyle: { color: '#f56c6c55' },
      lineStyle: { color: '#f56c6c' } }],
  }
})

// 月度收益矩阵：由日净值重采样为月末后计算
const monthly = computed(() => {
  const rows = run.value?.equity || []
  if (rows.length < 2) return []
  const map = new Map<string, number>()
  rows.forEach((r: any, i: number) => {
    if (i === 0) return
    const [y, m] = r.trade_date.split('-')
    const key = `${y}-${m}`
    map.set(key, r.equity) // 每月最后一条覆盖
  })
  const byYear = new Map<number, number[]>()
  const monthEnds = [...map.entries()]
  for (let i = 1; i < monthEnds.length; i++) {
    const [key, eq] = monthEnds[i]
    const prevEq = monthEnds[i - 1][1]
    const [y, m] = key.split('-').map(Number)
    const ret = Math.round((eq / prevEq - 1) * 10000) / 100
    if (!byYear.has(y)) byYear.set(y, new Array(12).fill(null))
    byYear.get(y)![m - 1] = ret
  }
  return [...byYear.entries()].map(([year, values]) => {
    const valid = values.filter((v) => v != null)
    const yearRet = valid.length ? Math.round(valid.reduce((a, b) => a + b, 0) * 100) / 100 : null
    return { year, values, yearRet }
  })
})

function cellStyle(v: number | null) {
  if (v == null) return {}
  const alpha = Math.min(Math.abs(v) / 10, 0.5)
  return v >= 0
    ? { background: `rgba(236,0,0,${alpha})`, color: alpha > 0.25 ? '#fff' : '#303133' }
    : { background: `rgba(0,168,84,${alpha})`, color: alpha > 0.25 ? '#fff' : '#303133' }
}

onMounted(async () => {
  loading.value = true
  try {
    run.value = await backtestApi.report(Number(route.params.id))
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
.muted {
  color: #909399;
  font-size: 13px;
}
.heatmap {
  border-collapse: collapse;
  width: 100%;
  text-align: center;
  font-size: 12px;
}
.heatmap th,
.heatmap td {
  border: 1px solid #ebeef5;
  padding: 6px 4px;
}
.heatmap .year {
  font-weight: 600;
  background: #fafafa;
}
</style>
