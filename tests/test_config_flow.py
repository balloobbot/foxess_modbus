"""The config flow."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DEVICE
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.foxess_modbus.const import CONF_ADAPTER
from custom_components.foxess_modbus.const import CONF_MAX_READ
from custom_components.foxess_modbus.const import CONF_POLL_INTERVAL
from custom_components.foxess_modbus.const import CONF_PROTOCOL
from custom_components.foxess_modbus.const import CONF_ROUND_VALUES
from custom_components.foxess_modbus.const import CONF_UNIT_ID
from custom_components.foxess_modbus.const import DOMAIN

from .conftest import seed_h3
from .conftest import seed_model

pytestmark = pytest.mark.usefixtures("patch_modbus")


async def _to_network_form(hass: HomeAssistant, adapter: str = "elfin_ew11") -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"adapter_type": "network"})
    assert result["step_id"] == "adapter"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADAPTER: adapter})
    assert result["step_id"] == "network"
    return result["flow_id"]


async def test_adds_an_inverter_behind_a_network_adapter(hass: HomeAssistant, unit: MockModbusUnit) -> None:
    seed_h3(unit)
    flow_id = await _to_network_form(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROTOCOL: "udp", CONF_HOST: "192.168.1.50", CONF_PORT: 502, CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "H3-10.0-E"
    assert result["data"] == {
        CONF_ADAPTER: "elfin_ew11",
        CONF_PROTOCOL: "udp",
        CONF_HOST: "192.168.1.50",
        CONF_PORT: 502,
        CONF_UNIT_ID: 247,
    }
    assert result["result"].unique_id == "udp:192.168.1.50:502:247"


async def test_a_direct_connection_skips_the_adapter_step(hass: HomeAssistant, unit: MockModbusUnit) -> None:
    seed_model(unit, "H1-5.0-E")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"adapter_type": "direct"})
    assert result["step_id"] == "network"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.60", CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROTOCOL] == "tcp"
    assert result["data"][CONF_PORT] == 502


async def test_adds_an_inverter_on_a_serial_port(hass: HomeAssistant, unit: MockModbusUnit) -> None:
    seed_h3(unit)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"adapter_type": "serial"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADAPTER: "dsd_tech_sh_u10"})
    assert result["step_id"] == "serial"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "/dev/ttyUSB0", CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "serial:/dev/ttyUSB0:247"


@pytest.mark.parametrize(
    ("seed", "error"),
    [
        (lambda unit: seed_model(unit, "XYZ-1"), "unsupported_model"),
        (lambda unit: unit.fail_requests(ModbusTimeoutError()), "cannot_connect"),
    ],
)
async def test_shows_why_the_inverter_cannot_be_added(
    hass: HomeAssistant,
    unit: MockModbusUnit,
    seed: Callable[[MockModbusUnit], None],
    error: str,
) -> None:
    seed(unit)
    flow_id = await _to_network_form(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROTOCOL: "tcp", CONF_HOST: "192.168.1.50", CONF_PORT: 502, CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_rejects_a_second_entry_for_the_same_inverter(
    hass: HomeAssistant, unit: MockModbusUnit, config_entry: MockConfigEntry
) -> None:
    seed_h3(unit)
    config_entry.add_to_hass(hass)
    flow_id = await _to_network_form(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROTOCOL: "tcp", CONF_HOST: "192.168.1.50", CONF_PORT: 502, CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigures_the_connection(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Callable[[], Awaitable[MockConfigEntry]]
) -> None:
    seed_h3(unit)
    entry = await setup_entry()

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"adapter_type": "network"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADAPTER: "usr_w610"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROTOCOL: "udp", CONF_HOST: "192.168.1.51", CONF_PORT: 8899, CONF_UNIT_ID: 247}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.1.51"
    assert entry.data[CONF_ADAPTER] == "usr_w610"
    assert entry.unique_id == "udp:192.168.1.51:8899:247"


async def test_options(
    hass: HomeAssistant, unit: MockModbusUnit, setup_entry: Callable[[], Awaitable[MockConfigEntry]]
) -> None:
    seed_h3(unit)
    entry = await setup_entry()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 30, CONF_MAX_READ: 50, CONF_ROUND_VALUES: True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_POLL_INTERVAL: 30, CONF_MAX_READ: 50, CONF_ROUND_VALUES: True}
    assert entry.runtime_data.inverter.max_read == 50
