"""Tests for which entities survive the inverter going away"""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass

from custom_components.foxess_modbus.const import ENTITY_ID_PREFIX
from custom_components.foxess_modbus.const import FRIENDLY_NAME
from custom_components.foxess_modbus.const import UNIQUE_ID_PREFIX
from custom_components.foxess_modbus.entities.modbus_sensor import ModbusSensor
from custom_components.foxess_modbus.entities.modbus_sensor import ModbusSensorDescription


class EntityStateClassSensor(ModbusSensor):
    """Stands in for IntegrationSensor, which declares its state class on the entity, not the description"""

    _attr_state_class = SensorStateClass.TOTAL


def _sensor(
    state_class: SensorStateClass | None,
    *,
    is_connected: bool,
    cls: type[ModbusSensor] = ModbusSensor,
) -> ModbusSensor:
    controller = MagicMock()
    controller.is_connected = is_connected
    controller.inverter_details = {ENTITY_ID_PREFIX: "", UNIQUE_ID_PREFIX: "", FRIENDLY_NAME: ""}
    description = ModbusSensorDescription(key="test", addresses=[], state_class=state_class)
    return cls(controller, description, [1], None)


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
