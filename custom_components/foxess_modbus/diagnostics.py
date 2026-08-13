"""Diagnostics download"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .common.types import HassData
from .const import DOMAIN
from .const import FRIENDLY_NAME
from .const import INVERTER_CONN
from .const import INVERTER_MODEL
from .modbus_controller import ModbusController


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return the raw register map of each inverter in this entry, so an issue report shows what it returned"""
    hass_data: HassData = hass.data[DOMAIN]
    return {"inverters": [_inverter(x) for x in hass_data[entry.entry_id]["controllers"]]}


def _inverter(controller: ModbusController) -> dict[str, Any]:
    last_poll = controller.last_poll
    return {
        "friendly_name": controller.inverter_details[FRIENDLY_NAME],
        "model": controller.inverter_details[INVERTER_MODEL],
        "connection_type": controller.inverter_details[INVERTER_CONN],
        "connected": controller.is_connected,
        "connection_error": controller.current_connection_error,
        # Which addresses the last poll actually refreshed: everything else in the map is older than that
        "updated": last_poll.updated if last_poll is not None else [],
        "failed": {key: str(err) for key, err in last_poll.failed.items()} if last_poll is not None else {},
        "registers": controller.raw_registers,
    }
