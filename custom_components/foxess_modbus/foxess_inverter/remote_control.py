"""Force charge and force discharge through the inverter's remote control.

Remote control sets the inverter's active power: positive exports, negative
imports. A watchdog on the inverter ends remote control when it is not
renewed, and the inverter falls back to its work mode.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from .exceptions import FoxEssError
from .layouts import RemoteControlRegisters, WorkMode

if TYPE_CHECKING:
    from .inverter import FoxEssInverter

_LOGGER = logging.getLogger(__name__)

# A PV string above this voltage has sun on it.
PV_SUN_VOLTAGE = 70
# Steer the battery this far below the power it can take, so PV is not clipped.
CHARGE_MARGIN = 200
# Below this battery charge limit, steering leaves no margin for PV.
MIN_CHARGE_LIMIT = 50


class RemoteControlMode(StrEnum):
    """What remote control does."""

    DISABLE = "disable"
    FORCE_CHARGE = "force_charge"
    FORCE_DISCHARGE = "force_discharge"


class RemoteControl:
    """Run force charge or force discharge, one step per readings poll.

    Force discharge exports at the set power. Force charge imports at the set
    power, and stops at the max SoC. Where the inverter reports how much power
    the battery can take, force charge steers the import so the battery
    charges just below that limit. PV then fills the rest instead of being
    clipped.
    """

    def __init__(self, inverter: FoxEssInverter, *, watchdog_seconds: int) -> None:
        """Control ``inverter``. The inverter ends remote control if a step
        does not come within ``watchdog_seconds``.
        """
        if inverter.spec is None or inverter.spec.remote_control is None:
            raise FoxEssError(f"{inverter.model_name} has no remote control")
        self._inverter = inverter
        self._registers: RemoteControlRegisters = inverter.spec.remote_control
        self.watchdog_seconds = watchdog_seconds
        self.mode = RemoteControlMode.DISABLE
        # In W. None is the inverter's rated power.
        self.charge_power: int | None = None
        self.discharge_power: int | None = None
        # Used where the inverter has no max SoC setting of its own.
        self.max_soc: int | None = None
        self._enabled = False
        self._previous_mode = RemoteControlMode.DISABLE
        self._import_power = 0

    async def async_set_mode(self, mode: RemoteControlMode) -> None:
        """Change mode, and take the first step at once."""
        self.mode = mode
        await self.async_step()

    def reset(self) -> None:
        """Forget what was written: the link dropped, or the inverter restarted.

        The next step writes the watchdog and the enable flag again.
        """
        self._enabled = False
        self._previous_mode = RemoteControlMode.DISABLE

    async def async_step(self) -> None:
        """Take one step. Call after each readings poll."""
        try:
            if self.mode is RemoteControlMode.FORCE_CHARGE:
                await self._async_charge()
            elif self.mode is RemoteControlMode.FORCE_DISCHARGE:
                await self._async_discharge()
            else:
                await self._async_disable()
        finally:
            self._previous_mode = self.mode

    def _limit(self, power: int | None) -> int:
        capacity = self._inverter.capacity or 0
        return capacity if power is None or power > capacity else power

    async def _async_discharge(self) -> None:
        await self._async_enable(WorkMode.FEED_IN_FIRST)
        await self._async_write_active_power(self._limit(self.discharge_power))

    async def _async_charge(self) -> None:
        inverter = self._inverter
        socs = [
            soc
            for name in ("battery_soc", "battery_soc_1", "battery_soc_2")
            if (soc := inverter.get(name)) is not None
        ]
        max_soc = self.max_soc if self.max_soc is not None else inverter.get("max_soc")
        # The inverter does not stop at the max SoC by itself.
        if socs and max_soc is not None and max(socs) >= max_soc:
            _LOGGER.debug("Force charge: SoC %s%% reached %s%%", max(socs), max_soc)
            await self._async_disable(WorkMode.BACK_UP)
            return

        max_import = self._limit(self.charge_power)
        # Without sun there is nothing to steer around: charge at full power.
        if not self._has_sun():
            await self._async_enable(WorkMode.BACK_UP)
            await self._async_write_active_power(-max_import)
            return

        limit = inverter.get("battery_charge_power_limit")
        battery_power = inverter.get("battery_power")
        if limit is None or battery_power is None:
            await self._async_enable(WorkMode.BACK_UP)
            await self._async_write_active_power(-max_import)
            return

        limit = abs(int(limit))
        charging = abs(round(battery_power * 1000))
        if limit < MIN_CHARGE_LIMIT:
            _LOGGER.debug("Force charge: battery takes %s W, using Back-up", limit)
            await self._async_disable(WorkMode.BACK_UP)
            return

        if self._previous_mode is not RemoteControlMode.FORCE_CHARGE:
            # Import nothing for one step: the battery then charges from PV
            # alone, which shows how much PV there is.
            self._import_power = 0
        else:
            setpoint = max(limit - CHARGE_MARGIN, MIN_CHARGE_LIMIT)
            previous = self._import_power
            error = setpoint - charging
            if previous > setpoint:
                new = setpoint
            else:
                # PV recovers as the import backs off, so step a bit harder
                # while backing off.
                new = previous + int((1.5 if error < 0 else 1.0) * error)
            # Pause at 0 W when switching between import and export.
            if (previous > 0 > new) or (previous < 0 < new):
                new = 0
            else:
                new = max(min(new, max_import), -max_import)
            _LOGGER.debug(
                "Force charge: battery %s W, limit %s W, import %s W -> %s W",
                charging,
                limit,
                previous,
                new,
            )
            self._import_power = new

        await self._async_enable(WorkMode.BACK_UP)
        await self._async_write_active_power(-self._import_power)

    def _has_sun(self) -> bool:
        return any(
            (voltage := self._inverter.get(f"pv{n}_voltage")) is not None
            and voltage > PV_SUN_VOLTAGE
            for n in range(1, 7)
        )

    async def _async_enable(self, fallback: WorkMode) -> None:
        """Turn remote control on, with the work mode to fall back to."""
        await self._async_ensure_work_mode(fallback)
        if self._enabled:
            return
        self._enabled = True
        # These registers refuse a multi-register write.
        unit = self._inverter.modbus_unit
        await unit.write_register(self._registers.timeout, self.watchdog_seconds)
        await unit.write_register(self._registers.enable, 1)

    async def _async_disable(self, work_mode: WorkMode | None = None) -> None:
        """Turn remote control off, if this object turned it on.

        The FoxESS app's strategy periods use remote control too. Turning it
        off when this object did not turn it on would end such a period.
        After a restart the watchdog ends what was left on.
        """
        if self._enabled:
            self._enabled = False
            await self._inverter.modbus_unit.write_register(self._registers.enable, 0)
        if work_mode is not None:
            await self._async_ensure_work_mode(work_mode)

    async def _async_ensure_work_mode(self, mode: WorkMode) -> None:
        if (
            not self._inverter.has("work_mode")
            or self._inverter.get("work_mode") is mode
        ):
            return
        await self._inverter.async_set_work_mode(mode)

    async def _async_write_active_power(self, power: int) -> None:
        """Write the active power in W: positive exports, negative imports."""
        unit = self._inverter.modbus_unit
        if self._registers.active_power_words == 1:
            await unit.write_register(self._registers.active_power, power & 0xFFFF)
            return
        word = power & 0xFFFFFFFF
        await unit.write_registers(
            self._registers.active_power, [word >> 16, word & 0xFFFF]
        )
