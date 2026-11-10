"""The websocket command the charge period card uses."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import charge_periods
from .const import DOMAIN
from .coordinator import FoxEssConfigEntry

# The card's fields, and the entity behind each.
_ENTITIES = {
    "period_start_entity_id": (Platform.TIME, "start"),
    "period_end_entity_id": (Platform.TIME, "end"),
    "enable_force_charge_entity_id": (Platform.SWITCH, "force_charge"),
    "enable_charge_from_grid_entity_id": (Platform.SWITCH, "charge_from_grid"),
}


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register the websocket command."""
    websocket_api.async_register_command(hass, websocket_get_charge_periods)


@websocket_api.websocket_command(
    {probatio.Required("type"): f"{DOMAIN}/get_charge_periods", probatio.Required("inverter"): str}
)
@callback
def websocket_get_charge_periods(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The entities of each charge period of an inverter."""
    device = dr.async_get(hass).async_get(msg["inverter"])
    entry: FoxEssConfigEntry | None = (
        hass.config_entries.async_get_entry(device.config_entry_id) if device is not None else None
    )
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Not a loaded FoxESS inverter")
        return
    runtime_data = entry.runtime_data
    registry = er.async_get(hass)
    periods = []
    if runtime_data.inverter.has("charge_period_1_start"):
        for n in charge_periods.PERIODS:
            periods.append(
                {
                    field: registry.async_get_entity_id(
                        platform, DOMAIN, f"{entry.entry_id}_charge_period_{n}_{suffix}"
                    )
                    for field, (platform, suffix) in _ENTITIES.items()
                }
            )
    connection.send_result(msg["id"], {"friendly_name": entry.title, "charge_periods": periods})
