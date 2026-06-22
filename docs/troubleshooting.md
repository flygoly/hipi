# HiPi 故障排除

## 模组未被识别

```bash
dmesg | tail -50
lsusb
systemctl status ModemManager
```

确认内核加载 `qmi_wwan`、`option` 模块。Quectel VID 为 `2c7c`。

## SIM PIN 锁定

```bash
hipi unlock <PIN>
# 或
mmcli -i 0 --pin=<PIN>
```

## EC801E ECM / AT 短信

EC801E 固件通常仅支持 ECM（`usbnet` 1），HiPi 通过 AT 串口收发短息，**无需切换 QMI**。

```bash
hipi status    # sms_backend: "at", at_port: "/dev/ttyUSB..."
sudo ./scripts/setup-quectel-ec801e.sh   # 若 AT 口缺失
systemctl --user restart hipi-daemon
```

固定 AT 口：`echo /dev/ttyUSB2 > ~/.config/hipi/at_port`

## 4G 模式下短信发送失败

部分运营商在 VoLTE/IMS 下短信行为异常。尝试：

```bash
sudo ./scripts/quectel-voice-setup.sh
sudo systemctl restart ModemManager
mmcli -m 0 --command='AT+QCFG="ims"'
```

若仍失败，可联系运营商确认卡是否支持 CS 域短信，或查阅 Quectel 文档调整 `sms_domain_pref`。

## 有数据无语音

1. 检查音频设备：`cat /proc/asound/cards | grep -i quectel`
2. 在 HiPi「状态」页点击「配置通话音频」
3. 确认 SIM 已开通语音；EC801E 变体需支持音频接口
4. 运行 `scripts/quectel-voice-setup.sh`

## HiPi 守护进程未运行

```bash
systemctl --user enable --now hipi-daemon
# 或
hipi-daemon &
hipi status
```

## 权限问题

### D-Bus AccessDenied（hipi-daemon 崩溃或 hipi status 无模组）

开发安装（`pip install -e`）**不会**自动配置 ModemManager 的 D-Bus / Polkit 权限。若日志出现：

```
org.freedesktop.DBus.Error.AccessDenied: ... GetManagedObjects
```

执行：

```bash
sudo ./scripts/install-system-policy.sh
# 注销并重新登录
systemctl --user restart hipi-daemon
hipi status
```

`.deb` 安装已包含策略文件；若仍报错，可再运行上述脚本。

### dialout / plugdev 组

确保用户在 `dialout` 和 `plugdev` 组：

```bash
groups
sudo usermod -aG dialout,plugdev $USER
# 重新登录
```

## Webhook 转发验签失败

参阅 [Webhook 文档](webhook.md)：使用**原始请求体**验签，检查系统时间同步，确认密钥与 `X-HiPi-Timestamp` / `X-HiPi-Signature` 头（大小写不敏感）。

本地测试：

```bash
export HIPI_WEBHOOK_SECRET=test-secret
python3 scripts/webhook-receiver.py --port 8765
```

## 真机验收

完整清单见 [device-checklist.md](device-checklist.md)。快速预检：

```bash
./scripts/device-verify.sh
./scripts/run-tests.sh
```

## Orange Pi Ubuntu 镜像

建议使用官方发布的固定版本镜像进行测试，避免内核/驱动差异导致 QMI 行为不一致。
