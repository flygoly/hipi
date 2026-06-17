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

确保用户在 `dialout` 和 `plugdev` 组：

```bash
groups
sudo usermod -aG dialout,plugdev $USER
# 重新登录
```

## Orange Pi Ubuntu 镜像

建议使用官方发布的固定版本镜像进行测试，避免内核/驱动差异导致 QMI 行为不一致。
