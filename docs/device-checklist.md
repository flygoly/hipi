# EC801E 真机验证清单

在 Orange Pi 6 Plus 上完成 HiPi 安装后，按本清单逐项验证。自动化预检可运行：

```bash
chmod +x scripts/device-verify.sh scripts/run-tests.sh
./scripts/run-tests.sh          # 本地单元测试（开发机 / Orange Pi 均可）
./scripts/device-verify.sh      # 硬件与守护进程预检
```

## 环境准备

- [ ] 官方 Ubuntu Desktop GNOME 镜像（Noble 24.04）
- [ ] EC801E-CN 插入 **USB 3.0 HOST** 口
- [ ] SIM 已开通**语音 + 短信**（非纯数据卡）
- [ ] 用户已在 `dialout`、`plugdev` 组（安装 `.deb` 后重新登录）

```bash
groups | grep -E 'dialout|plugdev'
```

## 系统与守护进程

- [ ] `ModemManager` 运行中：`systemctl is-active ModemManager`
- [ ] `hipi-daemon` 用户服务已启用：`systemctl --user is-active hipi-daemon`
- [ ] `hipi status` 返回 `modem_present: true`
- [ ] GNOME 顶栏 HiPi 扩展显示运营商与信号（可选）

```bash
hipi status
cat "$XDG_RUNTIME_DIR/hipi-status.json" | python3 -m json.tool
```

## 模组与网络注册

- [ ] `lsusb` 可见 Quectel（VID `2c7c`）
- [ ] `mmcli -L` 列出至少一个 modem
- [ ] 信号强度 > 0%，已注册运营商
- [ ] 若 SIM 锁定：`hipi unlock <PIN>` 成功

## 短信

- [ ] **发送**：`hipi send-sms <号码> "HiPi测试"` 成功，对方收到
- [ ] **中文**：发送与接收含中文、标点、数字的短信，UI 显示正常
- [ ] **接收**：向本机号码发短信，HiPi 会话列表出现新消息，未读角标更新
- [ ] **搜索**：在消息页按号码或内容搜索能找到记录
- [ ] **同步**：「状态」→「同步模组短信」不重复刷历史通知

## 语音通话

- [ ] `/proc/asound/cards` 含 Quectel 或 UAC 音频设备
- [ ] 「状态」→「配置通话音频」无报错
- [ ] **主叫**：拨号盘拨打手机号，状态由拨打中 → 通话中 → 挂断
- [ ] **被叫**：来电弹窗可接听/拒接，双向能听清
- [ ] 通话记录写入「电话」页历史

若仅有数据无语音，运行 `sudo ./scripts/quectel-voice-setup.sh` 并参阅 [故障排除](troubleshooting.md)。

## 联系人与转发（可选）

- [ ] 添加联系人后，会话/通话显示姓名
- [ ] vCard 导入：同号码合并更新姓名
- [ ] 短信转发到另一号码：`[HiPi转发]` 前缀正确
- [ ] Webhook：配置 URL + 密钥，`scripts/webhook-receiver.py` 收到 JSON 且验签通过

## 数据导出

- [ ] 「状态」导出短信/通话 CSV，Excel 打开中文不乱码（UTF-8 BOM）
- [ ] 勾选日期范围后仅导出区间内记录

## 记录模板

| 项目 | 日期 | 运营商 | 结果 | 备注 |
|------|------|--------|------|------|
| 短信中文收发 | | | ☐ 通过 | |
| 主叫语音 | | | ☐ 通过 | |
| 被叫语音 | | | ☐ 通过 | |
| Webhook 验签 | | | ☐ 通过 | |

## 诊断命令汇总

```bash
./scripts/modem-probe.sh | python3 -m json.tool
journalctl --user -u hipi-daemon -n 50 --no-pager
mmcli -m 0
```
