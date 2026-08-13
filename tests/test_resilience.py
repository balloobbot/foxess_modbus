"""Tests for what a poll does when only part of the inverter answers"""

import logging
from typing import Callable

import pytest
from modbus_connection import IllegalDataAddressError
from modbus_connection import ModbusConnectionError
from modbus_connection import ModbusProtocolError
from modbus_connection import ModbusTimeoutError
from modbus_connection import ServerDeviceBusyError
from modbus_connection.mock import MockModbusUnit

from custom_components.foxess_modbus.common.types import RegisterPollType
from custom_components.foxess_modbus.modbus_controller import _NUM_FAILED_POLLS_FOR_DISCONNECTION

from .conftest import Entity
from .conftest import Harness


class CountingEntity(Entity):
    """Records how many reads the poll had made by the time it was notified"""

    def __init__(self, unit: MockModbusUnit, addresses: list[int]) -> None:
        super().__init__(addresses)
        self._unit = unit
        self.reads_when_notified: list[int] = []

    def update_callback(self, changed_addresses: set[int]) -> None:
        self.reads_when_notified.append(len(self._unit.read_events))
        super().update_callback(changed_addresses)


class OnConnectionEntity(Entity):
    """An entity whose registers are only read once per connection"""

    @property
    def register_poll_type(self) -> RegisterPollType:
        return RegisterPollType.ON_CONNECTION


async def test_a_failed_read_does_not_discard_the_rest_of_the_poll(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(max_read=5)
    entity = harness.add_entity(1, 2)
    harness.add_entity(100, 101)
    harness.unit.holding[1] = [10, 11]
    harness.unit.holding[100] = [20, 21]

    await harness.poll()
    assert harness.controller.read(1, signed=False) == 10
    assert harness.controller.read(100, signed=False) == 20

    # The inverter goes slow on one block, and everything moves on in the meantime
    harness.unit.holding[1] = [30, 31]
    harness.unit.holding[100] = [40, 41]
    harness.unit.fail_read(100, ModbusTimeoutError("no response"))
    entity.changed_addresses.clear()

    await harness.poll()

    assert harness.controller.read(1, signed=False) == 30
    # The block which didn't answer kept its previous values rather than being blanked or re-read as 40
    assert harness.controller.read(100, signed=False) == 20
    # ...and its sensors weren't asked to re-render, since nothing they depend on changed
    assert harness.controller.is_connected
    assert entity.changed_addresses == [{1, 2}]


async def test_sensors_are_notified_only_once_every_range_has_been_tried(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(max_read=5)
    entity = CountingEntity(harness.unit, [1, 2])
    harness.controller.register_modbus_entity(entity)
    harness.add_entity(100, 101)
    harness.unit.fail_read(100, ModbusTimeoutError("no response"))

    await harness.poll()

    # One read covers 1-2, then 100-101 is attempted the full three times before being given up on
    assert [(x.address, x.count) for x in harness.unit.read_events] == [(1, 2), (100, 2), (100, 2), (100, 2)]
    # All four had happened by the time the notification went out, so a sensor never renders halfway through a poll
    assert entity.reads_when_notified == [4]


async def test_a_dead_link_abandons_the_poll(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(max_read=5)
    harness.add_entity(1, 2)
    harness.add_entity(100, 101)
    harness.unit.fail_requests(ModbusConnectionError("connection refused"))

    await harness.poll()

    # Containing a failure per range is for a device which is answering. There's no point working through the
    # remaining ranges once the link itself is down
    assert [(x.address, x.count) for x in harness.unit.read_events] == [(1, 2)]


async def test_a_permanently_failing_range_never_marks_the_inverter_unavailable(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(max_read=5)
    entity = harness.add_entity(1, 2)
    harness.add_entity(100, 101)
    harness.unit.holding[1] = [10, 11]
    harness.unit.fail_read(100, ModbusTimeoutError("no response"))

    for _ in range(_NUM_FAILED_POLLS_FOR_DISCONNECTION * 2):
        await harness.poll()

    assert harness.controller.is_connected
    assert harness.controller.current_connection_error is None
    assert entity.connection_changes == 0
    assert harness.controller.read(1, signed=False) == 10


async def test_a_poll_where_nothing_answers_is_a_failed_poll(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    entity = harness.add_entity(1)
    harness.unit.fail_requests(ServerDeviceBusyError())

    for _ in range(_NUM_FAILED_POLLS_FOR_DISCONNECTION):
        await harness.poll()

    # The link is up but the inverter isn't talking to us at all, which containing failures per range mustn't hide
    assert not harness.controller.is_connected
    assert entity.connection_changes == 1


async def test_a_range_which_keeps_answering_wrongly_is_only_reported_once(
    make_harness: Callable[..., Harness], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness(max_read=5)
    harness.add_entity(1, 2)
    harness.add_entity(100, 101)
    harness.unit.fail_read(100, ModbusProtocolError("wrong response"))

    for _ in range(3):
        await harness.poll()

    # A misconfigured adapter answers wrongly on every poll, and the user only needs telling about it once
    warnings = [x for x in caplog.records if x.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "100-101" in warnings[0].getMessage()


async def test_a_rebuilt_link_reports_a_wrong_response_again(
    make_harness: Callable[..., Harness], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness(max_read=5)
    harness.add_entity(1, 2)
    harness.unit.fail_read(1, ModbusProtocolError("wrong response"))

    for _ in range(_NUM_FAILED_POLLS_FOR_DISCONNECTION + 1):
        await harness.poll()

    # Enough failures dropped the link, and the range still being wrong over the new one is worth hearing about
    assert len([x for x in caplog.records if "Invalid response" in x.getMessage()]) == 2


async def test_a_register_the_inverter_rejects_did_not_answer(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(max_read=5)
    harness.add_entity(1, 2)
    harness.unit.fail_read(1, IllegalDataAddressError())

    await harness.poll()

    # Address 1 was rejected on its own and recorded as blank, so only address 2 actually answered
    assert harness.controller.last_poll is not None
    assert harness.controller.last_poll.updated == ["2-2"]


async def test_on_connection_registers_are_read_until_a_poll_reads_them_all(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(max_read=5)
    harness.controller.register_modbus_entity(OnConnectionEntity([1]))
    harness.add_entity(100, 101)
    harness.unit.fail_read(100, ModbusTimeoutError("no response"))

    await harness.poll()
    harness.unit.read_events.clear()
    await harness.poll()

    # That poll only partly succeeded, so it might not have got as far as address 1. Ask for it again
    assert (1, 1) in [(x.address, x.count) for x in harness.unit.read_events]

    harness.unit.fail_read(100, None)
    await harness.poll()
    harness.unit.read_events.clear()
    await harness.poll()

    # A poll has now read everything, so the once-per-connection registers drop out of the read ranges
    assert [(x.address, x.count) for x in harness.unit.read_events] == [(100, 2)]
