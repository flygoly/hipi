"""Local contacts management."""

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


class ContactsPage(QWidget):
    dial_requested = Signal(str)
    message_requested = Signal(str)

    def __init__(self, rpc: RpcEventClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rpc = rpc
        self._selected_id: int | None = None

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索联系人…")
        self.search.textChanged.connect(self.refresh)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_select)

        self.name = QLineEdit()
        self.name.setPlaceholderText("姓名")
        self.number = QLineEdit()
        self.number.setPlaceholderText("号码")
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("备注（可选）")
        self.notes.setMaximumHeight(60)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        clear_btn = QPushButton("新建")
        clear_btn.clicked.connect(self._clear_form)
        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(self._delete)
        dial_btn = QPushButton("拨打")
        dial_btn.clicked.connect(self._dial)
        sms_btn = QPushButton("发短信")
        sms_btn.clicked.connect(self._message)

        form_btns = QHBoxLayout()
        form_btns.addWidget(save_btn)
        form_btns.addWidget(clear_btn)
        form_btns.addWidget(delete_btn)

        action_btns = QHBoxLayout()
        action_btns.addWidget(dial_btn)
        action_btns.addWidget(sms_btn)

        left = QVBoxLayout()
        left.addWidget(QLabel("联系人"))
        left.addWidget(self.search)
        left.addWidget(self.list)

        right = QVBoxLayout()
        right.addWidget(QLabel("详情"))
        right.addWidget(self.name)
        right.addWidget(self.number)
        right.addWidget(self.notes)
        right.addLayout(form_btns)
        right.addLayout(action_btns)
        right.addStretch()

        layout = QHBoxLayout(self)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setMaximumWidth(280)
        right_w = QWidget()
        right_w.setLayout(right)
        layout.addWidget(left_w)
        layout.addWidget(right_w, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        query = self.search.text().strip() or None
        try:
            contacts = self.rpc.call("list_contacts", {"query": query} if query else {})
        except RpcError as exc:
            QMessageBox.warning(self, "HiPi", str(exc))
            return
        self.list.clear()
        for contact in contacts:
            label = f"{contact['name']}  {contact['number']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, contact)
            self.list.addItem(item)

    def _on_select(self, item: QListWidgetItem) -> None:
        contact = item.data(Qt.ItemDataRole.UserRole)
        self._selected_id = contact["id"]
        self.name.setText(contact["name"])
        self.number.setText(contact["number"])
        self.notes.setPlainText(contact.get("notes", ""))

    def _clear_form(self) -> None:
        self._selected_id = None
        self.name.clear()
        self.number.clear()
        self.notes.clear()
        self.list.clearSelection()

    def _save(self) -> None:
        name = self.name.text().strip()
        number = self.number.text().strip()
        notes = self.notes.toPlainText().strip()
        if not name or not number:
            QMessageBox.information(self, "HiPi", "请填写姓名和号码")
            return
        try:
            if self._selected_id:
                result = self.rpc.call(
                    "update_contact",
                    {"id": self._selected_id, "name": name, "number": number, "notes": notes},
                )
            else:
                result = self.rpc.call(
                    "add_contact", {"name": name, "number": number, "notes": notes}
                )
            if not result.get("ok"):
                QMessageBox.warning(self, "HiPi", result.get("error", "保存失败"))
                return
            if not self._selected_id and result.get("contact"):
                self._selected_id = result["contact"]["id"]
            self.refresh()
        except RpcError as exc:
            QMessageBox.warning(self, "HiPi", str(exc))

    def _delete(self) -> None:
        if not self._selected_id:
            return
        try:
            result = self.rpc.call("delete_contact", {"id": self._selected_id})
            if result.get("ok"):
                self._clear_form()
                self.refresh()
        except RpcError as exc:
            QMessageBox.warning(self, "HiPi", str(exc))

    def _dial(self) -> None:
        number = self.number.text().strip()
        if number:
            self.dial_requested.emit(number)

    def _message(self) -> None:
        number = self.number.text().strip()
        if number:
            self.message_requested.emit(number)
