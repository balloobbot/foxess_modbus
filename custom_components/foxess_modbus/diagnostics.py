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
    # HA offers the download whatever state the entry is in, and a disabled one - or one whose setup failed - has no
    # controllers to ask. Say so, rather than failing the download of the very thing we asked the user for
    hass_data: HassData = hass.data.get(DOMAIN, {})
    entry_data = hass_data.get(entry.entry_id)
    if entry_data is None:
        return {"loaded": False}

    return {"loaded": True, "inverters": [_inverter(x) for x in entry_data["controllers"]]}


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
