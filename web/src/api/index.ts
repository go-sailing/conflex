import http from './request'

export const authApi = {
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }),
  me: () => http.get('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    http.put('/auth/password', { old_password, new_password }),
}

export const dataApi = {
  sources: () => http.get('/data-sources'),
  testSource: (name: string) => http.post(`/data-sources/${name}/test`),
  bootstrap: () => http.post('/data/bootstrap'),
  createJob: (body: Record<string, any>) => http.post('/data/jobs', body),
  coverage: () => http.get('/cache/coverage'),
  bars: (params: Record<string, any>) => http.get('/market/bars', { params }),
}

export const factorApi = {
  list: () => http.get('/factors'),
  analysis: (body: Record<string, any>) => http.post('/factors/analysis', body),
  scores: (params: Record<string, any>) => http.get('/scores', { params }),
}

export const strategyApi = {
  list: () => http.get('/strategies'),
  create: (body: Record<string, any>) => http.post('/strategies', body),
  update: (id: number, body: Record<string, any>) => http.put(`/strategies/${id}`, body),
  remove: (id: number) => http.delete(`/strategies/${id}`),
}

export const paperApi = {
  accounts: () => http.get('/accounts'),
  createAccount: (body: { name: string; initial_cash: number }) =>
    http.post('/accounts', body),
  positions: (id: number) => http.get(`/accounts/${id}/positions`),
  orders: (id: number, status?: string) =>
    http.get(`/accounts/${id}/orders`, { params: status ? { status } : {} }),
  trades: (id: number) => http.get(`/accounts/${id}/trades`),
  equity: (id: number) => http.get(`/accounts/${id}/equity`),
  placeOrder: (id: number, body: Record<string, any>) =>
    http.post(`/accounts/${id}/orders`, body),
  cancelOrder: (accountId: number, orderId: number) =>
    http.delete(`/orders/${orderId}`, { params: { account_id: accountId } }),
  rebalance: (id: number, body: Record<string, any>) =>
    http.post(`/accounts/${id}/rebalance`, body),
  marketDay: (id: number, day?: string) =>
    http.post(`/accounts/${id}/market-day`, { day }),
}

export const backtestApi = {
  create: (body: Record<string, any>) => http.post('/backtests', body),
  list: () => http.get('/backtests'),
  report: (id: number) => http.get(`/backtests/${id}/report`),
}

export const jobApi = {
  list: (limit = 50) => http.get('/jobs', { params: { limit } }),
  get: (id: number) => http.get(`/jobs/${id}`),
  cancel: (id: number) => http.post(`/jobs/${id}/cancel`),
  logs: (id: number) => http.get(`/jobs/${id}/logs`),
}

export const systemApi = {
  dashboard: () => http.get('/dashboard'),
  logs: (limit = 100) => http.get('/operation-logs', { params: { limit } }),
  quarantine: (limit = 100) => http.get('/quarantine', { params: { limit } }),
}
