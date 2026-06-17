# HiPi 硬件说明

## 目标平台

- **单板**: Orange Pi 6 Plus（32GB RAM 推荐）
- **系统**: 官方 Ubuntu Desktop 镜像（`Orangepi6plus_*_ubuntu_noble_desktop_gnome`）
- **模组**: Quectel **EC801E-CN** 一体化 USB 棒（USB 公头直插）

## 连接方式

1. 将 SIM 卡插入 EC801E 卡槽
2. 将 EC801E USB 插入 Orange Pi **USB 3.0 HOST** 口（供电更稳定）
3. 可选：3.5mm 耳机/麦克风用于通话音频（取决于模组是否暴露 UAC/模拟音频）

## 供电注意

EC801E 峰值电流约 2A。若出现频繁 `usb disconnect`：

- 换用 USB 3.0 口或带独立供电的 USB Hub
- 可选内核参数：`usbcore.autosuspend=-1`

## 验证

```bash
# 应看到 Quectel (2c7c)
lsusb | grep -i quectel

# ModemManager 应识别模组
mmcli -L

# HiPi 诊断
./scripts/modem-probe.sh
```

## 推荐测试 SIM

- 中国移动 / 中国电信各一张
- 确认已开通语音与短信功能（非纯数据卡）
