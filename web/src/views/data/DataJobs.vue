<template>
  <el-card header="数据更新任务">
    <div class="toolbar">
      <el-button type="primary" @click="openDialog">新建任务</el-button>
      <el-button @click="loadJobs">刷新</el-button>
    </div>
    <el-table :data="jobs" size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="kind" label="类型" width="140" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="180">
        <template #default="{ row }">
          <el-progress :percentage="Math.round((row.progress || 0) * 100)" :stroke-width="10" />
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" min-width="140" />
      <el-table-column prop="error" label="错误" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>

    <el-dialog v-model="dialog" title="新建数据任务" width="520px">
      <el-form label-width="90px">
        <el-form-item label="任务类型">
          <el-radio-group v-model="form.type">
            <el-radio value="update">增量更新</el-radio>
            <el-radio value="repair">数据修复</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="form.type === 'update'">
          <el-form-item label="股票池">
            <el-select v-model="form.universe" style="width: 100%">
              <el-option v-for="u in universes" :key="u.key" :label="u.name" :value="u.key" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.universe === 'custom'" label="股票列表">
            <el-input v-model="form.symbolsRaw" type="textarea" :rows="3"
                      placeholder="每行一个，如 000001.SZ" />
          </el-form-item>
        </template>
        <el-form-item v-else label="股票代码">
          <el-input v-model="form.symbol" placeholder="如 000001.SZ" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="form.start" type="date" value-format="YYYY-MM-DD"
                          placeholder="开始日期" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="form.end" type="date" value-format="YYYY-MM-DD"
                          placeholder="结束日期（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="submit" :loading="submitting">提交</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { dataApi, jobApi } from '@/api'

const jobs = ref<any[]>([])
const universes = ref<any[]>([])
const loading = ref(false)
const dialog = ref(false)
const submitting = ref(false)
const form = reactive({
  type: 'update',
  universe: 'all',
  symbol: '',
  symbolsRaw: '',
  start: '',
  end: '',
})

function statusType(s: string) {
  return { succeeded: 'success', failed: 'danger', running: 'primary', queued: 'info' }[s] || 'info'
}

function openDialog() {
  form.type = 'update'
  form.universe = 'all'
  form.symbol = ''
  form.symbolsRaw = ''
  form.start = ''
  form.end = ''
  dialog.value = true
}

async function loadUniverses() {
  try {
    universes.value = await dataApi.universes()
    universes.value.push({ key: 'custom', name: '自定义' })
  } catch {
    universes.value = [
      { key: 'all', name: '全部A股' },
      { key: 'hs300', name: '沪深300' },
      { key: 'zz500', name: '中证500' },
      { key: 'zz1000', name: '中证1000' },
      { key: 'star', name: '科创板' },
      { key: 'chinext', name: '创业板' },
      { key: 'main', name: '主板' },
      { key: 'custom', name: '自定义' },
    ]
  }
}

async function loadJobs() {
  loading.value = true
  try {
    jobs.value = await jobApi.list(100)
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (form.type === 'repair' && !form.symbol) {
    ElMessage.warning('修复任务需填写股票代码')
    return
  }
  if (!form.start) {
    ElMessage.warning('请选择开始日期')
    return
  }
  if (form.type === 'update' && form.universe === 'custom') {
    const symbols = form.symbolsRaw.split('\n').map(s => s.trim()).filter(Boolean)
    if (!symbols.length) {
      ElMessage.warning('自定义模式需填写股票代码')
      return
    }
  }
  submitting.value = true
  try {
    const body: Record<string, any> = {
      type: form.type,
      start: form.start,
    }
    if (form.type === 'repair') {
      body.symbol = form.symbol
    } else {
      if (form.universe === 'custom') {
        body.symbols = form.symbolsRaw.split('\n').map(s => s.trim()).filter(Boolean)
      } else {
        body.universe = form.universe
      }
    }
    if (form.end) body.end = form.end
    await dataApi.createJob(body)
    ElMessage.success('任务已提交')
    dialog.value = false
    await loadJobs()
  } catch {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadUniverses()
  loadJobs()
})
</script>
