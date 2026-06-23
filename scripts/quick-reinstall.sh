#!/usr/bin/env bash
# 快速重装 HiPi（不拔插 USB）
set -euo pipefail
cd ~/Documents/workspace/hipi
echo "==> 安装 HiPi"
pip3 install --user --break-system-packages -q .
echo "==> 重启 hipi-daemon"
pkill -9 -f hipi-daemon 2>/dev/null || true
sleep 1
rm -f /run/user/1000/hipi.sock
nohup ~/.local/bin/hipi-daemon > /dev/null 2>&1 &
sleep 3
echo "==> 状态"
~/.local/bin/hipi status
echo ""
echo "==> 完成，运行 hipi ui 打开界面 =="