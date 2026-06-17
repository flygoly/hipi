"""HiPi background daemon."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from gi.repository import GLib

from hipi.config import SOCKET_PATH, ensure_dirs
from hipi.daemon.audio import AudioRouter
from hipi.daemon.modem import ModemManagerClient, ModemManagerError
from hipi.daemon.rpc import RpcServer
from hipi.daemon.sms import SmsService
from hipi.daemon.voice import VoiceService
from hipi.db.models import Database, Message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("hipi.daemon")


class HiPiDaemon:
    def __init__(self) -> None:
        ensure_dirs()
        self.db = Database()
        self.mm: ModemManagerClient | None = None
        self.audio = AudioRouter()
        self.loop = asyncio.new_event_loop()
        self.rpc = RpcServer(str(SOCKET_PATH))
        self._glib_loop = GLib.MainLoop()
        self._sms: SmsService | None = None
        self._voice: VoiceService | None = None
        self._poll_timer: int | None = None

    def _on_message(self, msg: Message) -> None:
        asyncio.run_coroutine_threadsafe(
            self.rpc.broadcast_event("new_message", msg.to_dict()),
            self.loop,
        )

    def _on_call_event(self, event: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(
            self.rpc.broadcast_event(event.get("type", "call_event"), event),
            self.loop,
        )

    def _init_services(self) -> None:
        if not self.mm:
            self._sms = None
            self._voice = None
            return
        self._sms = SmsService(self.mm, self.db, on_message=self._on_message)
        self._voice = VoiceService(self.mm, self.db, on_call_event=self._on_call_event)

    def _register_handlers(self) -> None:
        self.rpc.register("ping", lambda _p: {"pong": True})
        self.rpc.register("get_status", self._handle_get_status)
        self.rpc.register("unlock_sim", self._handle_unlock_sim)
        self.rpc.register("send_sms", self._handle_send_sms)
        self.rpc.register("list_messages", self._handle_list_messages)
        self.rpc.register("list_conversations", self._handle_list_conversations)
        self.rpc.register("mark_conversation_read", self._handle_mark_read)
        self.rpc.register("dial", self._handle_dial)
        self.rpc.register("answer", self._handle_answer)
        self.rpc.register("hangup", self._handle_hangup)
        self.rpc.register("list_calls", self._handle_list_calls)
        self.rpc.register("list_active_calls", self._handle_list_active_calls)
        self.rpc.register("get_onboarding", self._handle_get_onboarding)
        self.rpc.register("complete_onboarding", self._handle_complete_onboarding)
        self.rpc.register("setup_call_audio", self._handle_setup_call_audio)
        self.rpc.register("sync_modem", self._handle_sync_modem)

    def _modem_path(self) -> str | None:
        if not self.mm:
            return None
        return self.mm.get_primary_modem_path()

    def _handle_get_status(self, _params: dict) -> dict[str, Any]:
        path = self._modem_path()
        if not path:
            return {"modem_present": False, "audio": self.audio.has_voice_audio()}
        status = self.mm.get_modem_status(path)
        return {
            "modem_present": True,
            "modem": status.to_dict(),
            "audio": self.audio.has_voice_audio(),
        }

    def _handle_unlock_sim(self, params: dict) -> dict[str, Any]:
        path = self._modem_path()
        if not path:
            return {"ok": False, "error": "No modem found"}
        pin = params.get("pin", "")
        if not pin:
            return {"ok": False, "error": "PIN required"}
        try:
            self.mm.unlock_sim(path, pin)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_send_sms(self, params: dict) -> dict[str, Any]:
        path = self._modem_path()
        if not path or not self._sms:
            return {"ok": False, "error": "No modem"}
        return self._sms.send_sms(path, params.get("number", ""), params.get("text", ""))

    def _handle_list_messages(self, params: dict) -> list[dict]:
        limit = int(params.get("limit", 100))
        peer = params.get("peer")
        return [m.to_dict() for m in self.db.list_messages(limit=limit, peer=peer)]

    def _handle_list_conversations(self, _params: dict) -> list[dict]:
        return self.db.list_conversations()

    def _handle_mark_read(self, params: dict) -> dict[str, bool]:
        peer = params.get("peer")
        if not peer:
            return {"ok": False}
        for msg in self.db.list_messages(limit=500, peer=peer):
            if msg.direction == "inbound" and msg.status == "received":
                self.db.update_message_status(msg.id, "read")
        return {"ok": True}

    def _handle_dial(self, params: dict) -> dict[str, Any]:
        path = self._modem_path()
        if not path or not self._voice:
            return {"ok": False, "error": "No modem"}
        audio_result = self.audio.setup_call_audio()
        result = self._voice.dial(path, params.get("number", ""))
        result["audio"] = audio_result
        return result

    def _handle_answer(self, params: dict) -> dict[str, Any]:
        if not self._voice:
            return {"ok": False, "error": "Voice service unavailable"}
        call_path = params.get("path")
        if not call_path:
            path = self._modem_path()
            if path:
                active = self._voice.list_active_calls(path)
                ringing = [c for c in active if c["state"] == "ringing-in"]
                if ringing:
                    call_path = ringing[0]["path"]
        if not call_path:
            return {"ok": False, "error": "No incoming call"}
        self.audio.setup_call_audio()
        return self._voice.answer(call_path)

    def _handle_hangup(self, params: dict) -> dict[str, Any]:
        if not self._voice:
            return {"ok": False, "error": "Voice service unavailable"}
        return self._voice.hangup(params.get("path"))

    def _handle_list_calls(self, params: dict) -> list[dict]:
        limit = int(params.get("limit", 50))
        return [c.to_dict() for c in self.db.list_calls(limit=limit)]

    def _handle_list_active_calls(self, _params: dict) -> list[dict]:
        path = self._modem_path()
        if not path or not self._voice:
            return []
        return self._voice.list_active_calls(path)

    def _handle_get_onboarding(self, _params: dict) -> dict[str, Any]:
        return {"complete": self.db.is_onboarding_complete()}

    def _handle_complete_onboarding(self, _params: dict) -> dict[str, bool]:
        self.db.mark_onboarding_complete()
        return {"ok": True}

    def _handle_setup_call_audio(self, _params: dict) -> dict[str, Any]:
        return self.audio.setup_call_audio()

    def _handle_sync_modem(self, _params: dict) -> dict[str, Any]:
        path = self._modem_path()
        if not path or not self._sms:
            return {"ok": False, "error": "No modem"}
        imported = self._sms.sync_from_modem(path)
        if self._voice:
            self._voice.poll_calls(path)
        return {"ok": True, "imported": len(imported)}

    def _on_modem_added(self, path: str) -> None:
        logger.info("Modem added: %s", path)
        try:
            self.mm.enable_modem(path)
        except Exception as exc:
            logger.warning("Enable modem failed: %s", exc)
        if self._sms:
            self._sms.sync_from_modem(path)

    def _on_sms_added(self, path: str) -> None:
        if self._sms:
            self._sms.handle_sms_added(path)

    def _on_call_added(self, path: str) -> None:
        if self._voice:
            self._voice.handle_call_added(path)

    def _poll_modem(self) -> bool:
        path = self._modem_path()
        if path and self._sms:
            self._sms.sync_from_modem(path)
        if path and self._voice:
            self._voice.poll_calls(path)
        return True

    def _setup_mm_signals(self) -> None:
        if not self.mm:
            return
        self.mm.on_modem_added(self._on_modem_added)
        self.mm.on_sms_added(self._on_sms_added)
        self.mm.on_call_added(self._on_call_added)
        self._poll_timer = GLib.timeout_add_seconds(30, self._poll_modem)

    async def _run_async(self) -> None:
        await self.rpc.start()

    def run(self) -> int:
        try:
            self.mm = ModemManagerClient()
        except ModemManagerError as exc:
            logger.error("%s", exc)
            self.mm = None

        self._init_services()
        self._register_handlers()
        self._setup_mm_signals()

        path = self._modem_path()
        if path:
            logger.info("Primary modem: %s", path)
            try:
                status = self.mm.get_modem_status(path)
                if status.state == "disabled":
                    self.mm.enable_modem(path)
            except Exception as exc:
                logger.warning("Modem enable: %s", exc)
            if self._sms:
                self._sms.sync_from_modem(path)

        self.loop.run_until_complete(self._run_async())

        def shutdown(*_args):
            logger.info("Shutting down")
            self.loop.create_task(self.rpc.stop())
            self._glib_loop.quit()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        import threading

        def run_glib():
            self._glib_loop.run()

        threading.Thread(target=run_glib, daemon=True).start()

        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.rpc.stop())
            self.db.close()
        return 0


def main() -> int:
    return HiPiDaemon().run()


if __name__ == "__main__":
    raise SystemExit(main())
