"""Offline commands only; live adapters are future milestones."""

import argparse
import json
import sys

from sadaf.runtime import FakeTextProvider, InMemoryTurnStore, TextSession
from sadaf.settings import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sadaf offline foundation")
    parser.add_argument("--no-dotenv", action="store_true", help="Do not read .env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Validate setup offline; never create stores or clients")
    text = commands.add_parser("text", help="Use an ephemeral fake text session")
    text.add_argument("--message", help="One synthetic turn; otherwise read lines from stdin")
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 13):
        print("Unsupported Python: use Python 3.13", file=sys.stderr)
        return 2
    try:
        settings = load_settings(read_dotenv=not args.no_dotenv)
    except SettingsError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    if args.command == "doctor":
        print(json.dumps({
            "status": "ok", "python": "3.13", "execution": "offline",
            "configured_roles": {name: getattr(settings, name).provider for name in
                                 ("reasoning", "extraction", "voice", "embeddings")},
            "m2_configured": settings.m2_endpoint is not None,
            "clients_started": False, "stores_opened": False,
            "live_capabilities_verified": False,
        }, indent=2))
        return 0
    if any(getattr(settings, name).provider not in {"fake", "disabled"} for name in
           ("reasoning", "extraction", "voice", "embeddings")):
        print("Text mode requires offline role settings; live adapters are not implemented", file=sys.stderr)
        return 2
    session = TextSession(FakeTextProvider(), InMemoryTurnStore())
    try:
        if args.message is not None:
            print(session.respond(args.message))
        else:
            print("Sadaf offline fake. Ephemeral history; EOF exits.")
            for line in sys.stdin:
                if line.strip():
                    print(session.respond(line.rstrip("\n")))
    except (ValueError, KeyboardInterrupt):
        print("Text session stopped or input was empty", file=sys.stderr)
        return 2
    return 0
