<template>
  <el-card header="新建回测">
    <el-form label-width="120px" style="max-width: 760px">
      <el-form-item label="任务名称">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="因子组合">
        <el-select v-model="factorNames" multiple filterable collapse-tags
                   placeholder="选择因子" style="width: 100%">
          <el-option v-for="f in factors" :key="f.name" :label="f.name" :value="f.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="回测区间">
        <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD"
                        start-placeholder="开始" end-placeholder="结束" />
      </el-form-item>
      <el-form-item label="持仓数量">
        <el-input-number v-model="form.top_n" :min="1" :max="200" />
      </el-form-item>
      <el-form-item label="调仓频率">
        <el-radio-group v-model="form.rebalance">
          <el-radio value="D">每日</el-radio>
          <el-radio value="W">每周</el-radio>
          <el-radio value="M">每月</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="加权方式">
        <el-radio-group v-model="form.weighting">
          <el-radio value="equal">等权</el-radio>
          <el-radio value="ic">IC加权</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="初始资金">
        <el-input-number v-model="form.initial_cash" :min="100000" :step="100000"
                         :formatter="(v: string) => `${v}`" style="width: 220px" />
      </el-form-item>
      <el-form-item label="复权方式">
        <el-radio-group v-model="form.adjust">
          <el-radio value="none">不复权</el-radio>
          <el-radio value="qfq">前复权</el-radio>
          <el-radio value="hfq">后复权</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="基准代码">
        <el-input v-model="form.benchmark" placeholder="如 600519.SH（留空则无基准）"
                  style="width: 280px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="running" @click="submit">开始回测</el-button>
        <el-button @click="$router.push('/backtests')">返回列表</el-button>
      </el-form-item>
    </el-form>
    <JobProgress ref="jobRef" />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { backtestApi, factorApi, strategyApi } from '@/api'
import JobProgress from '@/components/JobProgress.vue'

const route = useRoute()
const router = useRouter()
const factors = ref<any[]>([])
const factorNames = ref<string[]>(['price_mom_20', 'price_rev_20'])
const range = ref<[string, string]>(['2022-03-01', '2024-12-31'])
const jobRef = ref<InstanceType<typeof JobProgress>>()
const running = ref(false)
const form = reactive({
  name: 'web-backtest',
  top_n: 5,
  rebalance: 'M',
  weighting: 'equal',
  position_weighting: 'equal',
  initial_cash: 1_000_000,
  adjust: 'none',
  benchmark: '',
})

async function submit() {
  if (!factorNames.value.length || !range.value) {
    ElMessage.warning('请选择因子与回测区间')
    return
  }
  const payload = {
    ...form,
    factors: factorNames.value.map((name) => ({ name })),
    start: range.value[0],
    end: range.value[1],
  }
  const resp: any = await backtestApi.create(payload)
  running.value = true
  try {
    const result = await jobRef.value?.runJob(resp.job_id)
    if (result?.run_id) {
      ElMessage.success('回测完成')
      router.push(`/backtests/${result.run_id}`)
    }
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  factors.value = await factorApi.list()
  const sid = route.query.strategy
  if (sid) {
    const s: any = (await strategyApi.list()).find((x: any) => x.id === Number(sid))
    if (s) {
      form.name = s.name
      factorNames.value = s.factors.map((f: any) => f.name)
      form.top_n = s.rules?.top_n ?? 20
      form.rebalance = s.rebalance_freq
      form.weighting = s.weighting
    }
  }
})
</script>
