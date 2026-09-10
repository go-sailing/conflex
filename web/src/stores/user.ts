import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('conflex_token') || '',
    role: localStorage.getItem('conflex_role') || 'admin',
    username: localStorage.getItem('conflex_username') || '',
  }),
  getters: {
    loggedIn: (s) => !!s.token,
  },
  actions: {
    setAuth(token: string, role: string, username = '') {
      this.token = token
      this.role = role
      this.username = username
      localStorage.setItem('conflex_token', token)
      localStorage.setItem('conflex_role', role)
      localStorage.setItem('conflex_username', username)
    },
    logout() {
      this.token = ''
      this.role = ''
      this.username = ''
      localStorage.removeItem('conflex_token')
      localStorage.removeItem('conflex_role')
      localStorage.removeItem('conflex_username')
    },
  },
})
