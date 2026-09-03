"""Admission control for execution backends.

An :class:`AdmissionGate` bounds how many executions run at once. A slot is held for
the whole execution (a program that sleeps for its entire timeout occupies one just as
much as a busy one). When every slot is taken, a caller waits in a small bounded queue
for up to ``queue_timeout_s`` before being refused with :class:`NoCapacityError`, which
the API maps to ``503`` + ``Retry-After``.

Queueing turns a burst into slightly higher latency instead of a wall of ``503``s: with
``limit`` slots and runs that take a few hundred milliseconds, a queue of a couple of
seconds absorbs bursts several times larger than the slot count. ``queue_timeout_s = 0``
(or ``queue_size = 0``) restores reject-immediately behaviour.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

from ..execution import NoCapacityError


class AdmissionGate:
    def __init__(self, limit: int, *, queue_size: int = 0, queue_timeout_s: float = 0.0) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.queue_size = max(0, queue_size)
        self.queue_timeout_s = max(0.0, queue_timeout_s)
        self._slots = asyncio.Semaphore(limit)
        self._in_flight = 0
        self._queued = 0

    @property
    def in_flight(self) -> int:
        """Executions currently holding a slot."""
        return self._in_flight

    @property
    def queued(self) -> int:
        """Callers currently waiting for a slot."""
        return self._queued

    @property
    def queueing(self) -> bool:
        return self.queue_timeout_s > 0 and self.queue_size > 0

    async def acquire(self) -> float:
        """Take a slot, waiting in the queue if necessary.

        Returns the seconds spent waiting (``0.0`` when a slot was free). Raises
        :class:`NoCapacityError` when every slot is busy and either queueing is off, the
        queue is full, or no slot frees up within ``queue_timeout_s``.
        """
        if not self._slots.locked():
            await self._slots.acquire()  # a slot is free: never blocks
            self._in_flight += 1
            return 0.0
        if not self.queueing or self._queued >= self.queue_size:
            raise NoCapacityError(f"at capacity ({self.limit} concurrent executions)")
        self._queued += 1
        started = time.monotonic()
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self.queue_timeout_s)
        except TimeoutError:
            raise NoCapacityError(
                f"at capacity ({self.limit} concurrent executions); "
                f"no slot freed up within {self.queue_timeout_s:g}s"
            ) from None
        finally:
            self._queued -= 1
        self._in_flight += 1
        return time.monotonic() - started

    def release(self) -> None:
        self._in_flight -= 1
        self._slots.release()

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncIterator[float]:
        """``async with gate.slot() as waited_s:`` — hold a slot for the block."""
        waited = await self.acquire()
        try:
            yield waited
        finally:
            self.release()
