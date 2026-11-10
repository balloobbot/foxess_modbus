"""Settings, and the power remote control runs at."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number import NumberEntity
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.number import NumberMode
from homeassistant.components.number import RestoreNumber
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection import ModbusError

from .const import DOMAIN
from .coordinator import FoxEssConfigEntry
from .entity import FoxEssEntity

PARALLEL_UPDATES = 1


def _current(key: str) -> NumberEntityDescription:
    return NumberEntityDescription(
        key=key,
        translation_key=key,
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
    )


def _soc(key: str) -> NumberEntityDescription:
    return NumberEntityDescription(
        key=key,
        translation_key=key,
        device_class=NumberDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=10,
        native_max_value=100,
        native_step=1,
    )


def _power_limit(key: str) -> NumberEntityDescription:
    return NumberEntityDescription(
        key=key,
        translation_key=key,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=99999,
        native_step=1,
        mode=NumberMode.BOX,
    )


SETTINGS: tuple[NumberEntityDescription, ...] = (
    _current("max_charge_current"),
    _current("max_discharge_current"),
    _soc("min_soc"),
    _soc("max_soc"),
    _soc("min_soc_on_grid"),
    _power_limit("import_power_limit"),
    _power_limit("export_power_limit"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the settings this inverter has, and the remote control numbers."""
    runtime_data = entry.runtime_data
    inverter = runtime_data.inverter
    entities: list[Entity] = [
        FoxEssSettingNumber(entry, description)
        for description in SETTINGS
        if inverter.has(description.key) and inverter.is_writable(description.key)
    ]
    if runtime_data.remote_control is not None:
        capacity = (inverter.capacity or 0) / 1000
        entities += [
            FoxEssRemoteControlPower(entry, key, capacity) for key in ("force_charge_power", "force_discharge_power")
        ]
        # Without a max SoC setting, force charge stops at this one.
        if not inverter.has("max_soc"):
            entities.append(FoxEssRemoteControlMaxSoc(entry))
    async_add_entities(entities)


class FoxEssSettingNumber(FoxEssEntity, NumberEntity):
    """A setting the inverter stores."""

    @property
    def native_value(self) -> float | None:
        """The setting."""
        value: float | None = self.inverter_value
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Write the setting."""
        try:
            await self.runtime_data.inverter.async_set(self.field, value)
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.coordinator.async_update_listeners()


class _RemoteControlNumber(RestoreNumber):
    """A number remote control reads, kept by Home Assistant."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: FoxEssConfigEntry, key: str) -> None:
        runtime_data = entry.runtime_data
        assert runtime_data.remote_control is not None
        self._remote_control = runtime_data.remote_control
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = runtime_data.device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore the last value, and hand it to remote control."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self._apply()

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._attr_native_value = value
        self._apply()
        self.async_write_ha_state()

    def _apply(self) -> None:
        raise NotImplementedError


class FoxEssRemoteControlPower(_RemoteControlNumber):
    """The power force charge or force discharge runs at."""

    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_native_min_value = 0
    _attr_native_step = 0.001

    def __init__(self, entry: FoxEssConfigEntry, key: str, capacity: float) -> None:
        """Set the power of ``key``, up to the inverter's ``capacity`` in kW."""
        super().__init__(entry, key)
        self._key = key
        self._attr_native_max_value = capacity
        self._attr_native_value = capacity

    def _apply(self) -> None:
        watts = None if self._attr_native_value is None else round(self._attr_native_value * 1000)
        if self._key == "force_charge_power":
            self._remote_control.charge_power = watts
        else:
            self._remote_control.discharge_power = watts


class FoxEssRemoteControlMaxSoc(_RemoteControlNumber):
    """The SoC force charge stops at."""

    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, entry: FoxEssConfigEntry) -> None:
        """Set the max SoC of force charge."""
        super().__init__(entry, "force_charge_max_soc")
        self._attr_native_value = 100

    def _apply(self) -> None:
        value = self._attr_native_value
        self._remote_control.max_soc = None if value is None else int(value)
