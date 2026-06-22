# HiPi 从零到一使用指南

本文档面向 **Orange Pi 6 Plus + Ubuntu 24.04 Desktop + Quectel EC801E-CN**，从买齐硬件到收发第一条短信、打通第一通电话，按顺序操作即可。

---

## 你需要准备什么

| 物品 | 说明 |
|------|------|
| Orange Pi 6 Plus | 建议 32GB RAM 版 |
| 官方 Ubuntu Desktop 镜像 | `Orangepi6plus_*_ubuntu_noble_desktop_gnome` |
| TF 卡 + 读卡器 | 刷系统用 |
| Quectel EC801E-CN | USB 一体化 4G 模组（VID `2c7c`） |
| SIM 卡 | **必须含语音 + 短信**，非纯物联网数据卡 |
| 显示器 / 键鼠 | 首次配置桌面 |

---

## 第一步：刷机并进入桌面

1. 从 Orange Pi 官网下载 **Ubuntu 24.04 Desktop GNOME** 镜像。
2. 用 `dd` 或 balenaEtcher 写入 TF 卡。
3. 插卡上电，完成 Ubuntu 首次用户创建并登录桌面。
4. 连接 Wi‑Fi 或有线网络（安装依赖时需要）。

---

## 第二步：准备 SIM 与模组

1. **关机或拔掉 USB** 后，将 SIM 插入 EC801E 卡槽（注意 Nano/Micro 尺寸）。
2. 确认 SIM 已在运营商侧 **实名激活**，套餐含短信与语音。
3. 将 EC801E 插入 Orange Pi **USB 3.0 HOST 口**（供电更稳）。
4. 开机登录后，先确认系统能看到模组：

```bash
lsusb | grep -i quectel          # 应看到 2c7c
systemctl status ModemManager    # 应为 active
mmcli -L                         # 应列出 /org/freedesktop/ModemManager1/Modem/0
```

若 `lsusb` 无 Quectel，换 USB 口或带供电的 Hub。详见 [hardware.md](hardware.md)。

---

## 第三步：安装 HiPi

任选一种方式。

### 方式 A：一键安装脚本（推荐）

在 Orange Pi 上：

```bash
git clone https://github.com/flygoly/hipi.git
cd hipi
chmod +x scripts/install-orangepi.sh
./scripts/install-orangepi.sh
```

脚本会：安装系统依赖 → 本地构建 `.deb` → `dpkg -i` → 启用 `hipi-daemon`。

**完成后注销并重新登录**（加入 `dialout` / `plugdev` 组）。

### 方式 B：手动打 deb 包

```bash
git clone https://github.com/flygoly/hipi.git
cd hipi

sudo apt update
sudo apt install -y python3-pip python3-venv git \
  python3-gi python3-dbus modemmanager network-manager \
  pipewire pipewire-pulse libqmi-utils gir1.2-glib-2.0

chmod +x packaging/debian/build-deb.sh
./packaging/debian/build-deb.sh 0.1.0
sudo dpkg -i build/debian/hipi_0.1.0_arm64.deb
sudo apt install -f -y    # 若提示缺依赖

# 注销并重新登录
```

`postinst` 会自动：

- `systemctl --user enable --now hipi-daemon`
- 安装 GNOME 顶栏扩展
- `loginctl enable-linger`（注销后守护进程仍可运行）

### 方式 C：开发安装（改代码 / 跑测试）

```bash
git clone https://github.com/flygoly/hipi.git
cd hipi

sudo apt install -y python3-pip python3-venv python3-gi python3-dbus \
  modemmanager network-manager pipewire pipewire-pulse \
  libqmi-utils gir1.2-glib-2.0

pip install -e ".[dev]"
sudo ./scripts/install-system-policy.sh   # D-Bus / Polkit 权限，必做
# 注销重登后加入 dialout/plugdev
systemctl --user enable --now hipi-daemon
```

---

## 第四步：验证安装

```bash
# 守护进程
hipi ping                    # {"pong": true}
systemctl --user status hipi-daemon

# 模组与信号
hipi status                  # modem_present: true，有运营商与信号

# 自动化预检
chmod +x scripts/device-verify.sh scripts/run-tests.sh
./scripts/device-verify.sh
```

期望结果：

- `hipi ping` 成功
- `hipi status` 中 `modem_present: true`
- `signal_quality` > 0，`sim_locked: false`（或下一步解锁 PIN）

若 SIM 有 PIN：

```bash
hipi unlock 1234
```

---

## 第五步：首次启动与向导

```bash
hipi ui
```

或从应用菜单打开 **HiPi**。首次运行会进入设置向导：

1. **模组检测** — 确认 EC801E 被识别
2. **SIM 解锁** — 若已用 CLI 解锁可跳过
3. **网络注册** — 等待 `registered` / `connected`
4. **通话音频** — 点击「检测音频」；需要语音时运行下方脚本
5. **测试短信** — 可选，向另一号码发一条测试

---

## 第六步：验证短信（必做）

### 发送

```bash
hipi send-sms 13800138000 "HiPi 测试"
```

或在 UI「消息」页选择会话发送。对方手机应收到短信。

### 接收

用另一部手机向本机 SIM 号码发短信，然后：

```bash
hipi sync                      # 从模组同步收件箱
hipi list-conversations        # 查看会话与未读
```

或在 UI「消息」页查看，桌面会弹出通知。

### 冒烟脚本（可选）

```bash
export HIPI_SMOKE_NUMBER=你的测试号码
./scripts/device-verify.sh --smoke
```

---

## 第七步：验证语音（需要通话时）

### 准备音频

```bash
sudo ./scripts/quectel-voice-setup.sh
sudo systemctl restart ModemManager
hipi setup-audio
hipi status    # 确认 "audio": true
```

在 UI「状态」页也可点击「配置通话音频」。

### 拨打与接听

```bash
hipi dial 13800138000    # 主叫
hipi hangup              # 挂断
```

或在 UI「电话」页使用拨号盘。来电时会有弹窗，可接听 / 拒接。

---

## 第八步：日常使用

| 场景 | 操作 |
|------|------|
| 打开应用 | 菜单 **HiPi** 或 `hipi ui` |
| 看信号 / 运营商 | 窗口标题、托盘、GNOME 顶栏扩展 |
| 管理联系人 | UI「联系人」；支持 vCard 导入导出 |
| 短信转发 | UI「状态」→ 配置号码 / Webhook |
| 导出记录 | UI「状态」→ 导出 CSV |
| 同步历史短信 | UI「状态」→「同步模组短信」或 `hipi sync` |

### 常用 CLI

```bash
hipi status
hipi ping
hipi unlock <PIN>
hipi send-sms <号码> "内容"
hipi list-conversations
hipi dial <号码>
hipi hangup
hipi sync
hipi list-calls
hipi list-contacts
hipi setup-audio
```

---

## 第九步：可选功能

### GNOME 顶栏扩展

`.deb` 安装已自动配置。开发环境手动安装：

```bash
./packaging/gnome-shell-extension/install.sh
# 注销重登
```

顶栏显示运营商、信号、未读数；左键打开 HiPi，中键刷新。

### Webhook 短信转发

UI「状态」→ 填写 Webhook URL 与签名密钥。服务端验签见 [webhook.md](webhook.md)。

### 本地测试 Webhook

```bash
export HIPI_WEBHOOK_SECRET=test-secret
python3 scripts/webhook-receiver.py --port 8765
```

---

## 验收清单

完整勾选项见 [device-checklist.md](device-checklist.md)。核心通过标准：

- [ ] `hipi status` 有模组、有信号
- [ ] 能发出短信且对方收到
- [ ] 能收到短信并在 UI 显示
- [ ] （可选）能主叫 / 被叫且双向有声音

---

## 常见问题

| 现象 | 处理 |
|------|------|
| `hipi: command not found` | 重开终端；确认 deb 已安装 |
| `HiPi daemon is not running` | `systemctl --user start hipi-daemon` |
| 无模组 | 换 USB 3.0 口；`systemctl restart ModemManager` |
| SIM 锁定 | `hipi unlock <PIN>` |
| 有信号不能发短信 | 确认非纯数据卡；见 [troubleshooting.md](troubleshooting.md) |
| 有数据不能打电话 | `sudo ./scripts/quectel-voice-setup.sh` |
| 中文短信乱码 | 更新到最新 HiPi（使用 smspdudecoder 解码） |

---

## 日志与诊断

```bash
journalctl --user -u hipi-daemon -f
cat ~/.local/share/hipi/daemon-start.log    # UI 自动拉起失败时
./scripts/modem-probe.sh | python3 -m json.tool
./scripts/run-hardware-tests.sh             # 需 pytest + 真机
```

更多排障：[troubleshooting.md](troubleshooting.md)

---

## 架构一览

```
hipi ui (PySide6)  ←RPC→  hipi-daemon  ←D-Bus→  ModemManager  ←USB→  EC801E
                              ↓
                           SQLite
```

- **hipi-daemon**：后台服务，负责模组、短信、通话、数据库
- **hipi ui**：桌面界面，也可单独用 CLI 操作

---

## 下一步

- 硬件细节：[hardware.md](hardware.md)
- Webhook 集成：[webhook.md](webhook.md)
- 参与开发：`pip install -e ".[dev]"` 后运行 `./scripts/run-tests.sh`
