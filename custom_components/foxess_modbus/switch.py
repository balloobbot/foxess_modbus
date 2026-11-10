"""Whether each charge period force charges, and whether it charges from the grid."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import charge_periods
from .coordinator import FoxEssConfigEntry
from .entity import FoxEssEntity

PARALLEL_UPDATES = 1

_FLAGS = ("force_charge", "charge_from_grid")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charge period switches, if the inverter has charge periods."""
    inverter = entry.runtime_data.inverter
    async_add_entities(
        FoxEssChargePeriodSwitch(
            entry,
            SwitchEntityDescription(
                key=f"charge_period_{n}_{flag}",
                translation_key=f"charge_period_{flag}",
                translation_placeholders={"period": str(n)},
            ),
            n,
            flag,
        )
        for n in charge_periods.PERIODS
        for flag in _FLAGS
        if inverter.has(f"charge_period_{n}_{flag}")
    )


class FoxEssChargePeriodSwitch(FoxEssEntity, SwitchEntity):
    """One flag of a charge period."""

    def __init__(
        self,
        entry: FoxEssConfigEntry,
        description: SwitchEntityDescription,
        period: int,
        flag: str,
    ) -> None:
        """Switch ``flag`` of charge period ``period``."""
        super().__init__(entry, description)
        self._period = period
        self._flag = flag

    @property
    def is_on(self) -> bool | None:
        """Whether the flag is set."""
        value: bool | None = self.inverter_value
        return value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the flag."""
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the flag."""
        await self._async_write(False)

    async def _async_write(self, value: bool) -> None:
        period = charge_periods.current(self.runtime_data, self._period)
        if self._flag == "force_charge":
            period = replace(period, force_charge=value)
        else:
            period = replace(period, charge_from_grid=value)
        await charge_periods.async_write(self.runtime_data, {self._period: period})
