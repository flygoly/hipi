# HiPi

Orange Pi Ubuntu Desktop 上的 4G 短信与通话桌面应用，优先支持 **Quectel EC801E-CN** USB 一体化模组。

## 功能

- 短信收发（会话列表、撰写、系统通知）
- 语音通话（拨号盘、来电接听、通话记录）
- 模组状态（信号、运营商、IMEI）
- 首次运行向导
- 系统托盘

## 系统要求

- Orange Pi 6 Plus（或其他 ARM64 Ubuntu Desktop）
- Ubuntu 24.04 Desktop（GNOME）
- Quectel EC801E-CN USB 模组 + SIM 卡
- `modemmanager`, `network-manager`, `pipewire`

## 快速安装（开发）

```bash
sudo apt install python3-gi python3-dbus modemmanager network-manager pipewire \
  libqmi-utils gir1.2-glib-2.0

pip install -e ".[dev]"

# 启动守护进程
hipi-daemon &

# 启动 UI
hipi ui
```

## CLI

```bash
hipi status
hipi unlock <PIN>
hipi send-sms 13800138000 "你好"
hipi list-messages
```

## 打包安装（开箱即用）

```bash
chmod +x packaging/debian/build-deb.sh
./packaging/debian/build-deb.sh 0.1.0
sudo dpkg -i build/debian/hipi_0.1.0_arm64.deb

# 启用用户服务
systemctl --user enable --now hipi-daemon
```

安装后从应用菜单启动 **HiPi**，或运行 `hipi ui`。

## 诊断

```bash
chmod +x scripts/modem-probe.sh scripts/quectel-voice-setup.sh
./scripts/modem-probe.sh
```

## 文档

- [硬件说明](docs/hardware.md)
- [故障排除](docs/troubleshooting.md)

## 架构

- **hipi-daemon**: ModemManager D-Bus 桥接、短信/通话、SQLite、Unix socket RPC
- **hipi ui**: PySide6 桌面界面

## 许可证

Apache License 2.0 — 见 [LICENSE](LICENSE)
