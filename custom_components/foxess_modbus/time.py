"""The start and end of each charge period."""

from __future__ import annotations

from dataclasses import replace
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.components.time import TimeEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import charge_periods
from .coordinator import FoxEssConfigEntry
from .entity import FoxEssEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charge period times, if the inverter has charge periods."""
    inverter = entry.runtime_data.inverter
    async_add_entities(
        FoxEssChargePeriodTime(
            entry,
            TimeEntityDescription(
                key=f"charge_period_{n}_{end}",
                translation_key=f"charge_period_{end}",
                translation_placeholders={"period": str(n)},
            ),
            n,
            end,
        )
        for n in charge_periods.PERIODS
        for end in ("start", "end")
        if inverter.has(f"charge_period_{n}_{end}")
    )


class FoxEssChargePeriodTime(FoxEssEntity, TimeEntity, RestoreEntity):
    """When a charge period starts or ends.

    While the period is disabled, this shows and keeps the time it comes back
    with.
    """

    def __init__(
        self,
        entry: FoxEssConfigEntry,
        description: TimeEntityDescription,
        period: int,
        end: str,
    ) -> None:
        """Show the ``end`` ('start' or 'end') of charge period ``period``."""
        super().__init__(entry, description)
        self._period = period
        self._end = end

    async def async_added_to_hass(self) -> None:
        """Restore the time a disabled period comes back with."""
        await super().async_added_to_hass()
        if charge_periods.remembered(self.runtime_data, self._period, self._end):
            return
        if (state := await self.async_get_last_state()) is not None:
            try:
                value = time.fromisoformat(state.state)
            except ValueError:
                return
            charge_periods.remember(self.runtime_data, self._period, self._end, value)

    @property
    def native_value(self) -> time | None:
        """The time, or the one the period comes back with."""
        if self.runtime_data.inverter.get(f"charge_period_{self._period}_force_charge"):
            value: time | None = self.inverter_value
            return value
        return charge_periods.remembered(self.runtime_data, self._period, self._end) or self.inverter_value

    async def async_set_value(self, value: time) -> None:
        """Set the time. A disabled period only remembers it."""
        period = charge_periods.current(self.runtime_data, self._period)
        if not period.force_charge:
            charge_periods.remember(self.runtime_data, self._period, self._end, value)
            self.async_write_ha_state()
            return
        if self._end == "start":
            period = replace(period, start=value)
        else:
            period = replace(period, end=value)
        await charge_periods.async_write(self.runtime_data, {self._period: period})
