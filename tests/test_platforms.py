"""Writing settings, the work mode, remote control and charge periods."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from modbus_connection import IllegalDataValueError
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import entry_for
from .conftest import seed_h3
from .conftest import seed_model
from .conftest import state

type Setup = Callable[..., Awaitable[MockConfigEntry]]


async def _read(unit: MockModbusUnit, address: int, count: int = 1) -> list[int]:
    return await unit.read_holding_registers(address, count)


async def test_sets_a_setting(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    await setup_entry()
    entity_id = "number.h3_10_0_e_max_state_of_charge"
    assert state(hass, entity_id) == "100"

    await hass.services.async_call("number", "set_value", {ATTR_ENTITY_ID: entity_id, "value": 90}, blocking=True)

    assert await _read(unit, 41010) == [90]
    assert state(hass, entity_id) == "90"


async def test_a_refused_write_raises(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    await setup_entry()
    unit.fail_write(41010, IllegalDataValueError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value", {ATTR_ENTITY_ID: "number.h3_10_0_e_max_state_of_charge", "value": 90}, blocking=True
        )


async def test_work_mode_and_force_charge(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    await setup_entry()
    entity_id = "select.h3_10_0_e_work_mode"
    work_mode = hass.states.get(entity_id)
    assert work_mode is not None
    assert work_mode.state == "self_use"
    assert work_mode.attributes["options"] == [
        "self_use",
        "feed_in_first",
        "back_up",
        "peak_shaving",
        "force_charge",
        "force_discharge",
    ]

    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: entity_id, "option": "feed_in_first"}, blocking=True
    )
    assert await _read(unit, 41000) == [1]

    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: entity_id, "option": "force_discharge"}, blocking=True
    )
    assert state(hass, entity_id) == "force_discharge"
    assert await _read(unit, 44000) == [1]
    # Full power: the 10 kW the H3-10.0 is rated for.
    assert await _read(unit, 44002, 2) == [0, 10000]

    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: entity_id, "option": "self_use"}, blocking=True
    )
    assert await _read(unit, 44000) == [0]
    assert await _read(unit, 41000) == [0]


async def test_force_power_is_a_number(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    await setup_entry()
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.h3_10_0_e_force_discharge_power", "value": 2.5},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.h3_10_0_e_work_mode", "option": "force_discharge"},
        blocking=True,
    )
    assert await _read(unit, 44002, 2) == [0, 2500]


def _seed_h1_g2(unit: MockModbusUnit) -> None:
    seed_model(unit, "H1-5.0-E-G2", packed=True)
    unit.holding[36001] = [0x150, 0x150, 0x150]
    # Period 1: 02:30 to 05:00 from the grid. Period 2: off.
    unit.holding[41001] = [1, (2 << 8) | 30, 5 << 8, 0, 0, 0]


async def test_charge_periods(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    _seed_h1_g2(unit)
    await setup_entry(entry_for("H1-5.0-E-G2"))
    prefix = "h1_5_0_e_g2_charge_period"
    assert state(hass, f"time.{prefix}_1_start") == "02:30:00"
    assert state(hass, f"switch.{prefix}_1_force_charge") == "on"
    assert state(hass, f"switch.{prefix}_1_charge_from_grid") == "on"
    assert state(hass, f"switch.{prefix}_2_force_charge") == "off"

    # A disabled period remembers a time without writing it.
    await hass.services.async_call(
        "time", "set_value", {ATTR_ENTITY_ID: f"time.{prefix}_2_start", "time": "13:00"}, blocking=True
    )
    await hass.services.async_call(
        "time", "set_value", {ATTR_ENTITY_ID: f"time.{prefix}_2_end", "time": "14:15"}, blocking=True
    )
    assert await _read(unit, 41004, 3) == [0, 0, 0]
    assert state(hass, f"time.{prefix}_2_start") == "13:00:00"

    # Turning it on writes both periods, with the remembered times.
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: f"switch.{prefix}_2_force_charge"}, blocking=True
    )
    assert await _read(unit, 41001, 6) == [1, (2 << 8) | 30, 5 << 8, 0, 13 << 8, (14 << 8) | 15]

    # Turning period 1 off keeps its times for when it comes back.
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: f"switch.{prefix}_1_force_charge"}, blocking=True
    )
    assert await _read(unit, 41001, 3) == [1, 0, 0]
    assert state(hass, f"time.{prefix}_1_start") == "02:30:00"


async def test_h1_lan_runs_remote_control_without_a_work_mode(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup
) -> None:
    seed_model(unit, "H1-5.0-E")
    unit.holding[31024] = 50
    await setup_entry(entry_for("H1-5.0-E", adapter="direct"))

    assert hass.states.get("select.h1_5_0_e_work_mode") is None
    assert state(hass, "number.h1_5_0_e_force_charge_max_state_of_charge") == "100"

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.h1_5_0_e_force_charge_mode", "option": "force_charge"},
        blocking=True,
    )
    assert await _read(unit, 44000) == [1]
    assert await _read(unit, 44002) == [(-5000) & 0xFFFF]


async def test_h1_lan_integrates_the_energy_it_does_not_count(
    hass: HomeAssistant,
    unit: MockModbusUnit,
    setup_entry: Setup,
    freezer: FrozenDateTimeFactory,
) -> None:
    seed_model(unit, "H1-5.0-E")
    unit.holding[31014] = 3600  # exporting 3.6 kW
    await setup_entry(entry_for("H1-5.0-E", adapter="direct"))
    entity_id = "sensor.h1_5_0_e_feed_in"
    assert state(hass, entity_id) == "0.0"

    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # 3.6 kW for 10 s.
    assert state(hass, entity_id) == "0.01"
