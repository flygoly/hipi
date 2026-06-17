"""SMS conversation list and thread views."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hipi.daemon.rpc_client import RpcError
from hipi.ui.rpc_client import RpcEventClient


class ConversationList(QWidget):
    conversation_selected = Signal(str)

    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self._conversations: list[dict] = []
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索号码或内容…")
        self.search.textChanged.connect(self._apply_filter)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_click)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("会话"))
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

    def refresh(self) -> None:
        try:
            self._conversations = self.rpc.call("list_conversations")
        except RpcError as exc:
            QMessageBox.warning(self, "HiPi", str(exc))
            return
        self._apply_filter(self.search.text())

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        self.list.clear()
        for conv in self._conversations:
            peer = conv["peer"]
            body = conv.get("last_body", "") or ""
            if query and query not in peer.lower() and query not in body.lower():
                continue
            unread = conv.get("unread", 0)
            label = peer
            if unread:
                label = f"{label} ({unread})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, peer)
            item.setToolTip(body[:80])
            self.list.addItem(item)

    def _on_click(self, item: QListWidgetItem) -> None:
        peer = item.data(Qt.ItemDataRole.UserRole)
        if peer:
            self.conversation_selected.emit(peer)


class MessageThread(QWidget):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self._peer: str | None = None

        self.header = QLabel("选择会话")
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.compose = QTextEdit()
        self.compose.setPlaceholderText("输入短信内容…")
        self.compose.setMaximumHeight(80)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_message)
        self.new_btn = QPushButton("新短信")
        self.new_btn.clicked.connect(self._new_message)

        row = QHBoxLayout()
        row.addWidget(self.new_btn)
        row.addStretch()
        row.addWidget(self.send_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(self.messages)
        layout.addWidget(self.compose)
        layout.addLayout(row)

    def show_peer(self, peer: str) -> None:
        self._peer = peer
        self.header.setText(peer)
        self._load_messages()
        try:
            self.rpc.call("mark_conversation_read", {"peer": peer})
        except RpcError:
            pass

    def _new_message(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        number, ok = QInputDialog.getText(self, "新短信", "收件人号码:")
        if ok and number.strip():
            self.show_peer(number.strip())

    def _load_messages(self) -> None:
        if not self._peer:
            return
        try:
            msgs = self.rpc.call("list_messages", {"peer": self._peer, "limit": 200})
        except RpcError as exc:
            self.messages.setPlainText(str(exc))
            return
        lines = []
        for msg in reversed(msgs):
            arrow = "←" if msg["direction"] == "inbound" else "→"
            lines.append(f"{arrow} [{msg['timestamp'][:19]}] {msg['body']}")
        self.messages.setPlainText("\n".join(lines))

    def send_message(self) -> None:
        if not self._peer:
            QMessageBox.information(self, "HiPi", "请先选择或新建会话")
            return
        text = self.compose.toPlainText().strip()
        if not text:
            return
        try:
            result = self.rpc.call("send_sms", {"number": self._peer, "text": text})
            if not result.get("ok"):
                QMessageBox.warning(self, "发送失败", result.get("error", "未知错误"))
                return
            self.compose.clear()
            self._load_messages()
        except RpcError as exc:
            QMessageBox.warning(self, "发送失败", str(exc))

    def on_new_message(self, payload: dict) -> None:
        if self._peer and payload.get("peer") == self._peer:
            self._load_messages()


class SmsPage(QWidget):
    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self.conversations = ConversationList(rpc)
        self.thread = MessageThread(rpc)
        self.conversations.conversation_selected.connect(self.thread.show_peer)

        layout = QHBoxLayout(self)
        self.conversations.setMaximumWidth(260)
        layout.addWidget(self.conversations)
        layout.addWidget(self.thread, stretch=1)

    def refresh(self) -> None:
        self.conversations.refresh()
        if self.thread._peer:
            self.thread._load_messages()

    def on_event(self, event: str, payload: dict) -> None:
        if event in ("new_message", "message_updated"):
            self.conversations.refresh()
            self.thread.on_new_message(payload)
