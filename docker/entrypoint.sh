#!/bin/sh
# 容器入口：首次启动初始化证券列表/交易日历，随后启动 Web 服务
set -e

PORT="${CONFLEX_WEB_PORT:-8899}"
DATA="${CONFLEX_DATA_DIR:-/data}"

# 判断是否已完成引导：证券列表为空（含 meta.db 不存在或上次引导被中断的情况）即视为未初始化
if [ "${CONFLEX_AUTO_INIT:-true}" = "true" ]; then
    NEED_INIT=$(python -c "
import os, sqlite3
p = os.path.join('${DATA}', 'meta.db')
try:
    ready = os.path.exists(p) and sqlite3.connect(p).execute(
        'select count(*) from instrument').fetchone()[0] > 0
except Exception:
    ready = False
print('0' if ready else '1')
" 2>/dev/null || echo 1)

    if [ "$NEED_INIT" = "1" ]; then
        echo "[entrypoint] 首次启动，执行 conflex init 初始化证券列表与交易日历…"
        # 限时引导：数据源整体不可达/卡死时不阻断 Web 启动，界面内执行数据更新会自动补引导
        timeout "${CONFLEX_INIT_TIMEOUT:-300}" conflex init \
            || echo "[entrypoint] 警告：初始化未完成（数据源网络不可达或超时），Web 服务仍将继续启动。"
    fi
fi

echo "[entrypoint] 启动 Conflex Web：http://0.0.0.0:${PORT}"
# 单进程：JobManager 为进程内组件且 SQLite 为单文件库，不适合多 worker
exec uvicorn conflex.entrypoints.webapi.asgi:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --proxy-headers \
    --forwarded-allow-ips "*"
