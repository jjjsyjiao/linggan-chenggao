#!/usr/bin/env bash

# 小红书爆款笔记接口 curl 调用示例（集成测试 shell 版）
#
# 用法（在项目根目录执行）：
#   chmod +x tests/integration/xhs_note_curl.sh
#   APP_API_KEY=your-key ./tests/integration/xhs_note_curl.sh
#
# 可选环境变量：
#   XHS_BASE_URL  默认 http://127.0.0.1:8071
#   APP_API_KEY   作为 X-API-Key 发送到服务端

set -euo pipefail

BASE_URL="${XHS_BASE_URL:-http://127.0.0.1:8072}"
API_KEY="${APP_API_KEY:-test-key}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMG1="${SCRIPT_DIR}/20260202161329_150_6.jpg"
IMG2="${SCRIPT_DIR}/20260202161331_151_6.jpg"
IMG3="${SCRIPT_DIR}/20260202161332_152_6.jpg"
IMG4="${SCRIPT_DIR}/20260202161333_153_6.jpg"

for img in "$IMG1" "$IMG2" "$IMG3" "$IMG4"; do
  if [[ ! -f "$img" ]]; then
    echo "❌ 找不到测试图片: $img" >&2
    exit 1
  fi
done

IDEA_TEXT="我想分享最近开始用地中海饮食减脂"

echo "➡ 调用 ${BASE_URL}/api/v1/xhs/notes/report ..."

curl -v \
  -H "X-API-Key: ${API_KEY}" \
  -F "idea_text=${IDEA_TEXT}" \
  -F "images=@${IMG1};type=image/jpeg" \
  -F "images=@${IMG2};type=image/jpeg" \
  -F "images=@${IMG3};type=image/jpeg" \
  -F "images=@${IMG4};type=image/jpeg" \
  "${BASE_URL}/api/v1/xhs/notes/report"

echo

