"""Small asyncio wrapper around the synchronous client.

The core driver is synchronous by design for deterministic SCPI serialization.
This wrapper is useful when integrating into asyncio-based automation servers.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from .client import EResistorClient


class AsyncEResistorClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.sync = EResistorClient(*args, **kwargs)

    async def __aenter__(self) -> "AsyncEResistorClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    async def connect(self) -> None:
        await self._call(self.sync.connect)

    async def close(self) -> None:
        await self._call(self.sync.close)

    async def idn(self) -> str:
        return await self._call(self.sync.idn)

    async def set_mask(self, channel: int, mask) -> str:
        return await self._call(self.sync.set_mask, channel, mask)

    async def set_resistance(self, channel: int, resistance_ohm: float):
        return await self._call(self.sync.set_resistance, channel, resistance_ohm)

    async def set_temperature(self, channel: int, temperature_c: float):
        return await self._call(self.sync.set_temperature, channel, temperature_c)
