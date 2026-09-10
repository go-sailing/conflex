<template>
  <el-card v-if="visible" class="job-card" shadow="never">
    <div class="head">
      <el-tag :type="tagType" size="small">{{ statusText }}</el-tag>
      <span class="stage">{{ state.stage }}</span>
      <el-button v-if="state.running" link size="small" @click="visible = false">后台运行</el-button>
    </div>
    <el-progress :percentage="Math.round(state.progress * 100)" :status="progressStatus" />
    <div v-if="state.logs.length" class="log-box">
      <div v-for="(line, i) in state.logs" :key="i">{{ line }}</div>
    </div>
    <el-alert v-if="state.error" :title="state.error" type="error" :closable="false" />
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useJob } from '@/composables/useJob'

const { state, run } = useJob()
const visible = ref(false)

const statusText = computed(() => {
  return { queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败' }[
    state.value.status
  ] || state.value.status
})
const tagType = computed(() => {
  return { running: 'primary', succeeded: 'success', failed: 'danger' }[state.value.status] || 'info'
})
const progressStatus = computed(() => {
  if (state.value.status === 'failed') return Number(0) as any
  return state.value.status === 'succeeded' ? 'success' : undefined
})

async function runJob(jobId: number): Promise<any> {
  visible.value = true
  try {
    return await run(jobId)
  } catch {
    return null
  }
}

defineExpose({ runJob })
</script>

<style scoped>
.job-card {
  margin-bottom: 14px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.stage {
  color: #606266;
  font-size: 13px;
  flex: 1;
}
</style>
