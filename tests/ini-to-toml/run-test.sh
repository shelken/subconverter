#!/usr/bin/env bash
# run-test.sh — INI→TOML 1:1 转换验证
# 启动临时 subconverter 容器，分别用 config.ini 和 config.toml 生成 Clash YAML
# 对比两份输出是否完全一致
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # tests/ini-to-toml/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)" # 项目根 (config.ini 所在)
CONTAINER_NAME="subconverter-test-$$"
IMAGE="${IMAGE:-asdlokj1qpi23/subconverter:0.9.9}"
PORT="${PORT:-25500}"

INI_OUTPUT="/tmp/subtest_ini_$$.yml"
TOML_OUTPUT="/tmp/subtest_toml_$$.yml"

cleanup() {
  echo "[cleanup] 停止容器 $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  rm -f "$INI_OUTPUT" "$TOML_OUTPUT"
}
trap cleanup EXIT

# ── Step 1: 启动容器 ──
# 挂载说明:
#   PROJECT_ROOT → /base/testsrc  (config.ini, config.toml)
#   SCRIPT_DIR   → /base/testdata (test_sub.txt)
echo "[step 1] 启动临时 subconverter 容器 (port $PORT)"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:25500" \
  -v "$PROJECT_ROOT:/base/testsrc" \
  -v "$SCRIPT_DIR:/base/testdata" \
  "$IMAGE" >/dev/null

BASE="http://127.0.0.1:$PORT"

# 等待就绪（最多 10s）
for i in $(seq 1 10); do
  if curl -m 2 -sf "$BASE/version" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -m 2 -sf "$BASE/version" >/dev/null 2>&1; then
  echo "[FAIL] 容器未启动成功"
  exit 1
fi
echo "        容器就绪"

# ── Step 2: Warmup（首轮下载远程规则集，避免正式请求超时）──
echo "[step 2] warmup — 下载远程规则集..."
if ! curl -m 900 -sS "$BASE/sub?target=clash&url=testdata/test_sub.txt&config=testsrc/config.ini" -o /dev/null; then
  echo "[FAIL] warmup 失败（规则集下载超时或网络问题）"
  exit 1
fi
echo "        warmup 完成"

# ── Step 3: 正式请求 ──
echo "[step 3] 请求 INI  配置 -> ${INI_OUTPUT##*/}"
curl -m 900 -sS "$BASE/sub?target=clash&url=testdata/test_sub.txt&config=testsrc/config.ini" -o "$INI_OUTPUT"

echo "[step 4] 请求 TOML 配置 -> ${TOML_OUTPUT##*/}"
curl -m 900 -sS "$BASE/sub?target=clash&url=testdata/test_sub.txt&config=testsrc/config.toml" -o "$TOML_OUTPUT"

# ── Step 4: 非空检查 ──
INI_LINES=$(wc -l < "$INI_OUTPUT")
TOML_LINES=$(wc -l < "$TOML_OUTPUT")
echo ""
echo "        INI:  ${INI_LINES} 行"
echo "        TOML: ${TOML_LINES} 行"

if [ "$INI_LINES" -eq 0 ]; then
  echo "[FAIL] INI 输出为空"
  exit 1
fi
if [ "$TOML_LINES" -eq 0 ]; then
  echo "[FAIL] TOML 输出为空"
  exit 1
fi

# ── Step 5: 比对 ──
INI_HASH=$(md5 -q "$INI_OUTPUT" 2>/dev/null || md5sum "$INI_OUTPUT" | awk '{print $1}')
TOML_HASH=$(md5 -q "$TOML_OUTPUT" 2>/dev/null || md5sum "$TOML_OUTPUT" | awk '{print $1}')

if [ "$INI_HASH" = "$TOML_HASH" ]; then
  echo ""
  echo "═══════════════════════════════════════════"
  echo "  ✅ PASS — 两份输出完全一致"
  echo "  INI md5:  $INI_HASH"
  echo "  TOML md5: $TOML_HASH"
  echo "═══════════════════════════════════════════"
else
  echo ""
  echo "═══════════════════════════════════════════"
  echo "  ❌ FAIL — 输出不一致"
  echo "  INI md5:  $INI_HASH"
  echo "  TOML md5: $TOML_HASH"
  echo "═══════════════════════════════════════════"
  echo ""
  diff "$INI_OUTPUT" "$TOML_OUTPUT" | head -80
  exit 1
fi
