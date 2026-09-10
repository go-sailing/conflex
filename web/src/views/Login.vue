<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="brand">
        <el-icon :size="30" color="#409eff"><TrendCharts /></el-icon>
        <h2>Conflex 多因子量化选股系统</h2>
      </div>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="username" size="large" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" size="large" type="password" show-password
                    placeholder="密码" :prefix-icon="Lock" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading"
                   @click="submit">
          登录 / 首次启动创建管理员
        </el-button>
      </el-form>
      <p class="tip">首次使用时，本次提交的账号将自动成为管理员。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { authApi } from '@/api'
import { useUserStore } from '@/stores/user'

const username = ref('admin')
const password = ref('')
const loading = ref(false)
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const resp: any = await authApi.login(username.value, password.value)
    userStore.setAuth(resp.token, resp.role, username.value)
    ElMessage.success('登录成功')
    router.replace((route.query.redirect as string) || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d 0%, #2c5d8f 100%);
}
.login-card {
  width: 420px;
  padding: 16px 12px;
}
.brand {
  text-align: center;
  margin-bottom: 22px;
}
.brand h2 {
  font-size: 17px;
  margin: 10px 0 0;
  color: #303133;
}
.tip {
  text-align: center;
  color: #909399;
  font-size: 12px;
  margin: 12px 0 0;
}
</style>
