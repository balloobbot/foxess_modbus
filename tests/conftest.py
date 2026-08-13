"""Shared fixtures for the ModbusController tests"""

from datetime import timedelta
from typing import Callable
from typing import Iterator

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from modbus_connection.mock import MockModbusConnection
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.foxess_modbus.common.entity_controller import ModbusControllerEntity
from custom_components.foxess_modbus.common.types import ConnectionType
from custom_components.foxess_modbus.common.types import Inv
from custom_components.foxess_modbus.common.types import InverterModel
from custom_components.foxess_modbus.common.types import RegisterType
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

    def __init__(
        self,
        hass: HomeAssistant,
        controller: ModbusController,
        connection: MockModbusConnection,
        unit: MockModbusUnit,
    ) -> None:
        self._hass = hass
        self._polls = 0
        self.controller = controller
        self.connection = connection
        self.unit = unit

    def add_entity(self, *addresses: int) -> Entity:
        entity = Entity(list(addresses))
        self.controller.register_modbus_entity(entity)
        return entity

    async def poll(self) -> None:
        """Let the controller's poll timer fire, and wait for the poll to finish.

        async_track_time_interval dispatches with background=True, and a poll which has to establish the connection
        genuinely suspends, so the refresh is still pending when a plain async_block_till_done() returns.
        """
        self._polls += 1
        async_fire_time_changed(self._hass, dt_util.utcnow() + timedelta(seconds=_POLL_RATE * self._polls + 1))
        await self._hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture
def make_harness(hass: HomeAssistant) -> Iterator[Callable[..., Harness]]:
    """Builds a controller polling a mock inverter over holding registers"""

    controllers: list[ModbusController] = []

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
            connection,
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
        controllers.append(controller)
        return Harness(hass, controller, connection, connection.for_unit(_SLAVE))

    yield _make

    # The controller registers a poll timer with hass, which has to be cancelled before the test ends
    for controller in controllers:
        controller.unload()
