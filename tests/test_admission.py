"""AdmissionGate: bounded concurrency with a short, bounded queue (no Docker needed)."""

from __future__ import annotations

import asyncio

import pytest

from glimpse.execution import NoCapacityError
from glimpse.runners.admission import AdmissionGate


async def test_free_slot_is_immediate() -> None:
    gate = AdmissionGate(2, queue_size=4, queue_timeout_s=1.0)
    waited = await gate.acquire()
    assert waited == 0.0
    assert gate.in_flight == 1
    assert gate.queued == 0
    gate.release()
    assert gate.in_flight == 0


async def test_rejects_immediately_when_queueing_is_off() -> None:
    gate = AdmissionGate(1)  # queue_timeout_s=0: the old reject-at-capacity behaviour
    await gate.acquire()
    with pytest.raises(NoCapacityError, match="at capacity \\(1 concurrent"):
        await gate.acquire()
    assert gate.in_flight == 1
    gate.release()
    assert await gate.acquire() == 0.0


async def test_waits_for_a_slot_then_proceeds() -> None:
    gate = AdmissionGate(1, queue_size=4, queue_timeout_s=5.0)
    await gate.acquire()
    waiter = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0.05)
    assert gate.queued == 1
    assert not waiter.done()
    gate.release()
    waited = await asyncio.wait_for(waiter, 1.0)
    assert waited >= 0.04
    assert gate.in_flight == 1
    assert gate.queued == 0


async def test_queue_timeout_refuses_and_keeps_counts_straight() -> None:
    gate = AdmissionGate(1, queue_size=4, queue_timeout_s=0.1)
    await gate.acquire()
    with pytest.raises(NoCapacityError, match=r"no slot freed up within 0\.1s"):
        await gate.acquire()
    assert gate.in_flight == 1
    assert gate.queued == 0
    gate.release()
    assert await gate.acquire() == 0.0


async def test_full_queue_rejects_immediately() -> None:
    gate = AdmissionGate(1, queue_size=1, queue_timeout_s=5.0)
    await gate.acquire()
    waiter = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0.01)
    assert gate.queued == 1
    with pytest.raises(NoCapacityError):
        await gate.acquire()  # the one queue seat is taken
    gate.release()
    await asyncio.wait_for(waiter, 1.0)
    gate.release()


async def test_queue_is_fifo() -> None:
    gate = AdmissionGate(1, queue_size=8, queue_timeout_s=5.0)
    await gate.acquire()
    order: list[int] = []

    async def worker(n: int) -> None:
        await gate.acquire()
        order.append(n)
        gate.release()

    tasks = [asyncio.create_task(worker(n)) for n in range(4)]
    await asyncio.sleep(0.01)
    gate.release()
    await asyncio.wait_for(asyncio.gather(*tasks), 1.0)
    assert order == [0, 1, 2, 3]
    assert gate.in_flight == 0


async def test_slot_context_manager_releases_on_error() -> None:
    gate = AdmissionGate(1)
    with pytest.raises(RuntimeError):
        async with gate.slot() as waited:
            assert waited == 0.0
            assert gate.in_flight == 1
            raise RuntimeError("boom")
    assert gate.in_flight == 0
    async with gate.slot():
        assert gate.in_flight == 1


def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        AdmissionGate(0)
