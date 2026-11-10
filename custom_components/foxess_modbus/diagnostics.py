"""Diagnostics: what the inverter is, and its raw registers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusError

from .coordinator import FoxEssConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: FoxEssConfigEntry) -> dict[str, Any]:
    """The inverter's identity, its last poll, and every register it reads."""
    runtime_data = entry.runtime_data
    inverter = runtime_data.inverter
    report = runtime_data.readings.data
    registers: Any
    try:
        registers = await inverter.async_read_raw()
    except ModbusError as err:
        registers = {"error": str(err)}
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "model": inverter.model_name,
        "layout": inverter.layout,
        "manager_version": str(inverter.manager_version),
        "refused_fields": inverter.refused_fields,
        "updated": sorted(report.updated) if report else [],
        "failed": {name: str(err) for name, err in report.failed.items()} if report else {},
        "registers": registers,
    }
