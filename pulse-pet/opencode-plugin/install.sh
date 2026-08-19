#!/usr/bin/env bash
# PulsePet opencode 插件安装/卸载（macOS / Linux，TC-EV-01 / TC-EV-02）。
#
# 用法：
#   ./install.sh              # 安装（幂等）
#   ./install.sh --uninstall  # 卸载（只移除 --pulse-pet-managed 项）
#
# 依赖：node（仅用于 JSONC 感知的配置合并；插件本体运行在 opencode 的 Bun 运行时）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="$SCRIPT_DIR/pulse-pet-hook.js"
CONFIG_TOOL="$SCRIPT_DIR/opencode-config.mjs"

OPENCODE_DIR="${OPENCODE_DIR:-$HOME/.config/opencode}"
PLUGINS_DIR="$OPENCODE_DIR/plugins"
PLUGIN_FILE="$PLUGINS_DIR/pulse-pet-hook.js"

# 选择 opencode 配置：优先 opencode.json，其次 opencode.jsonc，都不存在则新建 opencode.json
find_config() {
  if [ -f "$OPENCODE_DIR/opencode.json" ]; then
    echo "$OPENCODE_DIR/opencode.json"
  elif [ -f "$OPENCODE_DIR/opencode.jsonc" ]; then
    echo "$OPENCODE_DIR/opencode.jsonc"
  else
    echo "$OPENCODE_DIR/opencode.json"
  fi
}

do_install() {
  mkdir -p "$PLUGINS_DIR"
  cp "$HOOK_SRC" "$PLUGIN_FILE"

  local cfg
  cfg="$(find_config)"
  if [ ! -f "$cfg" ]; then
    printf '{\n  "plugin": []\n}\n' > "$cfg"
  fi
  node "$CONFIG_TOOL" install "$cfg"

  echo "[pulse-pet] installed: hook -> $PLUGIN_FILE"
  echo "[pulse-pet] merged plugin entry into $cfg (idempotent, JSONC-safe)"
}

do_uninstall() {
  local cfg
  cfg="$(find_config)"
  if [ -f "$cfg" ]; then
    node "$CONFIG_TOOL" uninstall "$cfg"
    echo "[pulse-pet] removed managed plugin entry from $cfg"
  fi
  rm -f "$PLUGIN_FILE"
  echo "[pulse-pet] removed $PLUGIN_FILE"
}

if [ "${1:-}" = "--uninstall" ] || [ "${1:-}" = "uninstall" ]; then
  do_uninstall
else
  do_install
fi
