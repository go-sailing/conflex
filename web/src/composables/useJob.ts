import { ref } from 'vue'
import { jobApi } from '@/api'

export interface JobRunState {
  running: boolean
  status: string
  progress: number
  stage: string
  logs: string[]
  result: any
  error: string
}

/**
 * 订阅异步任务：通过 SSE 实时接收进度/日志/完成事件。
 * EventSource 不支持自定义请求头，token 走 query 参数（后端兼容）。
 */
export function useJob() {
  const state = ref<JobRunState>({
    running: false,
    status: '',
    progress: 0,
    stage: '',
    logs: [],
    result: null,
    error: '',
  })
  let es: EventSource | null = null

  async function run(jobId: number): Promise<any> {
    state.value = {
      running: true,
      status: 'queued',
      progress: 0,
      stage: '排队中',
      logs: [],
      result: null,
      error: '',
    }
    return new Promise((resolve, reject) => {
      const token = localStorage.getItem('conflex_token') || ''
      es = new EventSource(`/api/v1/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`)

      es.addEventListener('progress', (e: MessageEvent) => {
        const d = JSON.parse(e.data)
        state.value.progress = d.progress ?? state.value.progress
        state.value.stage = d.stage ?? state.value.stage
        state.value.status = 'running'
      })
      es.addEventListener('log', (e: MessageEvent) => {
        state.value.logs.push(JSON.parse(e.data).line)
      })
      es.addEventListener('finished', (e: MessageEvent) => {
        const d = JSON.parse(e.data)
        state.value.running = false
        state.value.status = 'succeeded'
        state.value.progress = 1
        state.value.stage = '完成'
        state.value.result = d.result
        cleanup()
        resolve(d.result)
      })
      es.addEventListener('error', (e: any) => {
        // 首次连接错误可能是网络问题；带任务错误信息的 event 才判定失败
        if (e && e.data) {
          const d = JSON.parse(e.data)
          state.value.running = false
          state.value.status = 'failed'
          state.value.error = d.error || '任务失败'
          cleanup()
          reject(new Error(state.value.error))
        }
      })
    })
  }

  async function cancel() {
    // EventSource 无取消语义，调后端置取消标志
  }

  function cleanup() {
    es?.close()
    es = null
  }

  return { state, run, cancel }
}
