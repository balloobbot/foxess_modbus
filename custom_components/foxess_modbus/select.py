"""The work mode, and force charge and force discharge."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.components.select import SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection import ModbusError

from .const import DOMAIN
from .coordinator import FoxEssConfigEntry
from .entity import FoxEssEntity
from .foxess_inverter import RemoteControlMode
from .foxess_inverter import WorkMode

PARALLEL_UPDATES = 1

_FORCE_MODES = [RemoteControlMode.FORCE_CHARGE, RemoteControlMode.FORCE_DISCHARGE]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the work mode select, or the remote control one if there is none."""
    runtime_data = entry.runtime_data
    entities: list[Entity] = []
    if runtime_data.inverter.has("work_mode"):
        entities.append(
            FoxEssWorkModeSelect(entry, SelectEntityDescription(key="work_mode", translation_key="work_mode"))
        )
    elif runtime_data.remote_control is not None:
        entities.append(
            FoxEssRemoteControlSelect(
                entry,
                SelectEntityDescription(key="force_charge_mode", translation_key="force_charge_mode"),
            )
        )
    async_add_entities(entities)


class FoxEssWorkModeSelect(FoxEssEntity, SelectEntity):
    """The work mode, with force charge and force discharge where remote
    control can do them.
    """

    def __init__(self, entry: FoxEssConfigEntry, description: SelectEntityDescription) -> None:
        """Offer the inverter's work modes."""
        super().__init__(entry, description)
        self._remote_control = entry.runtime_data.remote_control
        self._attr_options = [mode.value for mode in entry.runtime_data.inverter.work_modes] + (
            [mode.value for mode in _FORCE_MODES] if self._remote_control else []
        )

    @property
    def current_option(self) -> str | None:
        """The force mode while one runs, else the work mode."""
        if self._remote_control is not None and self._remote_control.mode is not RemoteControlMode.DISABLE:
            return self._remote_control.mode.value
        mode: WorkMode | None = self.inverter_value
        return None if mode is None else mode.value

    async def async_select_option(self, option: str) -> None:
        """Run a force mode, or stop it and set the work mode."""
        try:
            if option in RemoteControlMode.__members__.values():
                assert self._remote_control is not None
                await self._remote_control.async_set_mode(RemoteControlMode(option))
            else:
                if self._remote_control is not None:
                    await self._remote_control.async_set_mode(RemoteControlMode.DISABLE)
                await self.runtime_data.inverter.async_set_work_mode(WorkMode(option))
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()


class FoxEssRemoteControlSelect(SelectEntity):
    """Force charge and force discharge, for an inverter with no work mode."""

    _attr_has_entity_name = True

    def __init__(self, entry: FoxEssConfigEntry, description: SelectEntityDescription) -> None:
        """Run remote control of ``entry``'s inverter."""
        runtime_data = entry.runtime_data
        assert runtime_data.remote_control is not None
        self._remote_control = runtime_data.remote_control
        self.entity_description = description
        self._attr_options = [mode.value for mode in RemoteControlMode]
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = runtime_data.device_info(entry)

    @property
    def current_option(self) -> str:
        """The mode remote control runs in."""
        return self._remote_control.mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the mode."""
        try:
            await self._remote_control.async_set_mode(RemoteControlMode(option))
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()
