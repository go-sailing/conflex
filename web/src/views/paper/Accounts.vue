<template>
  <div v-loading="loading">
    <el-card class="page-card">
      <div class="toolbar">
        <el-radio-group v-model="currentId" @change="loadDetail">
          <el-radio-button v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.name }}（{{ fmt(a.cash_available + a.cash_frozen + (a.market_value || 0)) }}）
          </el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="createDialog = true">新建账户</el-button>
        <template v-if="currentId">
          <el-button type="success" @click="orderDialog = true">手工下单</el-button>
          <el-button @click="rebalanceDialog = true">目标调仓</el-button>
          <el-button type="warning" @click="runDay">执行交易日撮合/结算</el-button>
        </template>
      </div>
    </el-card>

    <el-card v-if="currentId">
      <el-tabs v-model="tab">
        <el-tab-pane label="持仓" name="positions">
          <el-table :data="positions" size="small">
            <el-table-column prop="symbol" label="股票" width="140" />
            <el-table-column prop="qty" label="持仓量" width="100" />
            <el-table-column prop="available_qty" label="可用(T+1)" width="110" />
            <el-table-column prop="cost_price" label="成本价" width="100" />
            <el-table-column prop="last_price" label="最新价" width="100" />
            <el-table-column label="市值" width="140">
              <template #default="{ row }">{{ fmt(row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="浮动盈亏">
              <template #default="{ row }">
                <span :style="{ color: row.floating_pnl >= 0 ? '#ec0000' : '#00a854' }">
                  {{ fmt(row.floating_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="委托" name="orders">
          <el-table :data="orders" size="small">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="symbol" label="股票" width="130" />
            <el-table-column prop="side" label="方向" width="80">
              <template #default="{ row }">
                <el-tag :type="row.side === 'buy' ? 'danger' : 'success'" size="small">
                  {{ row.side === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="qty" label="数量" width="90" />
            <el-table-column prop="filled_qty" label="已成" width="90" />
            <el-table-column prop="status" label="状态" width="150" />
            <el-table-column prop="signal_date" label="信号日" width="120" />
            <el-table-column prop="trade_date" label="成交日" width="120" />
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button v-if="row.status === 'pending'" link type="danger" size="small"
                           @click="cancel(row.id)">撤单</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="成交" name="trades">
          <el-table :data="trades" size="small">
            <el-table-column prop="trade_date" label="成交日" width="120" />
            <el-table-column prop="symbol" label="股票" width="130" />
            <el-table-column prop="side" label="方向" width="80" />
            <el-table-column prop="qty" label="数量" width="100" />
            <el-table-column prop="price" label="成交价" width="100" />
            <el-table-column label="费用合计" width="120">
              <template #default="{ row }">
                {{ ((row.commission || 0) + (row.stamp_tax || 0) + (row.transfer_fee || 0)).toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="净值" name="equity">
          <EChart v-if="equity.length" :option="equityOption" />
          <el-empty v-else description="执行盘后结算后生成净值" :image-size="70" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建账户 -->
    <el-dialog v-model="createDialog" title="新建模拟账户" width="420px">
      <el-form label-width="90px">
        <el-form-item label="账户名"><el-input v-model="newAccount.name" /></el-form-item>
        <el-form-item label="初始资金">
          <el-input-number v-model="newAccount.initial_cash" :min="10000" :step="100000"
                           style="width: 200px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="createAccount">创建</el-button>
      </template>
    </el-dialog>

    <!-- 下单 -->
    <el-dialog v-model="orderDialog" title="手工下单（T 日信号、T+1 开盘成交）" width="460px">
      <el-form label-width="90px">
        <el-form-item label="股票代码"><el-input v-model="order.symbol" /></el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="order.side">
            <el-radio value="buy">买入</el-radio>
            <el-radio value="sell">卖出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数量(股)">
          <el-input-number v-model="order.qty" :min="100" :step="100" style="width: 200px" />
        </el-form-item>
        <el-form-item label="信号日期">
          <el-date-picker v-model="order.signal_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="orderDialog = false">取消</el-button>
        <el-button type="primary" @click="placeOrder">提交</el-button>
      </template>
    </el-dialog>

    <!-- 目标调仓 -->
    <el-dialog v-model="rebalanceDialog" title="目标持仓调仓" width="520px">
      <el-form label-width="90px">
        <el-form-item label="目标权重">
          <el-input v-model="weightsText" type="textarea" :rows="5"
                    placeholder='JSON 格式，如 {"600519.SH": 0.2, "000001.SZ": 0.3}' />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="day" type="date" value-format="YYYY-MM-DD"
                          placeholder="默认今天" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rebalanceDialog = false">取消</el-button>
        <el-button @click="previewRebalance">预览差价单</el-button>
        <el-button type="primary" @click="commitRebalance">确认调仓</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { paperApi } from '@/api'
import EChart from '@/components/EChart.vue'

const route = useRoute()
const loading = ref(false)
const accounts = ref<any[]>([])
const currentId = ref<number | null>(null)
const tab = ref('positions')
const positions = ref<any[]>([])
const orders = ref<any[]>([])
const trades = ref<any[]>([])
const equity = ref<any[]>([])

const createDialog = ref(false)
const newAccount = reactive({ name: '', initial_cash: 1_000_000 })
const orderDialog = ref(false)
const order = reactive({ symbol: (route.query.symbol as string) || '', side: 'buy',
  qty: 1000, signal_date: '' })
const rebalanceDialog = ref(false)
const weightsText = ref('')
const day = ref('')

const equityOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 80, right: 30, top: 30, bottom: 40 },
  xAxis: { type: 'category', data: equity.value.map((e) => e.trade_date) },
  yAxis: { type: 'value', scale: true },
  dataZoom: [{ type: 'inside' }],
  series: [
    { name: '总资产', type: 'line', data: equity.value.map((e) => e.total_equity),
      showSymbol: false, lineStyle: { width: 2 } },
  ],
}))

function fmt(v: any) {
  return Number(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

async function loadAccounts() {
  accounts.value = await paperApi.accounts()
  if (!currentId.value && accounts.value.length) currentId.value = accounts.value[0].id
  if (currentId.value) await loadDetail()
}
async function loadDetail() {
  if (!currentId.value) return
  loading.value = true
  try {
    const [p, o, t, e] = await Promise.all([
      paperApi.positions(currentId.value),
      paperApi.orders(currentId.value),
      paperApi.trades(currentId.value),
      paperApi.equity(currentId.value),
    ])
    positions.value = p
    orders.value = o
    trades.value = t
    equity.value = e
  } finally {
    loading.value = false
  }
}
async function createAccount() {
  if (!newAccount.name) return ElMessage.warning('请输入账户名')
  const r: any = await paperApi.createAccount({ ...newAccount })
  createDialog.value = false
  newAccount.name = ''
  ElMessage.success('账户已创建')
  await loadAccounts()
  currentId.value = r.id
}
async function placeOrder() {
  await paperApi.placeOrder(currentId.value!, {
    symbol: order.symbol, side: order.side, qty: order.qty,
    signal_date: order.signal_date || null,
  })
  orderDialog.value = false
  ElMessage.success('委托已提交，下一交易日开盘撮合')
  await loadDetail()
}
async function cancel(id: number) {
  await paperApi.cancelOrder(currentId.value!, id)
  ElMessage.success('已撤单')
  await loadDetail()
}
async function runDay() {
  const r: any = await paperApi.marketDay(currentId.value!, day.value || undefined)
  ElMessage.success(`成交 ${r.filled} 笔，拒绝 ${r.rejected} 笔，总资产 ${r.total_equity}`)
  await loadDetail()
}
async function previewRebalance() {
  const weights = JSON.parse(weightsText.value)
  const r: any = await paperApi.rebalance(currentId.value!, { weights, on: day.value || null, commit: false })
  ElMessage.info(`差价单 ${r.length} 笔：` + r.map((x: any) => `${x.side === 'buy' ? '买' : '卖'}${x.symbol}x${x.qty}`).join('；'))
}
async function commitRebalance() {
  const weights = JSON.parse(weightsText.value)
  const r: any = await paperApi.rebalance(currentId.value!, { weights, on: day.value || null, commit: true })
  ElMessage.success(`已生成 ${r.orders.length} 张委托单`)
  rebalanceDialog.value = false
  tab.value = 'orders'
  await loadDetail()
}

onMounted(loadAccounts)
</script>
