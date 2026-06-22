"""HiPi command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from hipi import __version__
from hipi.config import ensure_dirs
from hipi.daemon.rpc_client import RpcClient, RpcError


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_status(client: RpcClient) -> int:
    status = client.call("get_status")
    _print_json(status)
    return 0


def cmd_unlock(client: RpcClient, pin: str) -> int:
    result = client.call("unlock_sim", {"pin": pin})
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_send_sms(client: RpcClient, number: str, text: str) -> int:
    result = client.call("send_sms", {"number": number, "text": text})
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_list_messages(client: RpcClient, limit: int) -> int:
    messages = client.call("list_messages", {"limit": limit})
    _print_json(messages)
    return 0


def cmd_dial(client: RpcClient, number: str) -> int:
    result = client.call("dial", {"number": number})
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_hangup(client: RpcClient, path: str | None) -> int:
    params = {"path": path} if path else {}
    result = client.call("hangup", params)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_sync(client: RpcClient) -> int:
    result = client.call("sync_modem")
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_list_calls(client: RpcClient, limit: int) -> int:
    calls = client.call("list_calls", {"limit": limit})
    _print_json(calls)
    return 0


def cmd_setup_audio(client: RpcClient) -> int:
    result = client.call("setup_call_audio")
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_list_contacts(client: RpcClient, query: str | None) -> int:
    params = {"query": query} if query else {}
    contacts = client.call("list_contacts", params)
    _print_json(contacts)
    return 0


def cmd_daemon() -> int:
    from hipi.daemon.server import main as daemon_main

    return daemon_main()


def cmd_ui() -> int:
    from hipi.ui.app import run_app

    return run_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hipi", description="HiPi 4G SMS and voice")
    parser.add_argument("--version", action="version", version=f"hipi {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ui", help="Launch desktop UI")
    sub.add_parser("daemon", help="Run background daemon")

    p_status = sub.add_parser("status", help="Show modem status")
    p_status.set_defaults(func=lambda c, a: cmd_status(c))

    p_unlock = sub.add_parser("unlock", help="Unlock SIM with PIN")
    p_unlock.add_argument("pin", help="SIM PIN code")
    p_unlock.set_defaults(func=lambda c, a: cmd_unlock(c, a.pin))

    p_sms = sub.add_parser("send-sms", help="Send an SMS")
    p_sms.add_argument("number", help="Recipient phone number")
    p_sms.add_argument("text", help="Message body")
    p_sms.set_defaults(func=lambda c, a: cmd_send_sms(c, a.number, a.text))

    p_list = sub.add_parser("list-messages", help="List stored messages")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=lambda c, a: cmd_list_messages(c, a.limit))

    p_dial = sub.add_parser("dial", help="Place a voice call")
    p_dial.add_argument("number", help="Phone number to dial")
    p_dial.set_defaults(func=lambda c, a: cmd_dial(c, a.number))

    p_hangup = sub.add_parser("hangup", help="Hang up active call(s)")
    p_hangup.add_argument("--path", help="ModemManager call object path")
    p_hangup.set_defaults(func=lambda c, a: cmd_hangup(c, a.path))

    p_sync = sub.add_parser("sync", help="Sync SMS from modem")
    p_sync.set_defaults(func=lambda c, a: cmd_sync(c))

    p_calls = sub.add_parser("list-calls", help="List call history")
    p_calls.add_argument("--limit", type=int, default=50)
    p_calls.set_defaults(func=lambda c, a: cmd_list_calls(c, a.limit))

    p_contacts = sub.add_parser("list-contacts", help="List local contacts")
    p_contacts.add_argument("--query", help="Search by name or number")
    p_contacts.set_defaults(func=lambda c, a: cmd_list_contacts(c, a.query))

    p_audio = sub.add_parser("setup-audio", help="Route call audio to modem device")
    p_audio.set_defaults(func=lambda c, a: cmd_setup_audio(c))

    args = parser.parse_args(argv)
    ensure_dirs()

    if args.command in (None, "ui"):
        return cmd_ui()
    if args.command == "daemon":
        return cmd_daemon()

    client = RpcClient()
    try:
        return args.func(client, args)
    except RpcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
