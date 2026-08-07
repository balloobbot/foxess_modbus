"""Tests for ModbusController, run against modbus-connection's in-memory backend"""

from datetime import timedelta
from typing import Any
from typing import Callable
from typing import cast

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from modbus_connection import ModbusConnectionError
from modbus_connection import ModbusExceptionError
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.foxess_modbus.common.entity_controller import ModbusControllerEntity
from custom_components.foxess_modbus.common.types import ConnectionType
from custom_components.foxess_modbus.common.types import Inv
from custom_components.foxess_modbus.common.types import InverterModel
from custom_components.foxess_modbus.common.types import RegisterType
from custom_components.foxess_modbus.connection import InverterConnection
from custom_components.foxess_modbus.const import ENTITY_ID_PREFIX
from custom_components.foxess_modbus.const import FRIENDLY_NAME
from custom_components.foxess_modbus.const import INVERTER_MODEL
from custom_components.foxess_modbus.const import UNIQUE_ID_PREFIX
from custom_components.foxess_modbus.inverter_profiles import INVERTER_PROFILES
from custom_components.foxess_modbus.inverter_profiles import InverterModelConnectionTypeProfile
from custom_components.foxess_modbus.inverter_profiles import SpecialRegisterConfig
from custom_components.foxess_modbus.modbus_controller import ModbusController

_SLAVE = 247
_POLL_RATE = 10

# Modbus exception code 02, which the controller treats as "this register doesn't exist"
_ILLEGAL_ADDRESS = 2


class Entity(ModbusControllerEntity):
    """A stand-in for a sensor: it just tells the controller which addresses it cares about"""

    def __init__(self, addresses: list[int]) -> None:
        self._addresses = addresses
        self.changed_addresses: list[set[int]] = []
        self.connection_changes = 0

    @property
    def addresses(self) -> list[int]:
        return self._addresses

    def update_callback(self, changed_addresses: set[int]) -> None:
        self.changed_addresses.append(changed_addresses)

    def is_connected_changed_callback(self) -> None:
        self.connection_changes += 1


class Harness:
    """A controller wired up to an in-memory inverter"""

    def __init__(self, hass: HomeAssistant, controller: ModbusController, unit: MockModbusUnit) -> None:
        self._hass = hass
        self._polls = 0
        self.controller = controller
        self.unit = unit

    def add_entity(self, *addresses: int) -> Entity:
        entity = Entity(list(addresses))
        self.controller.register_modbus_entity(entity)
        return entity

    async def poll(self) -> None:
        """Let the controller's poll timer fire, and wait for the poll to finish"""
        self._polls += 1
        async_fire_time_changed(self._hass, dt_util.utcnow() + timedelta(seconds=_POLL_RATE * self._polls + 1))
        await self._hass.async_block_till_done()


@pytest.fixture
def make_harness(hass: HomeAssistant) -> Callable[..., Harness]:
    """Builds a controller polling a mock inverter over holding registers"""

    def _make(
        max_read: int = 5,
        special_registers: SpecialRegisterConfig | None = None,
    ) -> Harness:
        # KUARA_H3 has neither charge periods nor a remote control config, so the controller polls exactly the
        # addresses the test asks for and nothing else
        profile = InverterModelConnectionTypeProfile(
            INVERTER_PROFILES[InverterModel.KUARA_H3],
            ConnectionType.AUX,
            RegisterType.HOLDING,
            {None: Inv.KUARA_H3},
            special_registers if special_registers is not None else SpecialRegisterConfig(),
        )
        connection = MockModbusConnection()
        controller = ModbusController(
            hass,
            cast(InverterConnection, connection),
            profile,
            {
                INVERTER_MODEL: "Kuara 6.0-3-H",
                FRIENDLY_NAME: "",
                ENTITY_ID_PREFIX: "",
                UNIQUE_ID_PREFIX: "",
            },
            _SLAVE,
            _POLL_RATE,
            max_read,
        )
        return Harness(hass, controller, connection.for_unit(_SLAVE))

    return _make


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
    harness.unit.fail_read(20, ModbusExceptionError(_ILLEGAL_ADDRESS))

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
    harness.unit.on_write(lambda event: writes.append((event.address, event.values)))

    await harness.controller.write_registers(1, [10, 20, 30])

    assert writes == [(1, [10, 20, 30])]


async def test_repeated_failures_mark_the_inverter_disconnected(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness()
    entity = harness.add_entity(1)
    harness.unit.holding[1] = 5
    harness.unit.fail_read(1, ModbusConnectionError("connection refused"))

    for _ in range(4):
        await harness.poll()
    assert harness.controller.is_connected

    await harness.poll()
    assert not harness.controller.is_connected
    assert harness.controller.current_connection_error == "connection refused"
    assert entity.connection_changes == 1

    harness.unit.fail_read(1, None)
    await harness.poll()

    assert harness.controller.is_connected
    assert harness.controller.current_connection_error is None
    assert entity.connection_changes == 2
