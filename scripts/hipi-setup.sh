#!/usr/bin/env bash
# HiPi EC801E 一键完整设置（含 AT 端口释放）
# 执行: sudo ~/Documents/workspace/hipi/scripts/hipi-setup.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "错误: 请用 sudo 执行: sudo $0" >&2
  exit 1
fi

USERNAME="${SUDO_USER:-$USER}"
HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
WS="$HOME_DIR/Documents/workspace/hipi"

SECTION() { echo; echo "==> $*"; }

# ────────────────────────────────────────────────────────────────────
SECTION "1. 启用 ModemManager debug 模式（mmat 备用通道）"
mkdir -p /etc/systemd/system/ModemManager.service.d
cat > /etc/systemd/system/ModemManager.service.d/hipi-debug.conf <<'UNIT'
[Service]
Environment=MM_FILTER_RULE_EXPLICIT_BLACKLIST=1
Environment=MM_FILTER_RULE_TTY_BLACKLIST=
ExecStart=
ExecStart=/usr/sbin/ModemManager --debug
UNIT
systemctl daemon-reload
echo "  已配置"

# ────────────────────────────────────────────────────────────────────
SECTION "2. 释放一个 AT 端口给 HiPi 直连"
# EC801E (2c7c:0903) 接口布局:
#   bInterfaceNumber 0 → ttyUSB1 (DIAG)
#   bInterfaceNumber 1 → ttyUSB2 (DIAG/PM)
#   bInterfaceNumber 2 → ttyUSB3 (AT)
#   bInterfaceNumber 3 → ttyUSB4 (AT, MM primary)
# 释放接口 2 (ttyUSB3)，保留接口 3 (ttyUSB4) 给 MM
cat > /etc/udev/rules.d/99-hipi-quectel.rules <<'RULE'
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2c7c", GROUP="plugdev", MODE="0660"
# 释放 bInterfaceNumber=02 (ttyUSB3 AT 口) 给 HiPi 直连
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", ATTRS{idProduct}=="0903", ATTRS{bInterfaceNumber}=="02", ENV{ID_MM_PORT_IGNORE}="1"
RULE
udevadm control --reload-rules
echo "  已安装 udev 规则（释放 ttyUSB3）"

# ────────────────────────────────────────────────────────────────────
SECTION "3. 拔插 EC801E USB（等待最长 60s）"
echo "  ⚠ 请现在拔掉 EC801E USB，等 3 秒后重新插入"
for i in $(seq 60 -1 1); do
  if lsusb -d 2c7c:0903 >/dev/null 2>&1; then
    echo "  检测到 EC801E"; break
  fi
  [[ $i -eq 1 ]] && { echo "  超时，请检查 USB 连接"; exit 1; }
  sleep 1
done
sleep 2

# ────────────────────────────────────────────────────────────────────
SECTION "4. 绑定 option 驱动"
modprobe option 2>/dev/null || true
sleep 0.5
echo "2c7c 0903" > /sys/bus/usb-serial/drivers/option1/new_id 2>/dev/null || true
sleep 0.5
if ! ls /dev/ttyUSB* >/dev/null 2>&1; then
  echo "  未检测到 /dev/ttyUSB*，请重新拔插 USB 后重试"; exit 1
fi
echo "  端口列表:"
ls -l /dev/ttyUSB*

# ────────────────────────────────────────────────────────────────────
SECTION "5. 重启 ModemManager"
# 清理旧过滤器（如果有，可能导致 MM 找不到模组）
rm -f /etc/ModemManager/conf.d/99-hipi-port-filter.conf
systemctl restart ModemManager
sleep 5
echo "  ModemManager 端口:"
mmcli -m 0 2>/dev/null | grep -E 'port|Port' || echo "  尚未识别模组（稍后自动识别）"

# ────────────────────────────────────────────────────────────────────
SECTION "6. 检查 dialout 组权限"
if groups "$USERNAME" | grep -qw dialout; then
  echo "  $USERNAME 已在 dialout 组"
else
  usermod -aG dialout "$USERNAME"
  echo "  已添加 $USERNAME 到 dialout 组（重新登录生效）"
fi

# ────────────────────────────────────────────────────────────────────
SECTION "7. 安装/更新 HiPi"
cd "$WS"
git pull --ff-only 2>/dev/null || true
sudo -u "$USERNAME" pip3 install --user --break-system-packages -q . 2>&1
echo "  安装完成"

# ────────────────────────────────────────────────────────────────────
SECTION "8. 重启 hipi-daemon"
pkill -f 'python3.*hipi-daemon' 2>/dev/null || true
sleep 1
rm -f /run/user/1000/hipi.sock
rm -f "$HOME_DIR/.config/hipi/at_port"
HIPI="/home/$USERNAME/.local/bin/hipi-daemon"
sudo -u "$USERNAME" nohup "$HIPI" > /dev/null 2>&1 &
echo "  daemon 已启动"
sleep 4

# ────────────────────────────────────────────────────────────────────
SECTION "9. 检查状态"
sudo -u "$USERNAME" /home/"$USERNAME"/.local/bin/hipi status 2>/dev/null \
  || echo "(daemon 尚未就绪，请稍后手动运行 hipi status)"

echo
echo "═══════════════════════════════════════"
echo "  设置完成！"
echo "  预期结果: sms_backend: 'at' 或 'mm'"
echo "  验证命令: hipi status        "
echo "  界面命令: hipi ui               "
echo "═══════════════════════════════════════"