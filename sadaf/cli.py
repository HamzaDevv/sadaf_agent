"""Offline foundation commands plus an explicit synthetic OpenRouter smoke."""

import argparse
import asyncio
import json
import sys

from sadaf.conversation import OpenRouterProvider
from sadaf.runtime import FakeTextProvider, InMemoryTurnStore, TextSession
from sadaf.settings import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sadaf offline foundation")
    parser.add_argument("--no-dotenv", action="store_true", help="Do not read .env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Validate setup offline; never create stores or clients")
    text = commands.add_parser("text", help="Use an ephemeral fake text session")
    text.add_argument("--message", help="One synthetic turn; otherwise read lines from stdin")
    smoke = commands.add_parser("live-smoke", help="Opt-in bounded synthetic OpenRouter text check")
    smoke.add_argument("--confirm-live", action="store_true", help="Authorize one synthetic provider request")
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
    if args.command == "live-smoke":
        if not args.confirm_live:
            print("Pass --confirm-live to authorize one synthetic OpenRouter request", file=sys.stderr)
            return 2
        if settings.reasoning.provider != "openrouter":
            print("SADAF_REASONING_PROVIDER must be openrouter", file=sys.stderr)
            return 2
        provider = OpenRouterProvider(settings.openrouter_api_key, settings.reasoning.model,
                                      timeout=20, retries=0, capabilities=())
        try:
            result = asyncio.run(provider.complete([
                {"role": "system", "content": "Reply with exactly: synthetic smoke passed"},
                {"role": "user", "content": "This is a synthetic connectivity check. Reply with the requested phrase."},
            ]))
        except Exception as error:
            print(f"OpenRouter smoke failed: {type(error).__name__}", file=sys.stderr)
            return 1
        print(json.dumps({"status":"response_received", "model":settings.reasoning.model,
                          "text":result.text, "prompt_tokens":result.usage.prompt_tokens,
                          "completion_tokens":result.usage.completion_tokens}, ensure_ascii=False))
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
