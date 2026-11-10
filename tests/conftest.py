"""Fixtures: a mock inverter behind a mock Modbus connection."""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusConnection
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.foxess_modbus.const import CONF_ADAPTER
from custom_components.foxess_modbus.const import CONF_PROTOCOL
from custom_components.foxess_modbus.const import CONF_UNIT_ID
from custom_components.foxess_modbus.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


def state(hass: HomeAssistant, entity_id: str) -> str:
    """The state of an entity that has to exist."""
    entity = hass.states.get(entity_id)
    assert entity is not None, entity_id
    return entity.state


def seed_model(unit: MockModbusUnit, name: str, *, packed: bool = False) -> None:
    """Put a model name at holding 30000, as the inverter does."""
    if packed:
        padded = name.encode() + b"\0" * (30 - len(name))
        words = [(padded[i] << 8) | padded[i + 1] for i in range(0, 30, 2)]
    else:
        words = [ord(c) for c in name] + [0] * (15 - len(name))
    unit.holding[30000] = words


def seed_h3(unit: MockModbusUnit) -> None:
    """An H3 on firmware 1.95, exporting from PV and charging its battery."""
    seed_model(unit, " H3-10.0-E")
    unit.holding[30016] = [150, 140, 0x195]
    unit.holding[31000] = [3000, 50, 1500, 2900, 40, 1160]  # PV1, PV2
    unit.holding[31026] = [500, 400, 300]  # grid CT: exporting
    unit.holding[31036] = 0xFC18  # battery -1 kW: charging
    unit.holding[31038] = 60  # SoC
    unit.holding[31042] = 1  # BMS connected
    unit.holding[32000] = [0, 12345, 123]  # solar total 1234.5 kWh, today 12.3
    unit.holding[41000] = 0  # self use
    unit.holding[41007] = [250, 250, 10, 100, 15]


@pytest.fixture
def connection() -> MockModbusConnection:
    """The mock link."""
    return MockModbusConnection()


@pytest.fixture
def unit(connection: MockModbusConnection) -> MockModbusUnit:
    """The mock inverter, at the default unit id."""
    return connection.for_unit(247)


@pytest.fixture
def patch_modbus(unit: MockModbusUnit) -> Generator[None]:
    """Hand out the mock unit where the modbus integration would."""

    @asynccontextmanager
    async def temporary_unit(*args: Any) -> AsyncIterator[MockModbusUnit]:
        yield unit

    def get_unit(*args: Any) -> MockModbusUnit:
        return unit

    with (
        patch("custom_components.foxess_modbus.async_get_unit", get_unit),
        patch("custom_components.foxess_modbus.config_flow.async_get_temporary_unit", temporary_unit),
    ):
        yield


def entry_for(title: str, adapter: str = "elfin_ew11") -> MockConfigEntry:
    """A config entry for an inverter titled with its model."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id="tcp:192.168.1.50:502:247",
        version=2,
        data={
            CONF_ADAPTER: adapter,
            CONF_PROTOCOL: "tcp",
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 502,
            CONF_UNIT_ID: 247,
        },
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """An H3 behind a network adapter."""
    return entry_for("H3-10.0-E")


@pytest.fixture
def setup_entry(hass: HomeAssistant, config_entry: MockConfigEntry, patch_modbus: None) -> Callable[..., Any]:
    """Set up a config entry, by default the H3."""

    async def setup(entry: MockConfigEntry = config_entry) -> MockConfigEntry:
        if hass.config_entries.async_get_entry(entry.entry_id) is None:
            entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return setup
