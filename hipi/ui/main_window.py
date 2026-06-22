"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget

from hipi.contacts import contact_display_name
from hipi.daemon.rpc_client import RpcError
from hipi.ui.contacts.page import ContactsPage
from hipi.ui.icon import app_icon
from hipi.ui.phone.page import PhonePage
from hipi.ui.rpc_client import RpcEventClient
from hipi.ui.sms.page import SmsPage
from hipi.ui.status_page import StatusPage


class MainWindow(QMainWindow):
    modem_status_changed = Signal(dict)

    def __init__(self, rpc: RpcEventClient) -> None:
        super().__init__()
        self.rpc = rpc
        self.setWindowTitle("HiPi")
        self.setWindowIcon(app_icon())
        self.resize(900, 640)

        self.tabs = QTabWidget()
        self.sms_page = SmsPage(rpc)
        self.phone_page = PhonePage(rpc)
        self.contacts_page = ContactsPage(rpc)
        self.status_page = StatusPage(rpc)

        self.tabs.addTab(self.sms_page, "消息")
        self.tabs.addTab(self.phone_page, "电话")
        self.tabs.addTab(self.contacts_page, "联系人")
        self.tabs.addTab(self.status_page, "状态")

        self.contacts_page.dial_requested.connect(self._dial_contact)
        self.contacts_page.message_requested.connect(self._message_contact)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("正在连接模组…")

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.refresh_modem_status)
        self._status_timer.start(15000)

        self.rpc.event_received.connect(self._on_event)
        self.refresh_all()
        self.refresh_modem_status()

    def _dial_contact(self, number: str) -> None:
        self.tabs.setCurrentWidget(self.phone_page)
        self.phone_page.dial_number(number)

    def _message_contact(self, number: str) -> None:
        self.tabs.setCurrentWidget(self.sms_page)
        self.sms_page.thread.show_peer(number)

    def refresh_modem_status(self) -> None:
        try:
            status = self.rpc.call("get_status")
        except RpcError:
            self.status_bar.showMessage("后台服务未连接")
            return

        if not status.get("modem_present"):
            self.setWindowTitle("HiPi — 无模组")
            self.status_bar.showMessage("未检测到 4G 模组")
            self.modem_status_changed.emit(status)
            return

        m = status["modem"]
        signal_q = m.get("signal_quality", 0)
        operator = m.get("operator_name") or m.get("operator_code") or "未知运营商"
        state = m.get("state", "unknown")
        title = f"HiPi — {operator} {signal_q}%"
        self.setWindowTitle(title)
        self.status_bar.showMessage(f"{operator} | 信号 {signal_q}% | {state}")
        self.modem_status_changed.emit(status)

    def refresh_all(self) -> None:
        self.sms_page.refresh()
        self.phone_page.refresh()
        self.contacts_page.refresh()
        self.status_page.refresh()

    def _on_event(self, event: str, payload: dict) -> None:
        self.sms_page.on_event(event, payload)
        self.phone_page.on_event(event, payload)
        if event in ("new_message", "incoming_call"):
            self.refresh_modem_status()
        if event == "new_message":
            from hipi.ui.notifications import notify

            peer = payload.get("peer", "")
            label = contact_display_name(peer, payload.get("name"))
            notify("新短信", f"{label}: {payload.get('body', '')[:80]}")
        elif event == "incoming_call":
            from hipi.ui.notifications import notify

            call = payload.get("call", {})
            peer = call.get("peer", "未知号码")
            label = contact_display_name(peer, call.get("name"))
            notify("来电", label, urgency="critical")
