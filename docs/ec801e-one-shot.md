# EC801E 真机一次性验收流程

面向 Orange Pi 6 Plus + Ubuntu Desktop GNOME + Quectel EC801E-CN 的完整上机流程。按顺序执行，可在一天内完成安装与验收。

## 1. 硬件与镜像

1. 刷入官方 **Ubuntu 24.04 Desktop GNOME** 镜像（Orange Pi 6 Plus）
2. EC801E 插入 **USB 3.0 HOST**，SIM 已开通语音与短信
3. 登录桌面用户（后续 systemd 用户服务依赖此账户）

## 2. 获取代码

```bash
git clone git@github.com:flygoly/hipi.git
cd hipi
```

## 3. 安装方式（二选一）

### A. 开发安装（推荐调试）

```bash
sudo apt install python3-pip python3-gi python3-dbus modemmanager network-manager \
  pipewire pipewire-pulse libqmi-utils gir1.2-glib-2.0

pip install -e ".[dev]"
systemctl --user enable --now hipi-daemon
hipi ui
```

### B. 打包安装（接近量产）

```bash
chmod +x packaging/debian/build-deb.sh
./packaging/debian/build-deb.sh 0.1.0
sudo dpkg -i build/debian/hipi_0.1.0_arm64.deb
# 注销并重新登录（dialout/plugdev 组）
```

`postinst` 会自动 `systemctl --user enable --now hipi-daemon`。

## 4. 自动化预检

```bash
chmod +x scripts/run-tests.sh scripts/device-verify.sh
./scripts/run-tests.sh
./scripts/device-verify.sh
```

可选冒烟（需设置测试号码，会向该号码发短信）：

```bash
export HIPI_SMOKE_NUMBER=13800138000
./scripts/device-verify.sh --smoke
```

## 5. GNOME 顶栏扩展（可选）

安装 `.deb` 时会自动为桌面用户安装扩展；开发环境可手动执行：

```bash
./packaging/gnome-shell-extension/install.sh
# 注销重登，或 X11 下 Alt+F2 → r
```

## 6. 语音准备（需要通话时）

```bash
sudo ./scripts/quectel-voice-setup.sh
sudo systemctl restart ModemManager
hipi status   # 确认 audio: true
```

在 HiPi「状态」页点击「配置通话音频」。

## 7. 首次向导

```bash
hipi ui
```

完成：模组检测 → PIN → 网络注册 → 音频 → 可选测试短信。

## 8. 功能验收

详细勾选项见 [device-checklist.md](device-checklist.md)。核心命令：

```bash
hipi status
hipi send-sms <号码> "HiPi测试"
hipi dial <号码>
hipi hangup
hipi sync
```

## 9. 常见问题

| 现象 | 处理 |
|------|------|
| 无模组 | `lsusb \| grep -i quectel`、`systemctl status ModemManager` |
| daemon 未运行 | `systemctl --user restart hipi-daemon` |
| 有数据无语音 | `scripts/quectel-voice-setup.sh`、检查 ALSA 卡 |
| Webhook 验签失败 | [webhook.md](webhook.md) |

完整排障：[troubleshooting.md](troubleshooting.md)

## 10. 日志

```bash
journalctl --user -u hipi-daemon -f
./scripts/modem-probe.sh | python3 -m json.tool
```
