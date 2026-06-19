"""First-run setup wizard."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from hipi.daemon.rpc_client import RpcError
from hipi.ui.rpc_client import RpcEventClient


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("欢迎使用 HiPi")
        self.setSubTitle("4G 短信与通话 — Orange Pi + Quectel EC801E")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "请确保：\n"
                "• EC801E USB 模组已插入 Orange Pi USB 3.0 口\n"
                "• SIM 卡已插入模组\n"
                "• ModemManager 服务正在运行"
            )
        )


class ModemDetectPage(QWizardPage):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setTitle("检测模组")
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.detect_btn = QPushButton("检测")
        self.detect_btn.clicked.connect(self._detect)
        layout = QVBoxLayout(self)
        layout.addWidget(self.output)
        layout.addWidget(self.detect_btn)
        self._detected = False

    def _detect(self) -> None:
        try:
            status = self.rpc.call("get_status")
        except RpcError as exc:
            self.output.setPlainText(f"错误: {exc}")
            self._detected = False
            return
        if not status.get("modem_present"):
            self.output.setPlainText("未检测到模组。请检查 USB 连接后重试。")
            self._detected = False
            return
        m = status["modem"]
        self.output.setPlainText(
            f"已识别: {m.get('manufacturer')} {m.get('model')}\n"
            f"状态: {m.get('state')}\n"
            f"信号: {m.get('signal_quality')}%"
        )
        self._detected = True

    def isComplete(self) -> bool:
        return self._detected


class SimUnlockPage(QWizardPage):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setTitle("SIM 卡解锁")
        self.setSubTitle("如 SIM 未设 PIN 可跳过")
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText("PIN（可选）")
        unlock_btn = QPushButton("解锁")
        unlock_btn.clicked.connect(self._unlock)
        skip_btn = QPushButton("跳过")
        skip_btn.clicked.connect(self._skip)
        row = QHBoxLayout()
        row.addWidget(unlock_btn)
        row.addWidget(skip_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.pin_input)
        layout.addLayout(row)
        self._done = False

    def _unlock(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        try:
            result = self.rpc.call("unlock_sim", {"pin": pin})
            if result.get("ok"):
                self._done = True
                self.completeChanged.emit()
            else:
                QMessageBox.warning(self, "解锁失败", result.get("error", ""))
        except RpcError as exc:
            QMessageBox.warning(self, "解锁失败", str(exc))

    def _skip(self) -> None:
        self._done = True
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done


class NetworkPage(QWizardPage):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setTitle("等待网络注册")
        self.status_label = QLabel("正在检查…")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        self._registered = False

    def initializePage(self) -> None:
        self.timer.start(2000)
        self._check()

    def cleanupPage(self) -> None:
        self.timer.stop()

    def _check(self) -> None:
        try:
            status = self.rpc.call("get_status")
            state = status.get("modem", {}).get("state", "")
            self.status_label.setText(f"当前状态: {state}")
            if state in ("registered", "connected", "enabled"):
                self._registered = True
                self.completeChanged.emit()
                self.timer.stop()
        except RpcError as exc:
            self.status_label.setText(str(exc))

    def isComplete(self) -> bool:
        return self._registered


class AudioPage(QWizardPage):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setTitle("通话音频")
        self.setSubTitle("检测 EC801E 是否暴露音频设备（语音通话需要）")
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        check_btn = QPushButton("检测音频")
        check_btn.clicked.connect(self._check)
        setup_btn = QPushButton("配置音频路由")
        setup_btn.clicked.connect(self._setup)
        skip_btn = QPushButton("跳过")
        skip_btn.clicked.connect(self._skip)
        row = QHBoxLayout()
        row.addWidget(check_btn)
        row.addWidget(setup_btn)
        row.addWidget(skip_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.output)
        layout.addLayout(row)
        self._done = False

    def initializePage(self) -> None:
        self._check()

    def _check(self) -> None:
        try:
            status = self.rpc.call("get_status")
        except RpcError as exc:
            self.output.setPlainText(str(exc))
            return
        has_audio = status.get("audio", False)
        voice = status.get("modem", {}).get("voice", False)
        lines = [
            f"模组语音能力: {'支持' if voice else '不支持或未注册'}",
            f"系统音频设备: {'已检测' if has_audio else '未检测'}",
        ]
        if not has_audio:
            lines.append(
                "\n若仅支持短信，可跳过此步。\n"
                "若需通话，请确认 EC801E 音频变体，并运行 scripts/quectel-voice-setup.sh"
            )
        self.output.setPlainText("\n".join(lines))
        if has_audio or not voice:
            self._done = True
            self.completeChanged.emit()

    def _setup(self) -> None:
        try:
            result = self.rpc.call("setup_call_audio")
            self.output.append(f"\n配置结果: {result}")
            if result.get("ok"):
                self._done = True
                self.completeChanged.emit()
        except RpcError as exc:
            self.output.append(f"\n配置失败: {exc}")

    def _skip(self) -> None:
        self._done = True
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done


class TestPage(QWizardPage):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setTitle("完成")
        self.setSubTitle("可选：发送测试短信验证功能")
        self.number = QLineEdit()
        self.number.setPlaceholderText("测试号码（可选）")
        self.text = QLineEdit()
        self.text.setPlaceholderText("测试内容")
        send_btn = QPushButton("发送测试短信")
        send_btn.clicked.connect(self._send_test)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("点击「完成」结束向导，或发送测试短信。"))
        layout.addWidget(self.number)
        layout.addWidget(self.text)
        layout.addWidget(send_btn)

    def _send_test(self) -> None:
        number = self.number.text().strip()
        text = self.text.text().strip() or "HiPi 测试"
        if not number:
            return
        try:
            result = self.rpc.call("send_sms", {"number": number, "text": text})
            if result.get("ok"):
                QMessageBox.information(self, "HiPi", "测试短信已发送")
            else:
                QMessageBox.warning(self, "HiPi", result.get("error", "发送失败"))
        except RpcError as exc:
            QMessageBox.warning(self, "HiPi", str(exc))


class OnboardingWizard(QWizard):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self.setWindowTitle("HiPi 设置向导")
        self.addPage(WelcomePage())
        self.addPage(ModemDetectPage(rpc))
        self.addPage(SimUnlockPage(rpc))
        self.addPage(NetworkPage(rpc))
        self.addPage(AudioPage(rpc))
        self.addPage(TestPage(rpc))
        self.finished.connect(self._on_finished)

    def _on_finished(self, result: int) -> None:
        if result == QWizard.DialogCode.Accepted:
            try:
                self.rpc.call("complete_onboarding")
            except RpcError:
                pass
