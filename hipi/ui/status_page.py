"""Modem status panel."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from hipi.daemon.rpc_client import RpcError
from hipi.ui.rpc_client import RpcEventClient


class StatusPage(QWidget):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self.info = QTextEdit()
        self.info.setReadOnly(True)
        sync_btn = QPushButton("同步模组短信")
        sync_btn.clicked.connect(self._sync)
        audio_btn = QPushButton("配置通话音频")
        audio_btn.clicked.connect(self._setup_audio)
        refresh_btn = QPushButton("刷新状态")
        refresh_btn.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("模组状态"))
        layout.addWidget(self.info)
        layout.addWidget(refresh_btn)
        layout.addWidget(sync_btn)
        layout.addWidget(audio_btn)

    def refresh(self) -> None:
        try:
            status = self.rpc.call("get_status")
        except RpcError as exc:
            self.info.setPlainText(str(exc))
            return

        if not status.get("modem_present"):
            self.info.setPlainText("未检测到 4G 模组。请插入 EC801E USB 并确认 ModemManager 正在运行。")
            return

        m = status["modem"]
        lines = [
            f"制造商: {m.get('manufacturer', '')}",
            f"型号: {m.get('model', '')}",
            f"状态: {m.get('state', '')}",
            f"信号: {m.get('signal_quality', 0)}%",
            f"运营商: {m.get('operator_name', '')} ({m.get('operator_code', '')})",
            f"技术: {', '.join(m.get('access_technologies', []))}",
            f"IMEI: {m.get('imei', '')}",
            f"本机号码: {', '.join(m.get('own_numbers', [])) or '未知'}",
            f"SIM 锁定: {'是' if m.get('sim_locked') else '否'}",
            f"短信: {'支持' if m.get('messaging') else '不支持'}",
            f"语音: {'支持' if m.get('voice') else '不支持'}",
            f"通话音频设备: {'已检测' if status.get('audio') else '未检测'}",
        ]
        self.info.setPlainText("\n".join(lines))

    def _sync(self) -> None:
        try:
            self.rpc.call("sync_modem")
            self.refresh()
        except RpcError as exc:
            self.info.append(f"\n同步失败: {exc}")

    def _setup_audio(self) -> None:
        try:
            result = self.rpc.call("setup_call_audio")
            self.info.append(f"\n音频: {result}")
        except RpcError as exc:
            self.info.append(f"\n音频配置失败: {exc}")
