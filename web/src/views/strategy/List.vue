<template>
  <el-card header="策略管理">
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建策略</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="strategies" size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="策略名" width="180" />
      <el-table-column label="因子组合" min-width="260">
        <template #default="{ row }">
          <el-tag v-for="f in row.factors" :key="f.name" size="small" style="margin: 2px">
            {{ f.name }}<span v-if="f.weight">:{{ f.weight }}</span>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="weighting" label="加权" width="90" />
      <el-table-column label="选股数" width="90">
        <template #default="{ row }">{{ row.rules?.top_n ?? 20 }}</template>
      </el-table-column>
      <el-table-column prop="rebalance_freq" label="调仓" width="80" />
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          <el-button link type="success" size="small"
                     @click="$router.push({ name: 'backtest-new', query: { strategy: row.id } })">
            去回测
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑策略' : '新建策略'" width="640px">
      <el-form label-width="100px">
        <el-form-item label="策略名">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="因子与权重">
          <div v-for="(item, idx) in form.factors" :key="idx" class="factor-row">
            <el-select v-model="item.name" filterable placeholder="因子" style="width: 240px">
              <el-option v-for="f in factors" :key="f.name" :label="f.name" :value="f.name" />
            </el-select>
            <el-input-number v-model="item.weight" :min="0" :step="0.1" controls-position="right"
                             placeholder="权重" style="width: 150px" />
            <el-button link type="danger" @click="form.factors.splice(idx, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.factors.push({ name: '', weight: 1 })">
            + 添加因子
          </el-button>
        </el-form-item>
        <el-form-item label="加权方式">
          <el-radio-group v-model="form.weighting">
            <el-radio value="equal">等权</el-radio>
            <el-radio value="manual">自定义</el-radio>
            <el-radio value="ic">IC加权</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="持仓数量">
          <el-input-number v-model="form.rules.top_n" :min="1" :max="200" />
        </el-form-item>
        <el-form-item label="调仓频率">
          <el-radio-group v-model="form.rebalance_freq">
            <el-radio value="D">每日</el-radio>
            <el-radio value="W">每周</el-radio>
            <el-radio value="M">每月</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { factorApi, strategyApi } from '@/api'

const strategies = ref<any[]>([])
const factors = ref<any[]>([])
const loading = ref(false)
const dialog = ref(false)
const form = reactive<any>({ id: null, name: '', factors: [{ name: 'price_mom_20', weight: 1 }],
  weighting: 'equal', rules: { top_n: 20 }, rebalance_freq: 'M' })

async function load() {
  loading.value = true
  try {
    strategies.value = await strategyApi.list()
  } finally {
    loading.value = false
  }
}
function openCreate() {
  Object.assign(form, { id: null, name: '', factors: [{ name: 'price_mom_20', weight: 1 }],
    weighting: 'equal', rules: { top_n: 20 }, rebalance_freq: 'M' })
  dialog.value = true
}
function openEdit(row: any) {
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  dialog.value = true
}
async function save() {
  if (!form.name || !form.factors.some((f: any) => f.name)) {
    ElMessage.warning('策略名与至少一个因子必填')
    return
  }
  const payload: any = {
    name: form.name,
    factors: form.factors.filter((f: any) => f.name),
    weighting: form.weighting,
    rules: form.rules,
    rebalance_freq: form.rebalance_freq,
  }
  if (form.id) {
    await strategyApi.update(form.id, payload)
  } else {
    await strategyApi.create(payload)
  }
  ElMessage.success('已保存')
  dialog.value = false
  await load()
}
async function remove(row: any) {
  await ElMessageBox.confirm(`确认删除策略「${row.name}」？`, '提示', { type: 'warning' })
  await strategyApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}
onMounted(async () => {
  factors.value = await factorApi.list()
  await load()
})
</script>

<style scoped>
.factor-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}
</style>
