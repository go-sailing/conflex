<template>
  <div>
    <el-card class="page-card" header="因子有效性分析（IC / 分层收益）">
      <div class="toolbar">
        <el-select v-model="form.universe" placeholder="股票池" style="width: 140px">
          <el-option v-for="u in universes" :key="u.key" :label="u.name" :value="u.key" />
        </el-select>
        <el-select v-model="form.factor" filterable placeholder="选择因子" style="width: 200px">
          <el-option v-for="f in factors" :key="f.name" :label="f.name" :value="f.name" />
        </el-select>
        <el-date-picker v-model="form.start" type="date" value-format="YYYY-MM-DD"
                        placeholder="开始日期" />
        <el-date-picker v-model="form.end" type="date" value-format="YYYY-MM-DD"
                        placeholder="结束日期（默认今天）" />
        <el-input-number v-model="form.horizon" :min="1" :max="60" controls-position="right"
                         placeholder="预测周期" style="width: 130px" />
        <el-input-number v-model="form.groups" :min="3" :max="10" controls-position="right"
                         placeholder="分组数" style="width: 120px" />
        <el-button type="primary" :loading="running" @click="submit">开始分析</el-button>
      </div>
      <div class="tip" v-if="form.universe">
        分析前会自动检查所选股票池在区间内的行情缓存，缺失部分增量拉取后再计算。
        首次分析较大股票池可能需要较长时间，可在下方进度卡片观察拉取进度。
      </div>
      <JobProgress ref="jobRef" />
    </el-card>

    <!-- 结果展示区：来自当前会话的运行结果 或 历史任务的 result_json -->
    <div v-if="result">
      <el-alert v-if="result.warnings?.length"
                type="warning" :closable="false"
                show-icon style="margin-bottom: 12px">
        <template #title>
          <div v-for="(w, i) in result.warnings" :key="i" style="margin: 2px 0">{{ w }}</div>
        </template>
      </el-alert>

      <div class="result-meta">
        股票池 <b>{{ universeLabel(result.universe) }}</b>
        · 成分股 {{ result.requested_count ?? '—' }} 只
        · 有效行情 {{ result.panel_count ?? '—' }} 只
        · 预测 {{ result.horizon }} 日
        · {{ result.groups }} 分组
      </div>

      <el-row :gutter="16">
        <el-col :span="6" v-for="card in cards" :key="card.label">
          <el-card class="page-card">
            <div class="metric-value">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" v-if="hasValidData">
        <el-col :span="14">
          <el-card class="page-card" header="IC 时序">
            <EChart :option="icOption" height="360px" />
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card class="page-card" header="分层平均收益">
            <EChart :option="layerOption" height="360px" />
          </el-card>
        </el-col>
      </el-row>
      <el-row v-else>
        <el-col :span="24">
          <el-card class="page-card">
            <div style="text-align:center;color:#909399;padding:40px">
              因子计算结果为空。
              <div style="margin-top:8px">
                分析前系统会按所选股票池自动增量拉取缺失行情；
                若多次重试仍为空，请到「数据源管理」检查免费数据源状态，
                或缩小股票池、扩大日期区间后再试。
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 历史因子分析任务 -->
    <el-card class="page-card" header="历史因子分析" style="margin-top: 16px">
      <div class="toolbar">
        <el-button @click="loadHistory" :icon="Refresh" circle size="small" />
        <span style="color:#909399;font-size:13px">共 {{ history.length }} 条</span>
      </div>
      <el-table :data="history" size="small" v-loading="historyLoading" max-height="260"
                highlight-current-row @current-change="onSelectJob">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="股票池" width="100">
          <template #default="{ row }">{{ universeLabel(row.params?.universe) }}</template>
        </el-table-column>
        <el-table-column label="因子" min-width="130">
          <template #default="{ row }">{{ row.params?.factor || '—' }}</template>
        </el-table-column>
        <el-table-column label="区间" min-width="220">
          <template #default="{ row }">
            {{ row.params?.start || '?' }} ~ {{ row.params?.end || '?' }}
            <span v-if="row.params?.horizon"> / 预测{{ row.params.horizon }}日</span>
            <span v-if="row.params?.groups"> / {{ row.params.groups }}分组</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary"
                       :disabled="row.status !== 'succeeded' || !row.result"
                       @click="selectJob(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { dataApi, factorApi, jobApi } from '@/api'
import JobProgress from '@/components/JobProgress.vue'
import EChart from '@/components/EChart.vue'

const route = useRoute()
const factors = ref<any[]>([])
const universes = ref<any[]>([])
const jobRef = ref<InstanceType<typeof JobProgress>>()
const running = ref(false)
const result = ref<any>(null)

// 历史因子分析任务
const history = ref<any[]>([])
const historyLoading = ref(false)

// 默认开始日期：一年前
function oneYearAgo(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
}

const form = reactive({
  factor: (route.query.factor as string) || 'price_rev_20',
  universe: 'all',
  start: oneYearAgo(),
  end: '',
  horizon: 5,
  groups: 10,
})

function universeLabel(key?: string) {
  if (!key) return '—'
  const hit = universes.value.find((u) => u.key === key)
  return hit ? hit.name : key
}

function statusType(s: string) {
  return { succeeded: 'success', failed: 'danger', running: 'primary', queued: 'info' }[s] || 'info'
}

const summary = computed(() => result.value?.summary)
const hasValidData = computed(() => {
  if (!result.value) return false
  const s = result.value.summary
  return (s && s.count && s.count > 0) ||
    (result.value.ic_series?.some((r: any) => r.ic != null))
})
const cards = computed(() => {
  const s = summary.value || {}
  const pct = (v: any) => (v == null ? '-' : (v * 100).toFixed(2) + '%')
  return [
    { label: 'IC 均值', value: s.ic_mean == null ? '-' : s.ic_mean.toFixed(4) },
    { label: 'ICIR', value: s.icir == null ? '-' : s.icir.toFixed(3) },
    { label: 'IC 胜率', value: pct(s.win_rate) },
    { label: '有效样本日', value: s.count ?? 0 },
  ]
})

const icOption = computed(() => {
  const rows = result.value?.ic_series || []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: rows.map((r: any) => r.date) },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }],
    series: [
      {
        name: 'IC', type: 'bar', data: rows.map((r: any) => r.ic),
        itemStyle: { color: (p: any) => (p.data >= 0 ? '#ec0000' : '#00a854') },
      },
    ],
  }
})

const layerOption = computed(() => {
  const lm = result.value?.layered_mean || {}
  const keys = Object.keys(lm)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: keys },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
    series: [
      {
        type: 'bar', data: keys.map((k) => Number((lm[k] * 100).toFixed(3))),
        itemStyle: { color: '#409eff' },
      },
    ],
  }
})

async function submit() {
  running.value = true
  try {
    const resp: any = await factorApi.analysis({
      factor: form.factor,
      universe: form.universe,
      start: form.start,
      end: form.end || null,
      horizon: form.horizon,
      groups: form.groups,
    })
    const r = await jobRef.value?.runJob(resp.job_id)
    result.value = r
    // 跑完刷新历史
    await loadHistory()
  } finally {
    running.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const rows: any[] = await jobApi.list(50, 'factor_analysis')
    history.value = rows
  } finally {
    historyLoading.value = false
  }
}

function selectJob(row: any) {
  if (row.result) {
    result.value = row.result
  }
}

function onSelectJob(row: any) {
  if (row?.result) result.value = row.result
}

onMounted(async () => {
  factors.value = await factorApi.list()
  universes.value = await dataApi.universes()
  await loadHistory()
})
</script>

<style scoped>
.label {
  color: #909399;
  font-size: 13px;
  margin-top: 6px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.tip {
  color: #909399;
  font-size: 12px;
  margin-bottom: 10px;
}
.result-meta {
  color: #606266;
  font-size: 13px;
  margin: 4px 0 12px;
}
</style>
