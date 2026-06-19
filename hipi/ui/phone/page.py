"""Phone dial pad and call history."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hipi.contacts import contact_display_name
from hipi.daemon.rpc_client import RpcError
from hipi.ui.rpc_client import RpcEventClient

DIAL_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]


class DialPad(QWidget):
    dial_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.number_label = QLabel("")
        self.number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.number_label.font()
        font.setPointSize(20)
        self.number_label.setFont(font)

        grid = QGridLayout()
        for i, key in enumerate(DIAL_KEYS):
            btn = QPushButton(key)
            btn.setMinimumSize(64, 48)
            btn.clicked.connect(lambda _=False, k=key: self._append(k))
            grid.addWidget(btn, i // 3, i % 3)

        call_btn = QPushButton("拨打")
        call_btn.setStyleSheet("background: #2e7d32; color: white;")
        call_btn.clicked.connect(self._dial)
        back_btn = QPushButton("删除")
        back_btn.clicked.connect(self._backspace)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear)

        actions = QHBoxLayout()
        actions.addWidget(back_btn)
        actions.addWidget(clear_btn)
        actions.addWidget(call_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.number_label)
        layout.addLayout(grid)
        layout.addLayout(actions)

    def _append(self, key: str) -> None:
        self.number_label.setText(self.number_label.text() + key)

    def _backspace(self) -> None:
        self.number_label.setText(self.number_label.text()[:-1])

    def _clear(self) -> None:
        self.number_label.setText("")

    def _dial(self) -> None:
        number = self.number_label.text().strip()
        if number:
            self.dial_requested.emit(number)


class CallHistory(QWidget):
    redial_requested = Signal(str)

    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_double_click)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("通话记录"))
        layout.addWidget(self.list)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

    def refresh(self) -> None:
        try:
            calls = self.rpc.call("list_calls", {"limit": 50})
        except RpcError:
            return
        self.list.clear()
        for call in calls:
            icon = {"inbound": "↓", "outbound": "↑"}.get(call["direction"], "•")
            peer = call["peer"]
            name = call.get("name")
            who = f"{name} ({peer})" if name else peer
            text = f"{icon} {who} — {call['state']} ({call['started_at'][:19]})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, peer)
            self.list.addItem(item)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        peer = item.data(Qt.ItemDataRole.UserRole)
        if peer:
            self.redial_requested.emit(peer)


class IncomingCallDialog(QWidget):
    answered = Signal(str)
    rejected = Signal(str)

    def __init__(self, call_path: str, number: str, name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.call_path = call_path
        self.number = number
        self.name = name
        self.setWindowTitle("来电")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        label = QLabel(f"来电: {contact_display_name(number, name)}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(18)
        label.setFont(font)

        answer = QPushButton("接听")
        answer.setStyleSheet("background: #2e7d32; color: white; min-height: 48px;")
        answer.clicked.connect(lambda: self.answered.emit(self.call_path))
        reject = QPushButton("拒接")
        reject.setStyleSheet("background: #c62828; color: white; min-height: 48px;")
        reject.clicked.connect(lambda: self.rejected.emit(self.call_path))

        row = QHBoxLayout()
        row.addWidget(reject)
        row.addWidget(answer)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addLayout(row)
        self.resize(360, 160)


class ActiveCallBar(QWidget):
    hangup_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("通话中")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._seconds = 0
        hangup = QPushButton("挂断")
        hangup.setStyleSheet("background: #c62828; color: white;")
        hangup.clicked.connect(self.hangup_requested.emit)
        layout = QHBoxLayout(self)
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(hangup)
        self.hide()

    def show_dialing(self, number: str) -> None:
        self.timer.stop()
        self._seconds = 0
        self.label.setText(f"正在拨打: {number}")
        self.show()

    def start(self, number: str) -> None:
        self._seconds = 0
        self.label.setText(f"通话中: {number}")
        self.timer.start(1000)
        self.show()

    def stop(self) -> None:
        self.timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._seconds += 1
        m, s = divmod(self._seconds, 60)
        parts = self.label.text().split(" — ")
        base = parts[0] if parts else "通话中"
        self.label.setText(f"{base} — {m:02d}:{s:02d}")


class PhonePage(QWidget):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self._incoming: IncomingCallDialog | None = None
        self._active_path: str | None = None
        self._pending_number: str | None = None

        self.dial_pad = DialPad()
        self.history = CallHistory(rpc)
        self.active_bar = ActiveCallBar()

        self.dial_pad.dial_requested.connect(self._dial)
        self.history.redial_requested.connect(self.dial_number)
        self.active_bar.hangup_requested.connect(self._hangup)

        left = QVBoxLayout()
        left.addWidget(self.dial_pad)
        left.addWidget(self.active_bar)

        left_w = QWidget()
        left_w.setLayout(left)

        layout = QHBoxLayout(self)
        layout.addWidget(left_w)
        layout.addWidget(self.history, stretch=1)

    def refresh(self) -> None:
        self.history.refresh()

    def dial_number(self, number: str) -> None:
        self.dial_pad.number_label.setText(number)
        self._dial(number)

    def _dial(self, number: str) -> None:
        try:
            result = self.rpc.call("dial", {"number": number})
            if not result.get("ok"):
                QMessageBox.warning(self, "拨打失败", result.get("error", ""))
                return
            self._active_path = result.get("path")
            self._pending_number = number
            self.active_bar.show_dialing(number)
            self.history.refresh()
        except RpcError as exc:
            QMessageBox.warning(self, "拨打失败", str(exc))

    def _hangup(self) -> None:
        try:
            self.rpc.call("hangup", {"path": self._active_path})
        except RpcError:
            pass
        self._active_path = None
        self.active_bar.stop()
        self.history.refresh()

    def _answer(self, call_path: str) -> None:
        try:
            result = self.rpc.call("answer", {"path": call_path})
            if result.get("ok"):
                self._active_path = call_path
                if self._incoming:
                    self._pending_number = self._incoming.number
                self.active_bar.show_dialing(self._pending_number or "来电")
            else:
                QMessageBox.warning(self, "接听失败", result.get("error", ""))
        except RpcError as exc:
            QMessageBox.warning(self, "接听失败", str(exc))
        if self._incoming:
            self._incoming.close()
            self._incoming = None

    def _reject(self, call_path: str) -> None:
        try:
            self.rpc.call("hangup", {"path": call_path})
        except RpcError:
            pass
        if self._incoming:
            self._incoming.close()
            self._incoming = None

    def on_event(self, event: str, payload: dict) -> None:
        if event == "incoming_call":
            call = payload.get("call", {})
            path = payload.get("path", "")
            number = call.get("peer", "未知号码")
            name = call.get("name")
            if self._incoming:
                self._incoming.close()
            self._incoming = IncomingCallDialog(path, number, name, self.window())
            self._incoming.answered.connect(self._answer)
            self._incoming.rejected.connect(self._reject)
            self._incoming.show()
        elif event == "call_started":
            call = payload.get("call", {})
            self._active_path = payload.get("path")
            number = call.get("peer") or self._pending_number or "未知号码"
            self.active_bar.show_dialing(number)
        elif event == "call_state":
            state = payload.get("state")
            if state == "active":
                if self._incoming:
                    self._incoming.close()
                    self._incoming = None
                number = self._pending_number or "通话中"
                self.active_bar.start(number)
            elif state in ("ringing-out", "dialing"):
                if self._pending_number:
                    self.active_bar.show_dialing(self._pending_number)
            elif state == "terminated":
                self._active_path = None
                self._pending_number = None
                self.active_bar.stop()
                self.history.refresh()
