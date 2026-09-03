"""``glimpse`` command line interface.

glimpse run hello.py                      # language inferred from the extension
glimpse run --lang go - < main.go         # read source from stdin
glimpse languages
glimpse serve --runner docker --port 8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__, languages
from .client import DEFAULT_URL, GlimpseClient, GlimpseError

ClientFactory = Callable[[str | None, str | None], GlimpseClient]

TIMEOUT_EXIT_CODE = 124


def _default_client(url: str | None, api_key: str | None) -> GlimpseClient:
    return GlimpseClient(url, api_key=api_key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glimpse",
        description="Run code snippets in isolated sandboxes via a Glimpse server.",
    )
    parser.add_argument("--version", action="version", version=f"glimpse {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a source file on a Glimpse server")
    run.add_argument("file", help="source file, or '-' to read the code from stdin")
    run.add_argument(
        "-l", "--lang", help="language id/alias (default: inferred from the extension)"
    )
    run.add_argument("--stdin-file", help="file whose contents become the program's stdin")
    run.add_argument(
        "--stdin", dest="stdin_text", help="literal string to use as the program's stdin"
    )
    run.add_argument("-t", "--timeout", type=float, help="run-phase timeout in seconds")
    run.add_argument("--json", action="store_true", help="print the raw JSON response")
    run.add_argument("-q", "--quiet", action="store_true", help="omit the status line")
    _server_args(run)

    langs = sub.add_parser("languages", help="list the languages the server supports")
    langs.add_argument("--json", action="store_true", help="print the raw JSON response")
    _server_args(langs)

    serve = sub.add_parser("serve", help="start the Glimpse API server")
    serve.add_argument("--runner", choices=["docker", "lambda", "unsafe-local"])
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--log-level")
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    return parser


def _server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--url",
        help=f"server URL (default: $GLIMPSE_URL or {DEFAULT_URL})",
    )
    parser.add_argument("--api-key", help="API key (default: $GLIMPSE_API_KEY)")


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _read_stdin_arg(args: argparse.Namespace) -> str:
    if args.stdin_text is not None:
        return str(args.stdin_text)
    if args.stdin_file:
        return Path(args.stdin_file).read_text(encoding="utf-8")
    return ""


def cmd_run(args: argparse.Namespace, make_client: ClientFactory) -> int:
    if args.lang:
        language = args.lang
    else:
        guessed = languages.from_filename(args.file) if args.file != "-" else None
        if guessed is None:
            print(
                "error: cannot infer the language; pass --lang (one of: "
                + ", ".join(languages.BY_ID)
                + ")",
                file=sys.stderr,
            )
            return 2
        language = guessed.id
    try:
        code = _read_source(args.file)
        stdin = _read_stdin_arg(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with make_client(args.url, args.api_key) as client:
        result = client.execute(language, code, stdin=stdin, timeout_s=args.timeout)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2))
    else:
        sys.stdout.write(result.stdout)
        sys.stdout.flush()
        sys.stderr.write(result.stderr)
        if not args.quiet:
            status = "timed out" if result.timed_out else f"exit {result.exit_code}"
            extra = " · output truncated" if result.truncated else ""
            print(
                f"[glimpse] {result.language} · {result.phase} · {status} · "
                f"{result.duration_ms} ms{extra}",
                file=sys.stderr,
            )
    if result.timed_out:
        return TIMEOUT_EXIT_CODE
    return result.exit_code


def cmd_languages(args: argparse.Namespace, make_client: ClientFactory) -> int:
    with make_client(args.url, args.api_key) as client:
        items = client.languages()
    if args.json:
        print(json.dumps([item.model_dump() for item in items], indent=2))
        return 0
    width = max(len(item.id) for item in items)
    for item in items:
        aliases = f" ({', '.join(item.aliases)})" if item.aliases else ""
        version = f"  {item.version}" if item.version else ""
        print(f"{item.id.ljust(width)}  {item.name}{aliases}{version}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import logging

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    # Settings are read from the environment by the app factory (so --reload works).
    if args.runner:
        os.environ["GLIMPSE_RUNNER"] = args.runner
    if args.host:
        os.environ["GLIMPSE_HOST"] = args.host
    if args.port:
        os.environ["GLIMPSE_PORT"] = str(args.port)
    if args.log_level:
        os.environ["GLIMPSE_LOG_LEVEL"] = args.log_level

    from .config import get_settings

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "glimpse.api.app:app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=args.reload,
    )
    return 0


def main(argv: Sequence[str] | None = None, *, make_client: ClientFactory | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    factory = make_client or _default_client
    try:
        if args.command == "run":
            return cmd_run(args, factory)
        if args.command == "languages":
            return cmd_languages(args, factory)
        if args.command == "serve":
            return cmd_serve(args)
    except GlimpseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
