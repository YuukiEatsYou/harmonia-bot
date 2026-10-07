"""Persistent, scoped storage for cogs.

Harmony is a single server, so the scopes are `server`, `channel`, `member`,
`role` and `user` - there is no guild dimension to carry around. Values live in
one JSON file per bot under the data directory, which keeps a deployment to a
single folder that can be backed up or copied, the same way Harmony itself does.

Reads and writes go through an `asyncio.Lock` and are flushed with a rename, so
a crash mid-write cannot corrupt the store. The file is only read from disk once
and then kept in memory; every write rewrites it whole, which is fine at the
scale of a single community.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("harmonia.config")

# The server scope has no id, so it is filed under a fixed key.
_SERVER_KEY = "_"
_SCOPES = ("server", "channel", "member", "role", "user")


class Config:
    """Owns one cog-config file and hands out scoped groups onto it."""

    def __init__(self, identifier: str, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir) / "config" / f"{identifier}.json"
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None

    def cog(self, name: str) -> CogConfig:
        """A view of this file namespaced to one cog's data."""
        return CogConfig(self, name)

    # --- file access (called under the lock) ------------------------------

    async def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text("utf-8"))
            except (OSError, ValueError):
                log.exception("could not read %s; starting from empty config", self.path)
                self._data = {}
        else:
            self._data = {}
        for scope in _SCOPES:
            self._data.setdefault(scope, {})
        return self._data

    async def _flush(self) -> None:
        assert self._data is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), "utf-8")
        os.replace(tmp, self.path)

    async def _get_group(self, scope: str, scope_id: str | None, cog: str) -> dict[str, Any]:
        data = await self._load()
        bucket = data.setdefault(scope, {})
        key = _SERVER_KEY if scope == "server" else str(scope_id)
        return bucket.setdefault(key, {}).setdefault(cog, {})

    async def _drop_group(self, scope: str, scope_id: str | None, cog: str) -> None:
        data = await self._load()
        bucket = data.get(scope, {})
        key = _SERVER_KEY if scope == "server" else str(scope_id)
        entry = bucket.get(key)
        if entry and cog in entry:
            del entry[cog]
            if not entry:
                bucket.pop(key, None)


class CogConfig:
    """The scoped entry points a cog uses: `.server()`, `.channel(id)`, ..."""

    def __init__(self, config: Config, cog: str) -> None:
        self._config = config
        self._cog = cog
        self._defaults: dict[str, Any] = {}

    def register(self, **defaults: Any) -> None:
        """Declare default values, applied when a key has never been set.

        Defaults are shared across scopes; a cog that needs different defaults
        per scope can pass an explicit `default` to `get` instead.
        """
        self._defaults.update(defaults)

    def server(self) -> ConfigGroup:
        return self._group("server", None)

    def channel(self, channel_id: str) -> ConfigGroup:
        return self._group("channel", channel_id)

    def member(self, member_id: str) -> ConfigGroup:
        return self._group("member", member_id)

    def role(self, role_id: str) -> ConfigGroup:
        return self._group("role", role_id)

    def user(self, user_id: str) -> ConfigGroup:
        return self._group("user", user_id)

    def _group(self, scope: str, scope_id: str | None) -> ConfigGroup:
        return ConfigGroup(self._config, scope, scope_id, self._cog, self._defaults)


class ConfigGroup:
    """Reads and writes one (scope, id, cog) slice of the store."""

    def __init__(
        self,
        config: Config,
        scope: str,
        scope_id: str | None,
        cog: str,
        defaults: dict[str, Any],
    ) -> None:
        self._config = config
        self._scope = scope
        self._scope_id = scope_id
        self._cog = cog
        self._defaults = defaults

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._config._lock:
            group = await self._config._get_group(self._scope, self._scope_id, self._cog)
            if key in group:
                return group[key]
        if key in self._defaults:
            return self._defaults[key]
        return default

    async def set(self, key: str, value: Any) -> None:
        async with self._config._lock:
            group = await self._config._get_group(self._scope, self._scope_id, self._cog)
            group[key] = value
            await self._config._flush()

    async def update(self, **values: Any) -> None:
        async with self._config._lock:
            group = await self._config._get_group(self._scope, self._scope_id, self._cog)
            group.update(values)
            await self._config._flush()

    async def all(self) -> dict[str, Any]:
        async with self._config._lock:
            group = await self._config._get_group(self._scope, self._scope_id, self._cog)
            merged = {**self._defaults, **group}
        return dict(merged)

    async def clear(self) -> None:
        async with self._config._lock:
            await self._config._drop_group(self._scope, self._scope_id, self._cog)
            await self._config._flush()

    async def delete(self, key: str) -> None:
        async with self._config._lock:
            group = await self._config._get_group(self._scope, self._scope_id, self._cog)
            group.pop(key, None)
            await self._config._flush()
