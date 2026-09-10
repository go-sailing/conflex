import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 60_000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('conflex_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (resp) => resp.data,
  (error: AxiosError<any>) => {
    const status = error.response?.status
    const detail = (error.response?.data as any)?.msg || error.message || '请求失败'
    if (status === 401) {
      localStorage.removeItem('conflex_token')
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
    } else {
      ElMessage.error(detail)
    }
    return Promise.reject(error)
  },
)

export default request
