# Conflex 多因子量化选股系统镜像
# 前端构建产物已随仓库分发（conflex/resources/web_dist），无需 Node 构建阶段
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    CONFLEX_DATA_DIR=/data \
    CONFLEX_WEB_PORT=8899

# tzdata：A 股交易日历依赖本机时区；curl 便于容器内排查
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先拷贝安装清单与包源码（web_dist 作为 package_data 随包安装）
COPY pyproject.toml ./
COPY conflex ./conflex

# 可通过 --build-arg PIP_INDEX_URL=<镜像源> 加速依赖下载
ARG PIP_INDEX_URL=https://pypi.org/simple
# web/cli：Web 后台与命令行；其余 extras 为可选行情数据源 SDK（代码内为延迟导入）
RUN pip install --upgrade pip -i "${PIP_INDEX_URL}" \
    && pip install ".[web,cli,tushare,akshare,baostock,efinance]" -i "${PIP_INDEX_URL}"

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 持久化运行时数据：meta.db(SQLite)、Parquet 行情、因子缓存、日志、JWT 密钥
VOLUME ["/data"]

EXPOSE 8899

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${CONFLEX_WEB_PORT}/api/v1/health" || exit 1

ENTRYPOINT ["entrypoint.sh"]
