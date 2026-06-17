"""Main application window."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from hipi.ui.phone.page import PhonePage
from hipi.ui.rpc_client import RpcEventClient
from hipi.ui.sms.page import SmsPage
from hipi.ui.status_page import StatusPage


class MainWindow(QMainWindow):
    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setWindowTitle("HiPi")
        self.resize(900, 640)

        self.tabs = QTabWidget()
        self.sms_page = SmsPage(rpc)
        self.phone_page = PhonePage(rpc)
        self.status_page = StatusPage(rpc)

        self.tabs.addTab(self.sms_page, "消息")
        self.tabs.addTab(self.phone_page, "电话")
        self.tabs.addTab(self.status_page, "状态")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self.rpc.event_received.connect(self._on_event)
        self.refresh_all()

    def refresh_all(self) -> None:
        self.sms_page.refresh()
        self.phone_page.refresh()
        self.status_page.refresh()

    def _on_event(self, event: str, payload: dict) -> None:
        self.sms_page.on_event(event, payload)
        self.phone_page.on_event(event, payload)
        if event == "new_message":
            from hipi.ui.notifications import notify

            notify("新短信", f"{payload.get('peer', '')}: {payload.get('body', '')[:80]}")
        elif event == "incoming_call":
            from hipi.ui.notifications import notify

            notify("来电", payload.get("call", {}).get("peer", "未知号码"), urgency="critical")
