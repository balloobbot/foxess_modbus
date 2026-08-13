"""Tests for which entities survive the inverter going away"""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.foxess_modbus.const import ENTITY_ID_PREFIX
from custom_components.foxess_modbus.const import FRIENDLY_NAME
from custom_components.foxess_modbus.const import UNIQUE_ID_PREFIX
from custom_components.foxess_modbus.entities.modbus_battery_sensor import ModbusBatterySensor
from custom_components.foxess_modbus.entities.modbus_battery_sensor import ModbusBatterySensorDescription
from custom_components.foxess_modbus.entities.modbus_sensor import ModbusSensor
from custom_components.foxess_modbus.entities.modbus_sensor import ModbusSensorDescription

_ADDRESS = 1
_BMS_CONNECT_STATE_ADDRESS = 2


class EntityStateClassSensor(ModbusSensor):
    """Stands in for IntegrationSensor, which declares its state class on the entity, not the description"""

    _attr_state_class = SensorStateClass.TOTAL


def _controller(*, is_connected: bool = True) -> MagicMock:
    controller = MagicMock()
    controller.is_connected = is_connected
    controller.inverter_details = {ENTITY_ID_PREFIX: "", UNIQUE_ID_PREFIX: "", FRIENDLY_NAME: ""}
    controller.read.return_value = None  # Nothing polled yet
    return controller


def _sensor(
    state_class: SensorStateClass | None,
    *,
    is_connected: bool = True,
    cls: type[ModbusSensor] = ModbusSensor,
    controller: MagicMock | None = None,
) -> ModbusSensor:
    if controller is None:
        controller = _controller(is_connected=is_connected)
    description = ModbusSensorDescription(key="test", addresses=[], state_class=state_class)
    sensor = cls(controller, description, [_ADDRESS], None)
    sensor.schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    return sensor


def _battery_sensor(state_class: SensorStateClass, controller: MagicMock) -> ModbusBatterySensor:
    description = ModbusBatterySensorDescription(
        key="test", addresses=[], bms_connect_state_address=[], state_class=state_class
    )
    sensor = ModbusBatterySensor(controller, description, [_ADDRESS], _BMS_CONNECT_STATE_ADDRESS)
    sensor.schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    return sensor


@pytest.mark.parametrize(
    ("state_class", "available_when_disconnected"),
    [
        (SensorStateClass.TOTAL, True),
        (SensorStateClass.TOTAL_INCREASING, True),
        (SensorStateClass.MEASUREMENT, False),
        (None, False),
    ],
)
def test_accumulators_outlive_the_inverter(
    state_class: SensorStateClass | None, available_when_disconnected: bool
) -> None:
    # A disconnection is routine (the inverter is off overnight), and blanking a total would gap the statistics
    assert _sensor(state_class, is_connected=False).available == available_when_disconnected
    assert _sensor(state_class, is_connected=True).available


def test_a_state_class_set_on_the_entity_also_counts() -> None:
    assert _sensor(None, is_connected=False, cls=EntityStateClassSensor).available


@pytest.mark.parametrize(
    ("state_class", "value_after"),
    [(SensorStateClass.TOTAL, 42), (SensorStateClass.MEASUREMENT, None)],
)
def test_a_total_holds_its_value_when_the_register_stops_reading(
    state_class: SensorStateClass, value_after: int | None
) -> None:
    controller = _controller()
    sensor = _sensor(state_class, controller=controller)

    controller.read.return_value = 42
    sensor._address_updated()  # noqa: SLF001
    assert sensor.native_value == 42

    # Unavailable is only half of it: a total which reads unknown through a successful poll gaps the statistics too
    controller.read.return_value = None
    sensor._address_updated()  # noqa: SLF001
    assert sensor.native_value == value_after


@pytest.mark.parametrize(
    ("state_class", "value_when_offline"),
    [(SensorStateClass.TOTAL, 42), (SensorStateClass.MEASUREMENT, None)],
)
def test_an_offline_bms_does_not_blank_a_total(state_class: SensorStateClass, value_when_offline: int | None) -> None:
    bms_connect_state = 1

    def read(address: int | list[int], *, signed: bool) -> int:  # noqa: ARG001
        return bms_connect_state if address == _BMS_CONNECT_STATE_ADDRESS else 42

    controller = _controller()
    controller.read = read
    sensor = _battery_sensor(state_class, controller)

    sensor._address_updated()  # noqa: SLF001
    assert sensor.native_value == 42

    bms_connect_state = 0  # BMS offline
    sensor._address_updated()  # noqa: SLF001
    assert sensor.native_value == value_when_offline


async def test_a_sensor_added_after_a_poll_shows_the_current_value(hass: HomeAssistant) -> None:
    controller = _controller()
    controller.read.return_value = 42
    sensor = _sensor(SensorStateClass.MEASUREMENT, controller=controller)
    sensor.hass = hass
    mock_restore_cache_with_extra_data(hass, ())

    await sensor.async_added_to_hass()

    # An entity enabled long after the first poll shouldn't sit at unknown until the next one
    assert sensor.native_value == 42


async def test_a_total_restores_its_value_across_a_restart(hass: HomeAssistant) -> None:
    sensor = _sensor(SensorStateClass.TOTAL)
    sensor.hass = hass
    mock_restore_cache_with_extra_data(
        hass,
        ((State(sensor.entity_id, "123.4"), {"native_value": 123.4, "native_unit_of_measurement": "kWh"}),),
    )

    await sensor.async_added_to_hass()

    # The first poll is a whole poll interval away, and until then the energy dashboard would see a gap
    assert sensor.native_value == 123.4
