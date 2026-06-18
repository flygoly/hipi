"""Modem status panel and SMS forward settings."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from hipi.daemon.rpc_client import RpcError
from hipi.ui.rpc_client import RpcEventClient


class StatusPage(QWidget):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self.info = QTextEdit()
        self.info.setReadOnly(True)

        self.forward_enabled = QCheckBox("启用短信转发（仅纯文本，不含彩信）")
        self.forward_target = QLineEdit()
        self.forward_target.setPlaceholderText("转发目标号码（可选）")
        self.forward_webhook = QLineEdit()
        self.forward_webhook.setPlaceholderText("Webhook URL（可选，POST JSON）")
        self.forward_secret = QLineEdit()
        self.forward_secret.setPlaceholderText("Webhook 签名密钥（可选，HMAC-SHA256）")
        self.forward_secret.setEchoMode(QLineEdit.EchoMode.Password)
        forward_save = QPushButton("保存转发设置")
        forward_save.clicked.connect(self._save_forward)

        forward_box = QGroupBox("短信转发")
        fb_layout = QVBoxLayout(forward_box)
        fb_layout.addWidget(self.forward_enabled)
        fb_layout.addWidget(self.forward_target)
        fb_layout.addWidget(self.forward_webhook)
        fb_layout.addWidget(self.forward_secret)
        fb_layout.addWidget(
            QLabel(
                "Webhook 签名头：X-HiPi-Timestamp、X-HiPi-Signature (sha256=…)。"
                "留空密钥则不签名。"
            )
        )
        fb_layout.addWidget(
            QLabel("收到新短信时转发到号码和/或 Webhook。号码转发带 [HiPi转发] 前缀。")
        )
        fb_layout.addWidget(forward_save)

        export_box = QGroupBox("数据导出")
        ex_layout = QVBoxLayout(export_box)
        self.export_date_filter = QCheckBox("按日期范围导出")
        date_row = QHBoxLayout()
        self.export_since = QDateEdit()
        self.export_since.setCalendarPopup(True)
        self.export_since.setDisplayFormat("yyyy-MM-dd")
        self.export_since.setDate(QDate.currentDate().addMonths(-1))
        self.export_until = QDateEdit()
        self.export_until.setCalendarPopup(True)
        self.export_until.setDisplayFormat("yyyy-MM-dd")
        self.export_until.setDate(QDate.currentDate())
        date_row.addWidget(QLabel("从"))
        date_row.addWidget(self.export_since)
        date_row.addWidget(QLabel("到"))
        date_row.addWidget(self.export_until)
        ex_layout.addWidget(self.export_date_filter)
        ex_layout.addLayout(date_row)
        btn_row = QHBoxLayout()
        export_sms = QPushButton("导出短信 CSV")
        export_sms.clicked.connect(self._export_messages)
        export_calls = QPushButton("导出通话 CSV")
        export_calls.clicked.connect(self._export_calls)
        btn_row.addWidget(export_sms)
        btn_row.addWidget(export_calls)
        ex_layout.addLayout(btn_row)

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
        layout.addWidget(forward_box)
        layout.addWidget(export_box)

        self._load_forward()

    def _load_forward(self) -> None:
        try:
            cfg = self.rpc.call("get_sms_forward")
            self.forward_enabled.setChecked(cfg.get("enabled", False))
            self.forward_target.setText(cfg.get("target", ""))
            self.forward_webhook.setText(cfg.get("webhook", ""))
            if cfg.get("webhook_secret_set"):
                self.forward_secret.setPlaceholderText("已设置（留空不修改，输入新值覆盖）")
        except RpcError:
            pass

    def _save_forward(self) -> None:
        try:
            params: dict = {
                "enabled": self.forward_enabled.isChecked(),
                "target": self.forward_target.text().strip(),
                "webhook": self.forward_webhook.text().strip(),
            }
            secret = self.forward_secret.text()
            if secret:
                params["webhook_secret"] = secret
            result = self.rpc.call("set_sms_forward", params)
            if not result.get("ok"):
                self.info.append(f"\n转发设置失败: {result.get('error')}")
            else:
                self.info.append("\n短信转发设置已保存")
        except RpcError as exc:
            self.info.append(f"\n转发设置失败: {exc}")

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

    def _export_params(self) -> dict:
        params: dict = {}
        if self.export_date_filter.isChecked():
            params["since"] = self.export_since.date().toString("yyyy-MM-dd")
            params["until"] = self.export_until.date().toString("yyyy-MM-dd")
        return params

    def _export_messages(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出短信", "hipi-messages.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            result = self.rpc.call("export_messages_csv", self._export_params())
            if not result.get("ok"):
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(result.get("csv", ""))
            self.info.append(f"\n短信已导出到 {path}")
        except (RpcError, OSError) as exc:
            self.info.append(f"\n导出失败: {exc}")

    def _export_calls(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出通话记录", "hipi-calls.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            result = self.rpc.call("export_calls_csv", self._export_params())
            if not result.get("ok"):
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(result.get("csv", ""))
            self.info.append(f"\n通话记录已导出到 {path}")
        except (RpcError, OSError) as exc:
            self.info.append(f"\n导出失败: {exc}")
