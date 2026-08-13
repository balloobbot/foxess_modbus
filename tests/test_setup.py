"""The one test which sets the integration up in Home Assistant, end to end"""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.foxess_modbus.common.types import ConnectionType
from custom_components.foxess_modbus.common.types import InverterModel
from custom_components.foxess_modbus.const import ADAPTER_ID
from custom_components.foxess_modbus.const import CONFIG_SAVE_TIME
from custom_components.foxess_modbus.const import DOMAIN
from custom_components.foxess_modbus.const import ENTITY_ID_PREFIX
from custom_components.foxess_modbus.const import FRIENDLY_NAME
from custom_components.foxess_modbus.const import HOST
from custom_components.foxess_modbus.const import INVERTER_BASE
from custom_components.foxess_modbus.const import INVERTER_CONN
from custom_components.foxess_modbus.const import INVERTER_MODEL
from custom_components.foxess_modbus.const import INVERTERS
from custom_components.foxess_modbus.const import MODBUS_SLAVE
from custom_components.foxess_modbus.const import MODBUS_TYPE
from custom_components.foxess_modbus.const import TCP
from custom_components.foxess_modbus.const import UNIQUE_ID_PREFIX
from custom_components.foxess_modbus.flow.flow_handler import FlowHandler

_SLAVE = 247
# What network_other merges in for TCP
_POLL_RATE = 15

# A Kuara H3 behind a generic Ethernet adapter, in the shape the config flow saves
_INVERTER: dict[str, Any] = {
    ADAPTER_ID: "network_other",
    INVERTER_BASE: InverterModel.KUARA_H3,
    INVERTER_MODEL: "Kuara 6.0-3-H",
    INVERTER_CONN: ConnectionType.AUX,
    MODBUS_SLAVE: _SLAVE,
    MODBUS_TYPE: TCP,
    HOST: "1.2.3.4:502",
    ENTITY_ID_PREFIX: "",
    UNIQUE_ID_PREFIX: "",
    FRIENDLY_NAME: "",
}


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} was never created"
    return state.state


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setting_up_the_entry_creates_sensors_which_read_the_inverter(hass: HomeAssistant) -> None:
    connection = MockModbusConnection()
    unit = connection.for_unit(_SLAVE)
    unit.holding[31002] = 1234  # pv1_power, scale 0.001
    unit.holding[32000] = [0, 4321]  # solar_energy_total, high word then low, scale 0.1

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=FlowHandler.VERSION,
        data={INVERTERS: {"inverter-1": _INVERTER}, CONFIG_SAVE_TIME: dt_util.utcnow()},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.foxess_modbus.build_connection", return_value=connection):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        # The platforms ran and built this model's entities, rather than the entry loading with nothing in it.
        # Nothing has been polled yet, so the sensor has no value to show
        assert _state(hass, "sensor.pv1_power") == "unknown"

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=_POLL_RATE + 1))
        await hass.async_block_till_done(wait_background_tasks=True)

        # The value came off the wire, through the controller's register cache, and out of the sensor's scaling
        assert float(_state(hass, "sensor.pv1_power")) == pytest.approx(1.234)
        # ...including one split over two registers
        assert float(_state(hass, "sensor.solar_energy_total")) == pytest.approx(432.1)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
