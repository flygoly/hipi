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
