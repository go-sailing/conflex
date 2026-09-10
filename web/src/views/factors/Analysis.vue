<template>
  <div>
    <el-card class="page-card" header="因子有效性分析（IC / 分层收益）">
      <div class="toolbar">
        <el-select v-model="form.factor" filterable placeholder="选择因子" style="width: 220px">
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
      <JobProgress ref="jobRef" />
    </el-card>

    <el-row v-if="summary" :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card class="page-card">
          <div class="metric-value">{{ card.value }}</div>
          <div class="label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="result" :gutter="16">
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { factorApi } from '@/api'
import JobProgress from '@/components/JobProgress.vue'
import EChart from '@/components/EChart.vue'

const route = useRoute()
const factors = ref<any[]>([])
const jobRef = ref<InstanceType<typeof JobProgress>>()
const running = ref(false)
const result = ref<any>(null)

const form = reactive({
  factor: (route.query.factor as string) || 'price_rev_20',
  start: '2022-03-01',
  end: '',
  horizon: 5,
  groups: 10,
})

const summary = computed(() => result.value?.summary)
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
      start: form.start,
      end: form.end || null,
      horizon: form.horizon,
      groups: form.groups,
    })
    const r = await jobRef.value?.runJob(resp.job_id)
    result.value = r
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  factors.value = await factorApi.list()
})
</script>

<style scoped>
.label {
  color: #909399;
  font-size: 13px;
  margin-top: 6px;
}
</style>
