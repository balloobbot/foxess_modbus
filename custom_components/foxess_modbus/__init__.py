"""The FoxESS - Modbus integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .adapters import ADAPTERS
from .connection import SERIAL_MESSAGE_SPACING
from .connection import build_params
from .const import CONF_ADAPTER
from .const import CONF_MAX_READ
from .const import CONF_POLL_INTERVAL
from .const import CONF_PROTOCOL
from .const import CONF_UNIT_ID
from .const import DOMAIN
from .const import PROTOCOL_SERIAL
from .const import SETTINGS_INTERVAL
from .coordinator import FoxEssConfigEntry
from .coordinator import FoxEssCoordinator
from .coordinator import FoxEssRuntimeData
from .foxess_inverter import FoxEssInverter
from .foxess_inverter import RemoteControl
from .services import async_setup_services
from .websocket_api import async_setup_websocket_api

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the services and the websocket API."""
    async_setup_services(hass)
    async_setup_websocket_api(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FoxEssConfigEntry) -> bool:
    """Set up an inverter."""
    adapter = ADAPTERS[entry.data[CONF_ADAPTER]]
    protocol = entry.data[CONF_PROTOCOL]
    unit = async_get_unit(hass, entry, build_params(entry.data), entry.data[CONF_UNIT_ID])
    if protocol == PROTOCOL_SERIAL:
        unit.set_message_spacing(SERIAL_MESSAGE_SPACING)
    # The options hold numbers from a number selector, which are floats.
    poll_interval = int(entry.options.get(CONF_POLL_INTERVAL) or adapter.default_poll_interval(protocol))
    inverter = FoxEssInverter(
        unit,
        connection_type=adapter.connection_type,
        max_read=int(entry.options.get(CONF_MAX_READ) or adapter.max_read),
    )
    readings = FoxEssCoordinator(
        hass,
        entry,
        inverter,
        inverter.async_update_readings,
        timedelta(seconds=poll_interval),
        entry.title,
    )
    settings = FoxEssCoordinator(
        hass,
        entry,
        inverter,
        inverter.async_update_settings,
        SETTINGS_INTERVAL,
        f"{entry.title} settings",
    )
    await readings.async_config_entry_first_refresh()
    await settings.async_config_entry_first_refresh()

    remote_control = None
    if inverter.spec is not None and inverter.spec.remote_control is not None:
        # The inverter ends remote control if two polls in a row miss it.
        remote_control = RemoteControl(inverter, watchdog_seconds=2 * poll_interval)
        readings.remote_control = remote_control

    entry.runtime_data = FoxEssRuntimeData(inverter, readings, settings, remote_control)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: FoxEssConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FoxEssConfigEntry) -> bool:
    """Unload an inverter."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
