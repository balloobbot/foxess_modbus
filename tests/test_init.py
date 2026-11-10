"""Setting up an inverter, and its sensors."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from modbus_connection import IllegalDataAddressError
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.foxess_modbus.const import DOMAIN

from .conftest import seed_h3
from .conftest import seed_model
from .conftest import state

type Setup = Callable[[], Awaitable[MockConfigEntry]]


async def test_sets_up_an_h3(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    entry = await setup_entry()

    assert entry.state is ConfigEntryState.LOADED
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    assert device is not None
    assert device.manufacturer == "FoxESS"
    assert device.model == "H3-10.0-E"
    assert device.sw_version == "1.95"

    assert state(hass, "sensor.h3_10_0_e_pv1_power") == "1.5"
    assert state(hass, "sensor.h3_10_0_e_pv_power") == "2.66"
    assert state(hass, "sensor.h3_10_0_e_feed_in_power_r") == "0.5"
    assert state(hass, "sensor.h3_10_0_e_battery_charge_power") == "1.0"
    assert state(hass, "sensor.h3_10_0_e_battery_state_of_charge") == "60"
    assert state(hass, "sensor.h3_10_0_e_solar_generation") == "1234.5"
    assert state(hass, "sensor.h3_10_0_e_manager_firmware") == "1.95"
    assert state(hass, "binary_sensor.h3_10_0_e_connection") == "on"
    # Not served by an H3 before 1.80 or after: the H3 has no CT2.
    assert hass.states.get("sensor.h3_10_0_e_ct2_power") is None


async def test_only_served_values_get_entities(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    entry = await setup_entry()
    keys = {
        e.unique_id.removeprefix(f"{entry.entry_id}_")
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    inverter = entry.runtime_data.inverter
    for key in keys:
        assert (
            inverter.has(key)
            or key.endswith("_energy_total")
            or key in ("connection", "force_charge_power", "force_discharge_power")
        ), key


async def test_unsupported_model_fails_setup(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_model(unit, "XYZ-1")
    config_entry = await _setup_failing(hass, setup_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_silent_inverter_retries_setup(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    unit.fail_requests(ModbusTimeoutError())
    config_entry = await _setup_failing(hass, setup_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def _setup_failing(hass: HomeAssistant, setup_entry: Setup) -> MockConfigEntry:
    try:
        return await setup_entry()
    except AssertionError:
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        return entries[0]


async def test_a_failing_part_goes_unavailable_but_totals_hold(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup, freezer: FrozenDateTimeFactory
) -> None:
    seed_h3(unit)
    await setup_entry()

    unit.fail_read(31000, IllegalDataAddressError())
    unit.holding[32002] = 130
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert state(hass, "sensor.h3_10_0_e_pv1_power") == STATE_UNAVAILABLE
    assert state(hass, "sensor.h3_10_0_e_solar_generation_today") == "13.0"


async def test_an_offline_inverter_goes_unavailable_and_comes_back(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup, freezer: FrozenDateTimeFactory
) -> None:
    seed_h3(unit)
    await setup_entry()

    unit.fail_requests(ModbusTimeoutError())
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert state(hass, "sensor.h3_10_0_e_pv1_power") == STATE_UNAVAILABLE
    assert state(hass, "sensor.h3_10_0_e_solar_generation") == "1234.5"
    assert state(hass, "binary_sensor.h3_10_0_e_connection") == "off"

    unit.fail_requests(None)
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert state(hass, "sensor.h3_10_0_e_pv1_power") == "1.5"


async def test_unloads(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    entry = await setup_entry()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
