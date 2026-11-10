"""Poll the inverter."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from modbus_connection import ModbusError
from modbus_connection import ModbusTimeoutError
from modbus_connection.model import UpdateReport

from .const import CONF_ROUND_VALUES
from .const import DOMAIN
from .const import MANUFACTURER
from .foxess_inverter import FoxEssInverter
from .foxess_inverter import RemoteControl
from .foxess_inverter import UnsupportedInverterError
from .foxess_inverter.layouts import Poll

_LOGGER = logging.getLogger(__name__)

# After this many polls in a row that nothing answers, drop the link. Some
# adapters keep a socket open while the inverter behind them stops answering.
_TIMEOUTS_BEFORE_RECONNECT = 5


class FoxEssCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Run one of the inverter's poll methods on its own interval."""

    config_entry: FoxEssConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FoxEssConfigEntry,
        inverter: FoxEssInverter,
        poll: Callable[[], Awaitable[UpdateReport]],
        interval: timedelta,
        name: str,
    ) -> None:
        """Poll ``inverter`` with ``poll`` every ``interval``."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=name, update_interval=interval)
        self.inverter = inverter
        self._poll = poll
        self._failing: set[str] = set()
        self._timeouts = 0
        self.remote_control: RemoteControl | None = None

    async def _async_update_data(self) -> UpdateReport:
        try:
            report = await self._poll()
        except UnsupportedInverterError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
                translation_placeholders={"model": err.model_name},
            ) from err
        except ModbusTimeoutError as err:
            self._timeouts += 1
            if self._timeouts >= _TIMEOUTS_BEFORE_RECONNECT:
                self._timeouts = 0
                await self.inverter.modbus_unit.disconnect()
            self._lost()
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="no_answer") from err
        except ModbusError as err:
            self._lost()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        self._timeouts = 0
        # A layout without settings polls nothing here, which is no failure.
        if report.failed and not report.updated:
            self._lost()
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="nothing_answered") from ExceptionGroup(
                "every part failed", list(report.failed.values())
            )
        self._log_part_changes(report)
        if self.remote_control is not None:
            try:
                await self.remote_control.async_step()
            except ModbusError as err:
                _LOGGER.warning("%s: remote control failed: %s", self.name, err)
        return report

    def _lost(self) -> None:
        """Make remote control write its watchdog again once the link is back."""
        if self.remote_control is not None:
            self.remote_control.reset()

    def _log_part_changes(self, report: UpdateReport) -> None:
        """Log a part's first failure and its recovery, once each."""
        for name, cause in report.failed.items():
            if name not in self._failing:
                self._failing.add(name)
                _LOGGER.warning(
                    "%s: %s failed to refresh, its entities are unavailable: %s",
                    self.name,
                    name,
                    cause,
                )
        for name in report.updated & self._failing:
            self._failing.discard(name)
            _LOGGER.info("%s: %s is available again", self.name, name)


@dataclass
class FoxEssRuntimeData:
    """What a loaded config entry holds."""

    inverter: FoxEssInverter
    readings: FoxEssCoordinator
    settings: FoxEssCoordinator
    remote_control: RemoteControl | None
    # Start and end times of charge periods, kept while a period is disabled.
    charge_period_times: dict[str, Any] = field(default_factory=dict)

    def coordinator_for(self, name: str) -> FoxEssCoordinator:
        """The coordinator that polls an inverter value."""
        part = self.inverter.parts[self.inverter.part_of(name)]
        return self.settings if part.poll is Poll.SETTINGS else self.readings

    @property
    def round_values(self) -> bool:
        """Whether sensors smooth and round their values."""
        return bool(self.readings.config_entry.options.get(CONF_ROUND_VALUES, False))

    def device_info(self, entry: ConfigEntry) -> DeviceInfo:
        """The inverter, for the device registry."""
        inverter = self.inverter
        version = inverter.manager_version
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=inverter.model_name,
            name=entry.title,
            sw_version=str(version) if version is not None else None,
        )


type FoxEssConfigEntry = ConfigEntry[FoxEssRuntimeData]
