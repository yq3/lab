#!/usr/bin/env bash
# 一键拉起计税/申报两个 A2A server（Ctrl-C 一起退）。
# 首次运行前请配置 .env（参照 .env.example）——server 启动本身不需要 LLM key，
# 只有主 agent 的 CLI / smoke.py 需要。
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --all-packages

trap 'kill $(jobs -p) 2>/dev/null' EXIT

uv run --no-sync python -m tax_calc.server &
uv run --no-sync python -m tax_filing.server &

echo
echo "两个 A2A server 已启动："
echo "  计税 agent  http://127.0.0.1:9101/.well-known/agent-card.json"
echo "  申报 agent  http://127.0.0.1:9102/.well-known/agent-card.json"
echo "另开终端运行健康检查：uv run python scripts/doctor.py"
echo
wait
