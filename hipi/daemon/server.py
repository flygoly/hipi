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
from hipi.daemon.forward import SmsForwarder
from hipi.daemon.modem import ModemManagerClient, ModemManagerError
from hipi.daemon.rpc import RpcServer
from hipi.daemon.sms import SmsService
from hipi.daemon.voice import VoiceService
from hipi.db.models import Database, Message
from hipi.export import export_calls_csv, export_messages_csv
from hipi.status_file import write_status_file
from hipi.util import normalize_number
from hipi.vcard import export_vcards, parse_vcard

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
        self._forwarder = SmsForwarder(self.db)
        self._poll_timer: int | None = None

    def _on_message(self, msg: Message) -> None:
        asyncio.run_coroutine_threadsafe(
            self.rpc.broadcast_event("new_message", msg.to_dict()),
            self.loop,
        )
        self._publish_status()

    def _on_message_updated(self, msg: Message) -> None:
        asyncio.run_coroutine_threadsafe(
            self.rpc.broadcast_event("message_updated", msg.to_dict()),
            self.loop,
        )

    def _on_call_event(self, event: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(
            self.rpc.broadcast_event(event.get("type", "call_event"), event),
            self.loop,
        )

    def _on_inbound_sms(self, msg: Message, props: dict, modem_path: str) -> None:
        if self._sms:
            self._forwarder.maybe_forward(msg, props, self._sms, modem_path)

    def _init_services(self) -> None:
        if not self.mm:
            self._sms = None
            self._voice = None
            return
        self._sms = SmsService(
            self.mm,
            self.db,
            on_message=self._on_message,
            on_message_updated=self._on_message_updated,
            on_inbound=self._on_inbound_sms,
        )
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
        self.rpc.register("list_contacts", self._handle_list_contacts)
        self.rpc.register("add_contact", self._handle_add_contact)
        self.rpc.register("update_contact", self._handle_update_contact)
        self.rpc.register("delete_contact", self._handle_delete_contact)
        self.rpc.register("get_sms_forward", self._handle_get_sms_forward)
        self.rpc.register("set_sms_forward", self._handle_set_sms_forward)
        self.rpc.register("get_contact_map", self._handle_get_contact_map)
        self.rpc.register("import_contacts_vcard", self._handle_import_contacts_vcard)
        self.rpc.register("export_contacts_vcard", self._handle_export_contacts_vcard)
        self.rpc.register("export_messages_csv", self._handle_export_messages_csv)
        self.rpc.register("export_calls_csv", self._handle_export_calls_csv)

    def _modem_path(self) -> str | None:
        if not self.mm:
            return None
        return self.mm.get_primary_modem_path()

    def _build_status(self) -> dict[str, Any]:
        path = self._modem_path()
        unread = self.db.count_unread_messages()
        base: dict[str, Any] = {
            "unread_sms": unread,
            "launch_command": "hipi ui",
        }
        if not path:
            base["modem_present"] = False
            base["audio"] = self.audio.has_voice_audio()
            return base
        status = self.mm.get_modem_status(path)
        base.update(
            {
                "modem_present": True,
                "modem": status.to_dict(),
                "audio": self.audio.has_voice_audio(),
            }
        )
        return base

    def _publish_status(self) -> dict[str, Any]:
        status = self._build_status()
        write_status_file(status)
        return status

    def _handle_get_status(self, _params: dict) -> dict[str, Any]:
        return self._publish_status()

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
        cmap = self.db.get_contact_map()
        convs = self.db.list_conversations()
        for conv in convs:
            conv["name"] = cmap.get(conv["peer"])
        return convs

    def _handle_mark_read(self, params: dict) -> dict[str, bool]:
        peer = params.get("peer")
        if not peer:
            return {"ok": False}
        for msg in self.db.list_messages(limit=500, peer=peer):
            if msg.direction == "inbound" and msg.status == "received":
                self.db.update_message_status(msg.id, "read")
        self._publish_status()
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
        result = self._voice.hangup(params.get("path"))
        self.audio.teardown_call_audio()
        return result

    def _handle_list_calls(self, params: dict) -> list[dict]:
        limit = int(params.get("limit", 50))
        cmap = self.db.get_contact_map()
        records = []
        for call in self.db.list_calls(limit=limit):
            data = call.to_dict()
            data["name"] = cmap.get(call.peer)
            records.append(data)
        return records

    def _handle_list_contacts(self, params: dict) -> list[dict]:
        query = params.get("query")
        return [c.to_dict() for c in self.db.list_contacts(query=query)]

    def _handle_add_contact(self, params: dict) -> dict[str, Any]:
        name = params.get("name", "").strip()
        number = params.get("number", "").strip()
        if not name or not number:
            return {"ok": False, "error": "姓名和号码必填"}
        try:
            contact = self.db.add_contact(name, number, params.get("notes", ""))
            return {"ok": True, "contact": contact.to_dict()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_update_contact(self, params: dict) -> dict[str, Any]:
        cid = int(params.get("id", 0))
        name = params.get("name", "").strip()
        number = params.get("number", "").strip()
        if not cid or not name or not number:
            return {"ok": False, "error": "参数不完整"}
        try:
            self.db.update_contact(cid, name, number, params.get("notes", ""))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_delete_contact(self, params: dict) -> dict[str, Any]:
        cid = int(params.get("id", 0))
        if not cid:
            return {"ok": False, "error": "缺少 id"}
        self.db.delete_contact(cid)
        return {"ok": True}

    def _handle_get_contact_map(self, _params: dict) -> dict[str, str]:
        return self.db.get_contact_map()

    def _handle_get_sms_forward(self, _params: dict) -> dict[str, Any]:
        return self.db.get_sms_forward_config()

    def _handle_set_sms_forward(self, params: dict) -> dict[str, Any]:
        enabled = bool(params.get("enabled", False))
        target = params.get("target", "").strip()
        webhook = params.get("webhook", "").strip()
        webhook_secret = params.get("webhook_secret")
        if enabled and not target and not webhook:
            return {"ok": False, "error": "启用转发时需填写目标号码或 Webhook URL"}
        if target:
            target = normalize_number(target)
        self.db.set_sms_forward_enabled(enabled)
        self.db.set_sms_forward_target(target)
        self.db.set_sms_forward_webhook(webhook)
        if webhook_secret is not None:
            self.db.set_sms_forward_webhook_secret(webhook_secret.strip())
        return {"ok": True, "config": self.db.get_sms_forward_config()}

    def _handle_export_messages_csv(self, params: dict) -> dict[str, Any]:
        limit = int(params.get("limit", 10000))
        return {"ok": True, "csv": export_messages_csv(self.db, limit=limit)}

    def _handle_export_calls_csv(self, params: dict) -> dict[str, Any]:
        limit = int(params.get("limit", 10000))
        return {"ok": True, "csv": export_calls_csv(self.db, limit=limit)}

    def _handle_import_contacts_vcard(self, params: dict) -> dict[str, Any]:
        content = params.get("content", "")
        if not content.strip():
            return {"ok": False, "error": "vCard 内容为空"}
        parsed = parse_vcard(content)
        if not parsed:
            return {"ok": False, "error": "未解析到有效联系人"}
        stats = self.db.import_contacts_batch([(c.name, c.number, c.notes) for c in parsed])
        return {"ok": True, **stats, "total_parsed": len(parsed)}

    def _handle_export_contacts_vcard(self, _params: dict) -> dict[str, Any]:
        contacts = [c.to_dict() for c in self.db.list_contacts()]
        return {"ok": True, "vcard": export_vcards(contacts), "count": len(contacts)}

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
        imported = self._sms.sync_from_modem(path, emit_events=False)
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
            self._sms.sync_from_modem(path, emit_events=False)

    def _on_sms_added(self, path: str) -> None:
        if self._sms:
            mp = self._modem_path()
            self._sms.handle_sms_added(path, mp)

    def _on_call_added(self, path: str) -> None:
        if self._voice:
            self._voice.handle_call_added(path)

    def _poll_modem(self) -> bool:
        path = self._modem_path()
        if path and self._sms:
            self._sms.sync_from_modem(path, emit_events=False)
        if path and self._voice:
            self._voice.poll_calls(path)
        self._publish_status()
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
                self._sms.sync_from_modem(path, emit_events=False)
            self._publish_status()

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
