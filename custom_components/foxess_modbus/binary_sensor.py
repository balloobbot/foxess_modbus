"""Whether the inverter answers."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FoxEssConfigEntry
from .coordinator import FoxEssCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the connection sensor."""
    async_add_entities([FoxEssConnectionSensor(entry)])


class FoxEssConnectionSensor(CoordinatorEntity[FoxEssCoordinator], BinarySensorEntity):
    """On while the inverter answers its polls."""

    _attr_has_entity_name = True
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: FoxEssConfigEntry) -> None:
        """Follow the readings poll of ``entry``."""
        super().__init__(entry.runtime_data.readings)
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_device_info = entry.runtime_data.device_info(entry)

    @property
    def available(self) -> bool:
        """Always available: being off is what it reports."""
        return True

    @property
    def is_on(self) -> bool:
        """Whether the last poll was answered."""
        return self.coordinator.last_update_success
