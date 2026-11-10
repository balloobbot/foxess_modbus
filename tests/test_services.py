"""Services, the websocket command, diagnostics and rounding."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.foxess_modbus.const import CONF_ROUND_VALUES
from custom_components.foxess_modbus.const import DOMAIN

from .conftest import entry_for
from .conftest import seed_h3
from .conftest import state
from .test_platforms import _seed_h1_g2

type Setup = Callable[..., Awaitable[MockConfigEntry]]


async def test_read_and_write_registers(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    seed_h3(unit)
    entry = await setup_entry()

    response = await hass.services.async_call(
        DOMAIN,
        "read_registers",
        {"config_entry_id": entry.entry_id, "start_address": 31000, "count": 2, "type": "holding"},
        blocking=True,
        return_response=True,
    )
    assert response == {"values": {"31000": 3000, "31001": 50}}

    await hass.services.async_call(
        DOMAIN,
        "write_registers",
        {"config_entry_id": entry.entry_id, "start_address": 41009, "values": "11, 99"},
        blocking=True,
    )
    assert await unit.read_holding_registers(41009, 2) == [11, 99]


async def test_update_charge_period(hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup) -> None:
    _seed_h1_g2(unit)
    entry = await setup_entry(entry_for("H1-5.0-E-G2"))

    await hass.services.async_call(
        DOMAIN,
        "update_charge_period",
        {
            "config_entry_id": entry.entry_id,
            "charge_period": "2",
            "enable_force_charge": True,
            "enable_charge_from_grid": False,
            "start": "13:00",
            "end": "14:15",
        },
        blocking=True,
    )
    assert await unit.read_holding_registers(41001, 6) == [1, (2 << 8) | 30, 5 << 8, 0, 13 << 8, (14 << 8) | 15]

    await hass.services.async_call(
        DOMAIN,
        "update_all_charge_periods",
        {
            "config_entry_id": entry.entry_id,
            "charge_periods": [
                {"enable_force_charge": False, "enable_charge_from_grid": False},
                {"enable_force_charge": True, "enable_charge_from_grid": True, "start": "01:00", "end": "02:00"},
            ],
        },
        blocking=True,
    )
    assert await unit.read_holding_registers(41001, 6) == [0, 0, 0, 1, 1 << 8, 2 << 8]


async def test_charge_period_services_need_charge_periods(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup
) -> None:
    seed_h3(unit)
    entry = await setup_entry()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "update_charge_period",
            {
                "config_entry_id": entry.entry_id,
                "charge_period": 1,
                "enable_force_charge": False,
                "enable_charge_from_grid": False,
            },
            blocking=True,
        )


async def test_websocket_lists_the_charge_period_entities(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup, hass_ws_client: WebSocketGenerator
) -> None:
    _seed_h1_g2(unit)
    entry = await setup_entry(entry_for("H1-5.0-E-G2"))
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    assert device is not None
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/get_charge_periods", "inverter": device.id})
    result = await client.receive_json()

    assert result["success"]
    assert result["result"]["friendly_name"] == "H1-5.0-E-G2"
    assert result["result"]["charge_periods"][0] == {
        "period_start_entity_id": "time.h1_5_0_e_g2_charge_period_1_start",
        "period_end_entity_id": "time.h1_5_0_e_g2_charge_period_1_end",
        "enable_force_charge_entity_id": "switch.h1_5_0_e_g2_charge_period_1_force_charge",
        "enable_charge_from_grid_entity_id": "switch.h1_5_0_e_g2_charge_period_1_charge_from_grid",
    }


async def test_diagnostics(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup, hass_client: ClientSessionGenerator
) -> None:
    seed_h3(unit)
    entry = await setup_entry()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics["model"] == "H3-10.0-E"
    assert diagnostics["layout"] == "h3"
    assert diagnostics["entry"]["data"]["host"] == "**REDACTED**"
    assert diagnostics["registers"]["holding"]["31002"] == 1500
    assert "live" in diagnostics["updated"]


async def test_rounding_smooths_values(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Setup, freezer: FrozenDateTimeFactory
) -> None:
    seed_h3(unit)
    entry = entry_for("H3-10.0-E")
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_ROUND_VALUES: True})
    await setup_entry(entry)
    entity_id = "sensor.h3_10_0_e_pv1_voltage"
    assert state(hass, entity_id) == "300"

    # A small wobble does not move the value.
    unit.holding[31000] = 3004
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert state(hass, entity_id) == "300"
