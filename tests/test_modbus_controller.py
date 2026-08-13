"""Tests for ModbusController, run against modbus-connection's in-memory backend"""

from typing import Any
from typing import Callable

from modbus_connection import IllegalDataAddressError
from modbus_connection import ModbusConnectionError
from modbus_connection import ModbusTimeoutError

from .conftest import Harness

_FC_WRITE_SINGLE_REGISTER = 0x06
_FC_WRITE_MULTIPLE_REGISTERS = 0x10


async def test_poll_batches_addresses_into_reads_of_at_most_max_read(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(max_read=5)
    # 1-2 and 4-5 are close enough to fetch in one read; 100 is not, and 200-206 needs splitting at max_read
    harness.add_entity(1, 2, 4, 5)
    harness.add_entity(100)
    harness.add_entity(200, 201, 202, 203, 204, 205, 206)

    await harness.poll()

    assert [(x.address, x.count) for x in harness.unit.read_events] == [(1, 5), (100, 1), (200, 5), (205, 2)]
    assert all(x.register_type == "holding" for x in harness.unit.read_events)


async def test_poll_makes_read_values_available(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    entity = harness.add_entity(1, 2)
    harness.unit.holding[1] = [0x1234, 0xFFFF]

    await harness.poll()

    assert harness.controller.read(1, signed=False) == 0x1234
    assert harness.controller.read(2, signed=True) == -1
    # A 32-bit value spread over two registers, least-significant word first
    assert harness.controller.read([1, 2], signed=False) == 0xFFFF1234
    assert entity.changed_addresses == [{1, 2}]


async def test_rejected_register_is_read_individually_then_skipped(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(max_read=5)
    harness.add_entity(10)
    harness.add_entity(20)
    harness.unit.holding[10] = 7
    harness.unit.fail_read(20, IllegalDataAddressError())

    await harness.poll()

    # 20 was rejected, so it was retried on its own before being written off
    assert [(x.address, x.count) for x in harness.unit.read_events] == [(10, 1), (20, 1), (20, 1)]
    assert harness.controller.read(10, signed=False) == 7
    assert harness.controller.read(20, signed=False) is None

    harness.unit.read_events.clear()
    await harness.poll()

    # Having been written off once, 20 isn't asked for again
    assert [(x.address, x.count) for x in harness.unit.read_events] == [(10, 1)]


async def test_reads_are_retried(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(1)

    attempts = 0

    def flaky() -> int:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ModbusTimeoutError("no response")
        return 42

    harness.unit.holding[1] = flaky

    await harness.poll()

    assert attempts == 3
    assert harness.controller.read(1, signed=False) == 42


async def test_read_failure_is_not_retried_forever(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(1)

    def always_times_out() -> int:
        raise ModbusTimeoutError("no response")

    harness.unit.holding[1] = always_times_out

    await harness.poll()

    assert len(harness.unit.read_events) == 3
    assert harness.controller.read(1, signed=False) is None


async def test_written_value_is_used_until_it_is_polled_back(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(1)
    harness.unit.holding[1] = 5

    await harness.poll()
    assert harness.controller.read(1, signed=False) == 5

    await harness.controller.write_register(1, 99)

    # The inverter takes a while to report a written value back, so the controller reports what it wrote
    assert harness.controller.read(1, signed=False) == 99
    assert await harness.unit.read_holding_registers(1, 1) == [99]


async def test_negative_written_values_are_sent_as_unsigned(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    harness.add_entity(1)

    await harness.controller.write_register(1, -1)

    assert await harness.unit.read_holding_registers(1, 1) == [0xFFFF]


async def test_multiple_values_are_written_in_one_request(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    writes: list[Any] = []
    harness.unit.on_write(lambda event: writes.append((event.address, event.values, event.function_code)))

    await harness.controller.write_registers(1, [10, 20, 30])

    assert writes == [(1, [10, 20, 30], _FC_WRITE_MULTIPLE_REGISTERS)]


async def test_a_single_value_is_written_with_write_single_register(make_harness: Callable[..., Harness]) -> None:
    # Which function code goes out is not an implementation detail: some inverters only accept 0x06 for a single
    # register, so collapsing this onto write_registers would work against the mock and fail against hardware
    harness = make_harness()
    writes: list[Any] = []
    harness.unit.on_write(lambda event: writes.append((event.address, event.values, event.function_code)))

    await harness.controller.write_register(1, 10)

    assert writes == [(1, [10], _FC_WRITE_SINGLE_REGISTER)]


async def test_repeated_failures_mark_the_inverter_disconnected(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    entity = harness.add_entity(1)
    harness.unit.holding[1] = 5
    harness.unit.fail_requests(ModbusConnectionError("connection refused"))

    for _ in range(4):
        await harness.poll()
    assert harness.controller.is_connected

    await harness.poll()
    assert not harness.controller.is_connected
    assert harness.controller.current_connection_error == "connection refused"
    assert entity.connection_changes == 1

    harness.unit.fail_requests(None)
    await harness.poll()

    assert harness.controller.is_connected
    assert harness.controller.current_connection_error is None
    assert entity.connection_changes == 2


async def test_a_wedged_link_is_dropped_so_the_next_poll_rebuilds_it(make_harness: Callable[..., Harness]) -> None:
    # Some adapters keep the socket open but stop answering. Reconnecting is the only way out, and it must not
    # need a config entry reload
    harness = make_harness()
    harness.add_entity(1)
    harness.unit.holding[1] = 5

    await harness.poll()
    assert harness.controller.is_connected
    assert harness.connection.connected

    harness.unit.fail_requests(ModbusTimeoutError("no response"))
    for _ in range(5):
        await harness.poll()

    assert not harness.controller.is_connected
    assert not harness.connection.connected, "the wedged link should have been dropped"

    harness.unit.fail_requests(None)
    await harness.poll()

    assert harness.controller.is_connected
    assert harness.connection.connected, "the next poll should have established a fresh link"
    assert harness.controller.read(1, signed=False) == 5
