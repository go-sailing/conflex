#!/usr/bin/env bash
# 构建前端并同步到后端托管目录（conflex/resources/web_dist）
set -euo pipefail
cd "$(dirname "$0")/.."

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

cd web
npm install --no-audit --no-fund
npm run build
cd ..

rm -rf conflex/resources/web_dist
mkdir -p conflex/resources/web_dist
cp -r web/dist/. conflex/resources/web_dist/
echo "同步完成：conflex/resources/web_dist"
