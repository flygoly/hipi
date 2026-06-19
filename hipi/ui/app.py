"""HiPi Qt application entry."""

from __future__ import annotations

import sys

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from hipi.config import ensure_dirs
from hipi.daemon.rpc_client import RpcError
from hipi.ui.main_window import MainWindow
from hipi.ui.rpc_client import DaemonStarter, RpcEventClient
from hipi.ui.setup.wizard import OnboardingWizard


def run_app() -> int:
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("HiPi")
    app.setQuitOnLastWindowClosed(False)

    rpc = RpcEventClient()

    if not _ensure_daemon(rpc):
        return 1

    rpc.start()

    window = MainWindow(rpc)
    tray = _setup_tray(app, window, rpc)
    rpc.connection_lost.connect(lambda: _on_daemon_lost(tray, rpc))

    if _needs_onboarding(rpc):
        wizard = OnboardingWizard(rpc, window)
        wizard.exec()

    window.show()
    return app.exec()


def _ensure_daemon(rpc: RpcEventClient) -> bool:
    try:
        rpc.call("ping")
        return True
    except RpcError:
        pass

    starter = DaemonStarter()
    loop = __import__("PySide6.QtCore", fromlist=["QEventLoop"]).QEventLoop()
    ok = {"done": False, "error": ""}

    def on_ok():
        ok["done"] = True
        loop.quit()

    def on_fail(msg: str):
        ok["error"] = msg
        loop.quit()

    starter.started_ok.connect(on_ok)
    starter.failed.connect(on_fail)
    starter.start()
    loop.exec()

    if ok["done"]:
        return True

    QMessageBox.critical(
        None,
        "HiPi",
        f"无法启动后台服务: {ok['error']}\n请手动运行: hipi-daemon",
    )
    return False


def _needs_onboarding(rpc: RpcEventClient) -> bool:
    try:
        result = rpc.call("get_onboarding")
        return not result.get("complete", False)
    except RpcError:
        return True


def _on_daemon_lost(tray: QSystemTrayIcon | None, rpc: RpcEventClient) -> None:
    if tray:
        tray.showMessage(
            "HiPi",
            "与后台服务断开，正在重连…",
            QSystemTrayIcon.MessageIcon.Warning,
            4000,
        )
    if not rpc._thread or not rpc._thread.is_alive():
        rpc.start()


def _update_tray_status(tray: QSystemTrayIcon, status: dict) -> None:
    if not status.get("modem_present"):
        tray.setToolTip("HiPi — 无模组")
        return
    m = status["modem"]
    signal_q = m.get("signal_quality", 0)
    operator = m.get("operator_name") or m.get("operator_code") or "未知"
    audio = "有音频" if status.get("audio") else "无音频"
    tray.setToolTip(f"HiPi — {operator} {signal_q}% | {audio}")


def _setup_tray(app: QApplication, window: MainWindow, rpc: RpcEventClient) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    tray = QSystemTrayIcon(QIcon(), app)
    tray.setToolTip("HiPi")

    menu = QMenu()
    show_action = QAction("打开 HiPi", app)
    show_action.triggered.connect(window.show)
    quit_action = QAction("退出", app)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    window.modem_status_changed.connect(
        lambda status: _update_tray_status(tray, status)
    )

    return tray
