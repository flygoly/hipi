# HiPi

Orange Pi Ubuntu Desktop 上的 4G 短信与通话桌面应用，优先支持 **Quectel EC801E-CN** USB 一体化模组。

## 快速开始（Orange Pi）

```bash
git clone https://github.com/flygoly/hipi.git
cd hipi
chmod +x scripts/install-orangepi.sh
./scripts/install-orangepi.sh
# 注销重登后
hipi ui
```

**完整 0→1 教程**（刷机、插卡、安装、验短信/语音）：[docs/getting-started.md](docs/getting-started.md)

## 功能

- 短信收发（会话列表、搜索、桌面通知、中文解码）
- 语音通话（拨号盘、来电接听、通话记录）
- 联系人簿（vCard 导入导出）
- 短信转发（号码 + Webhook HMAC 验签）
- 模组状态（信号、运营商、托盘 / GNOME 顶栏扩展）
- 首次运行向导、CSV 导出

## 系统要求

| 项目 | 要求 |
|------|------|
| 单板 | Orange Pi 6 Plus（或其他 ARM64） |
| 系统 | Ubuntu 24.04 Desktop（GNOME） |
| 模组 | Quectel EC801E-CN + 含语音/短信的 SIM |
| 服务 | ModemManager、PipeWire |

## 安装方式

### 一键安装（推荐）

```bash
./scripts/install-orangepi.sh [版本号]   # 默认 0.1.0
```

### 开发安装

```bash
sudo apt install python3-pip python3-gi python3-dbus modemmanager network-manager \
  pipewire pipewire-pulse libqmi-utils gir1.2-glib-2.0

pip install -e ".[dev]"
systemctl --user enable --now hipi-daemon
hipi ui
```

### 手动 deb 包

```bash
./packaging/debian/build-deb.sh 0.1.0
sudo dpkg -i build/debian/hipi_0.1.0_arm64.deb
```

安装后 `postinst` 会自动启用 `hipi-daemon`、GNOME 扩展，并配置 `loginctl enable-linger`。

## CLI 速查

```bash
hipi ping                      # 检查守护进程
hipi status                    # 模组状态
hipi unlock <PIN>              # 解锁 SIM
hipi send-sms <号> "内容"      # 发短信
hipi list-conversations        # 会话列表
hipi dial <号>                 # 拨打电话
hipi hangup                    # 挂断
hipi sync                      # 同步模组短信
hipi setup-audio               # 配置通话音频
hipi list-calls                # 通话记录
hipi list-contacts             # 联系人
```

## 验证与诊断

```bash
hipi ping && hipi status
./scripts/device-verify.sh
./scripts/modem-probe.sh
journalctl --user -u hipi-daemon -f
```

## 文档

| 文档 | 内容 |
|------|------|
| **[getting-started.md](docs/getting-started.md)** | **从零到一完整指南** |
| [hardware.md](docs/hardware.md) | 硬件连接与供电 |
| [device-checklist.md](docs/device-checklist.md) | 真机验收清单 |
| [troubleshooting.md](docs/troubleshooting.md) | 故障排除 |
| [webhook.md](docs/webhook.md) | Webhook 转发与验签 |
| [ec801e-one-shot.md](docs/ec801e-one-shot.md) | 验收快速索引 |

## 架构

```
hipi ui (PySide6)  ←RPC→  hipi-daemon  ←D-Bus→  ModemManager  ←USB→  EC801E
                              ↓
                           SQLite
```

## 许可证

Apache License 2.0 — 见 [LICENSE](LICENSE)
