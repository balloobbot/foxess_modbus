"""The base of every FoxESS entity."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FoxEssConfigEntry
from .coordinator import FoxEssCoordinator
from .coordinator import FoxEssRuntimeData


class FoxEssEntity(CoordinatorEntity[FoxEssCoordinator]):
    """An entity backed by one of the inverter's values."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: FoxEssConfigEntry,
        description: EntityDescription,
        field: str | None = None,
    ) -> None:
        """Back the entity with inverter value ``field``, by default its key."""
        runtime_data = entry.runtime_data
        self.field = field or description.key
        super().__init__(runtime_data.coordinator_for(self.field))
        self.entity_description = description
        self.runtime_data: FoxEssRuntimeData = runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = runtime_data.device_info(entry)

    @property
    def inverter_value(self) -> Any:
        """The current value of the backing field."""
        return self.runtime_data.inverter.get(self.field)

    @property
    def available(self) -> bool:
        """Whether the part this value is read with answered the last poll."""
        if not super().available or self.coordinator.data is None:
            return False
        return self.runtime_data.inverter.part_of(self.field) not in self.coordinator.data.failed
