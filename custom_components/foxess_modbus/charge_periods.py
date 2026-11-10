"""Edit the inverter's two charge periods.

The inverter takes both periods in one write, and stores a disabled period
with start and end 0. The times a disabled period had are remembered here, so
it comes back with them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time

from homeassistant.exceptions import HomeAssistantError
from modbus_connection import ModbusError

from .const import DOMAIN
from .coordinator import FoxEssRuntimeData
from .foxess_inverter import ChargePeriod

PERIODS = (1, 2)


def remember(runtime_data: FoxEssRuntimeData, n: int, end: str, value: time) -> None:
    """Remember a start or end time of period ``n``."""
    runtime_data.charge_period_times[f"{n}_{end}"] = value


def remembered(runtime_data: FoxEssRuntimeData, n: int, end: str) -> time | None:
    """The time remembered for a start or end of period ``n``."""
    value = runtime_data.charge_period_times.get(f"{n}_{end}")
    return value if isinstance(value, time) else None


def current(runtime_data: FoxEssRuntimeData, n: int) -> ChargePeriod:
    """Period ``n`` as it is now, with its remembered times if it is disabled."""
    period = runtime_data.inverter.charge_period(n)
    if period is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="charge_period_unknown",
            translation_placeholders={"period": str(n)},
        )
    if period.force_charge:
        remember(runtime_data, n, "start", period.start)
        remember(runtime_data, n, "end", period.end)
        return period
    return replace(
        period,
        start=remembered(runtime_data, n, "start") or period.start,
        end=remembered(runtime_data, n, "end") or period.end,
    )


async def async_write(runtime_data: FoxEssRuntimeData, periods: dict[int, ChargePeriod]) -> None:
    """Write the given periods, keeping the other one as it is."""
    for n, period in periods.items():
        if period.force_charge and period.start == period.end:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="charge_period_empty",
                translation_placeholders={"period": str(n)},
            )
    merged = [periods.get(n) or current(runtime_data, n) for n in PERIODS]
    try:
        await runtime_data.inverter.async_set_charge_periods(merged)
    except ModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    for n, period in zip(PERIODS, merged, strict=True):
        remember(runtime_data, n, "start", period.start)
        remember(runtime_data, n, "end", period.end)
    runtime_data.settings.async_update_listeners()
