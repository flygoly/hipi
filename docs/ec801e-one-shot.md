# EC801E 真机验收流程

> **完整 0→1 指南**请阅读 **[getting-started.md](getting-started.md)**（硬件准备、安装、短信/语音验证、日常使用）。

本文档为验收阶段的快速索引。

## 快速安装

```bash
git clone https://github.com/flygoly/hipi.git
cd hipi
./scripts/install-orangepi.sh
# 注销重登
```

## 预检

```bash
./scripts/run-tests.sh
./scripts/device-verify.sh
export HIPI_SMOKE_NUMBER=13800138000
./scripts/device-verify.sh --smoke
./scripts/device-verify.sh --hardware-tests
```

## 功能验收

详见 [device-checklist.md](device-checklist.md)。

```bash
hipi status
hipi send-sms <号码> "HiPi测试"
hipi dial <号码>
hipi hangup
```

## 日志

```bash
journalctl --user -u hipi-daemon -f
./scripts/modem-probe.sh | python3 -m json.tool
```
