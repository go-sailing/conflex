# Conflex · 多因子量化选股系统

本地优先（Local-first）的 A 股多因子量化研究平台：多源行情代理、因子研究、模拟交易、事件驱动回测与 Web 管理后台一体化，单机即可运行。

- 行情数据：多数据源自动故障轮换，已收盘 K 线本地永久缓存，绝不重复拉取
- 因子引擎：插件化因子注册、截面预处理流水线、IC/ICIR/分层分析、多因子合成选股
- 模拟持仓：贴近 A 股规则（T+1、涨跌停、整手、佣金/印花税/滑点）的纸上交易
- 回测引擎：事件驱动主循环 + 只读时钟，从架构层面防止未来函数与幸存者偏差
- Web 后台：Vue 3 管理界面，任务 SSE 实时进度，回测净值/回撤/月度热力图

> 仅供量化研究与学习，不接入实盘交易，不构成任何投资建议。

## 功能总览

| 模块 | 能力 |
| --- | --- |
| 行情数据获取代理 | Tushare / AKShare / synthetic（离线演示源）多源接入，优先级轮换、指数退避、熔断、令牌桶限频、并发请求去重；Parquet 按 `股票/年` 分区缓存，封闭数据（is_final）命中即零联网；原始价与复权因子分离存储，复权视图动态计算 |
| 多因子分析引擎 | 7 个内置因子（动量/反转/波动率/成交额/换手率/RSI/振幅），MAD 去极值、Z-Score 标准化、行业市值中性化；IC 时序、ICIR、胜率、分层收益；等权/IC 加权合成与 Top N 选股 |
| 模拟持仓管理 | 多账户、资金冻结/解冻、订单状态机、次日开盘撮合（涨停买不进/跌停卖不出/停牌拒单）、目标持仓差价单调仓、盘后盯市与净值快照 |
| 回测引擎 | 逐日事件循环（T 日信号、T+1 成交）、Point-in-time 股票池、夏普/索提诺/卡玛/最大回撤/信息比率/换手率指标、结果落库可复现 |
| Web 管理后台 | 仪表盘、数据源管理、更新任务、缓存 K 线浏览、因子库/分析/选股榜、策略 CRUD、模拟交易、回测新建与报告、任务管理、操作日志 |

## 系统架构

严格四层分层，依赖只能自上而下；CLI、Python SDK、Web REST API 共用同一套引擎内核：

```
入口层  Vue3 SPA / FastAPI REST / Typer CLI / Python SDK
应用层  MarketService / FactorService / SelectionService
        PaperService / BacktestService / JobManager(SSE)
领域层  marketdata / factors / portfolio / backtest（纯逻辑，无 IO）
基础设施 Tushare·AKShare·synthetic 适配器 / Parquet / SQLite / 安全(JWT)
```

详细设计见 [产品设计文档](docs/多因子量化选股系统产品设计文档.md) 与 [软件设计文档](docs/多因子量化选股系统软件设计文档.md)。

## 目录结构

```
conflex/
├── conflex/                  # Python 后端
│   ├── domain/               # 领域层：模型、行情端口、因子、持仓、回测
│   ├── application/          # 用例服务与异步任务管理器
│   ├── infra/                # 数据源适配器、Parquet/SQLite、安全
│   ├── entrypoints/          # CLI(typer) 与 WebAPI(FastAPI)
│   ├── container.py          # 依赖注入容器
│   └── resources/web_dist/   # 前端构建产物（随仓库分发，免构建启动）
├── web/                      # Vue3 + Vite + TS 前端源码
├── tests/                    # pytest（含多源轮换与回测黄金样本）
├── scripts/sync_web_dist.sh  # 前端构建并同步到后端托管目录
└── docs/                     # PRD 与软件设计文档
```

## 环境要求

- Python 3.10+
- （可选）Node.js 18+，仅在需要修改前端并重新构建时需要
- 无需任何外部数据库或中间件，行情存储为本地 Parquet + SQLite

## 快速开始

### 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[web,cli,dev]"
```

可选数据源依赖：

```bash
pip install -e ".[tushare]"   # 或 [akshare]
export TUSHARE_TOKEN=xxxxxx   # 密钥只走环境变量，不写入配置文件
```

未配置真实数据源时，系统使用内置 `synthetic` 确定性随机游走源（20 只演示股票），可完整体验全部功能与离线测试。

### 2. 启动 Web 管理后台

```bash
conflex init          # 初始化 SQLite、引导证券列表与交易日历
conflex web           # 默认 http://127.0.0.1:8899
```

浏览器打开 <http://127.0.0.1:8899>，首次登录提交的账号将自动成为管理员。服务默认只绑定回环地址。

### 3. 命令行使用

```bash
# 增量更新日线（封闭数据永久缓存，再次执行直接读本地）
conflex data update --start 2023-01-01
conflex data coverage                    # 查看缓存覆盖
conflex data repair --symbol 600519.SH --start 2024-01-01  # 强制重拉

conflex factor list                      # 因子库
conflex factor analyze price_rev_20 --start 2022-03-01     # IC/分层

conflex select --factors price_mom_20,price_rev_20 --top 10

conflex paper create demo                # 模拟账户
conflex backtest run --factors price_mom_20,price_rev_20 \
    --start 2022-03-01 --end 2024-12-31 --top 5 --rebalance M
```

## 前端开发

前端源码位于 `web/`，开发模式下 Vite 将 `/api` 代理到本地 8899 端口：

```bash
cd web
npm install
npm run dev              # http://127.0.0.1:5173
```

修改后重新构建并同步到后端托管目录：

```bash
bash scripts/sync_web_dist.sh
```

## 运行测试

```bash
pytest                    # 16 个用例：因子数值、T+1/费用、多源轮换、防未来、回测黄金样本、API 契约
```

## 数据与配置

- 运行时数据默认写入 `./data/`（可用环境变量 `CONFLEX_DATA_DIR` 覆盖）：
  - `market/daily/<symbol>/<year>.parquet`：日线分区
  - `meta.db`：SQLite 元数据/账户/订单/回测结果/任务/用户
- 配置优先级：环境变量 > `conflex.yaml` > 默认值；数据源 token 仅从环境变量读取
- 安全：JWT（HS256）鉴权、密码 PBKDF2 加盐哈希、数据源密钥脱敏展示、危险操作二次确认与审计日志

## 技术栈

**后端**：Python 3.10+、pandas、NumPy、PyArrow、FastAPI、Uvicorn、Typer、SQLite、Parquet
**前端**：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus、ECharts、axios

## 路线图

- [x] M1 数据底座（多源代理 + 永久缓存）
- [x] M2 因子引擎
- [x] M3 模拟持仓
- [x] M4 回测引擎
- [x] M5 Web 管理后台
- [ ] 分钟线、财务/基本面因子、复权因子定时更新、参数批量寻优、Viewer 只读角色

## 免责声明

本项目仅用于量化技术研究与教学，内置 synthetic 数据为随机生成的演示数据，不代表任何真实证券；回测收益不预示未来表现，使用者需自行承担研究与交易风险。
