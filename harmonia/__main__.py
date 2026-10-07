"""Launcher: read a config file, load the cogs, run the bot.

    python -m harmonia --config config.toml

The token and base URL can also come from the environment (`HARMONIA_TOKEN`,
`HARMONIA_BASE_URL`) or the command line, which is handy for a service unit that
should not carry the token in a file.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tomllib
from pathlib import Path

from .client import Bot

DEFAULT_EXTENSIONS = ["cogs.ping", "cogs.poll", "cogs.moderation"]


def _load_config(path: str) -> dict:
    file = Path(path)
    if not file.exists():
        return {}
    with file.open("rb") as handle:
        return tomllib.load(handle)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harmonia", description="Run a Harmony bot.")
    parser.add_argument("--config", default="config.toml", help="path to a TOML config file")
    parser.add_argument("--base-url", help="override the instance base URL")
    parser.add_argument("--token", help="override the bot token")
    parser.add_argument("--cog", dest="cogs", action="append", help="a cog to load (repeatable)")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING or ERROR")
    return parser


async def _serve(bot: Bot, extensions: list[str]) -> None:
    await bot.load_extensions(extensions)
    await bot.start()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = _load_config(args.config)

    base_url = args.base_url or config.get("base_url") or os.environ.get("HARMONIA_BASE_URL")
    token = args.token or config.get("token") or os.environ.get("HARMONIA_TOKEN")
    if not base_url or not token:
        print(
            "error: a base URL and a bot token are required "
            "(config file, environment or command line)",
            file=sys.stderr,
        )
        return 2

    level_name = str(args.log_level or config.get("log_level", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    extensions = args.cogs or config.get("extensions") or DEFAULT_EXTENSIONS
    bot = Bot(
        base_url=base_url,
        token=token,
        data_dir=config.get("data_dir", "data"),
        config_name=config.get("name", "bot"),
    )

    try:
        asyncio.run(_serve(bot, extensions))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
