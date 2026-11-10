"""Sensors for the values the inverter measures."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import RestoreSensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.const import EntityCategory
from homeassistant.const import UnitOfApparentPower
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.const import UnitOfElectricPotential
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfFrequency
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfReactivePower
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FoxEssConfigEntry
from .entity import FoxEssEntity
from .foxess_inverter import FoxEssInverter
from .foxess_inverter import GridStatus
from .foxess_inverter import InverterState

PARALLEL_UPDATES = 0

# A power reading is held for at most this long when integrating it into
# energy. A longer gap is a time the inverter did not answer.
_MAX_INTEGRATION_GAP = 300

_TOTALS = (SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING)


@dataclass(frozen=True, kw_only=True)
class FoxEssSensorDescription(SensorEntityDescription):
    """A sensor backed by an inverter value."""

    # With the "round sensor values" option, smooth the value and round it to
    # a multiple of this.
    round_to: float | None = None
    # The power to integrate, for an energy total the inverter does not keep.
    integrate: str | None = None


def _sensor(
    key: str,
    *,
    device_class: SensorDeviceClass | None = None,
    unit: str | None = None,
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    enabled: bool = True,
    round_to: float | None = None,
    category: EntityCategory | None = None,
    options: list[str] | None = None,
) -> FoxEssSensorDescription:
    return FoxEssSensorDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=state_class,
        entity_registry_enabled_default=enabled,
        round_to=round_to,
        entity_category=category,
        options=options,
    )


def _power(key: str, **kwargs: Any) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.POWER,
        unit=UnitOfPower.KILO_WATT,
        round_to=0.01,
        **kwargs,
    )


def _reactive(key: str) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        unit=UnitOfReactivePower.KILO_VOLT_AMPERE_REACTIVE,
        enabled=False,
        round_to=0.01,
    )


def _apparent(key: str) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.APPARENT_POWER,
        unit=UnitOfApparentPower.KILO_VOLT_AMPERE,
        enabled=False,
        round_to=0.01,
    )


def _voltage(key: str, **kwargs: Any) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.VOLTAGE,
        unit=UnitOfElectricPotential.VOLT,
        round_to=1,
        **kwargs,
    )


def _current(key: str, **kwargs: Any) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.CURRENT,
        unit=UnitOfElectricCurrent.AMPERE,
        **kwargs,
    )


def _temperature(key: str, **kwargs: Any) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        **kwargs,
    )


def _frequency(key: str) -> FoxEssSensorDescription:
    return _sensor(
        key,
        device_class=SensorDeviceClass.FREQUENCY,
        unit=UnitOfFrequency.HERTZ,
        enabled=False,
        round_to=0.1,
    )


def _energy(key: str, **kwargs: Any) -> FoxEssSensorDescription:
    state_class = SensorStateClass.TOTAL_INCREASING if key.endswith("_today") else SensorStateClass.TOTAL
    return _sensor(
        key,
        device_class=SensorDeviceClass.ENERGY,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=kwargs.pop("state_class", state_class),
        **kwargs,
    )


_PHASES = ("_r", "_s", "_t")
_LEGS = ("_l1", "_l2")
_BATTERIES = ("_1", "_2")
_PV_STRINGS = range(1, 7)


def _variants(
    description: FoxEssSensorDescription, suffixes: Iterable[str], placeholder: str
) -> list[FoxEssSensorDescription]:
    """The description, and one per suffix with the suffix as a placeholder."""
    return [
        description,
        *(
            replace(
                description,
                key=description.key + suffix,
                translation_key=f"{description.translation_key}_{placeholder}",
                translation_placeholders={placeholder: suffix.lstrip("_").upper()},
            )
            for suffix in suffixes
        ),
    ]


def _per_string(description: FoxEssSensorDescription, quantity: str) -> list[FoxEssSensorDescription]:
    """One description per PV string, keyed 'pv<n>_<quantity>'."""
    return [
        replace(
            description,
            key=f"pv{n}_{quantity}",
            translation_placeholders={"string": str(n)},
        )
        for n in _PV_STRINGS
    ]


def _leg(description: FoxEssSensorDescription, leg: str) -> FoxEssSensorDescription:
    """A split-phase leg, which most installs do not need to see."""
    return replace(
        description,
        key=description.key + leg,
        translation_key=f"{description.translation_key}_phase",
        translation_placeholders={"phase": leg.lstrip("_").upper()},
        entity_registry_enabled_default=False,
    )


SENSORS: tuple[FoxEssSensorDescription, ...] = (
    *_per_string(_voltage("pv_string_voltage"), "voltage"),
    *_per_string(_current("pv_string_current", round_to=1), "current"),
    *_per_string(_power("pv_string_power"), "power"),
    _power("pv_power"),
    *(
        replace(
            _energy("pv_string_energy", state_class=SensorStateClass.TOTAL_INCREASING),
            key=f"pv{n}_energy_total",
            translation_placeholders={"string": str(n)},
            integrate=f"pv{n}_power",
        )
        for n in _PV_STRINGS
    ),
    *_variants(_voltage("grid_voltage", enabled=False), (*_PHASES, *_LEGS), "phase"),
    _frequency("grid_frequency"),
    *_variants(_current("inverter_current", round_to=1), _PHASES, "phase"),
    _leg(_current("inverter_current", round_to=1), "_l2"),
    *_variants(_power("inverter_power"), _PHASES, "phase"),
    *_variants(_reactive("inverter_reactive_power"), _PHASES, "phase"),
    *_variants(_apparent("inverter_apparent_power"), _PHASES, "phase"),
    *_variants(_power("grid_ct_power"), _PHASES, "phase"),
    *(_leg(_power("grid_ct_power"), leg) for leg in _LEGS),
    *_variants(_power("feed_in_power"), _PHASES, "phase"),
    *_variants(_power("grid_consumption_power"), _PHASES, "phase"),
    *_variants(_power("ct2_power"), _PHASES, "phase"),
    *_variants(_reactive("grid_ct_reactive_power"), _PHASES, "phase"),
    *_variants(_apparent("grid_ct_apparent_power"), _PHASES, "phase"),
    *_variants(
        _sensor(
            "grid_ct_power_factor",
            device_class=SensorDeviceClass.POWER_FACTOR,
            enabled=False,
            round_to=0.001,
        ),
        _PHASES,
        "phase",
    ),
    *_variants(_power("load_power"), _PHASES, "phase"),
    *_variants(_voltage("eps_voltage", enabled=False), (*_PHASES, "_l2"), "phase"),
    *_variants(_current("eps_current", enabled=False, round_to=1), _PHASES, "phase"),
    *_variants(_power("eps_power", enabled=False), _PHASES, "phase"),
    _reactive("eps_reactive_power"),
    _apparent("eps_apparent_power"),
    _frequency("eps_frequency"),
    _temperature("inverter_temperature", round_to=0.5),
    _temperature("ambient_temperature", round_to=0.5),
    *_variants(_voltage("battery_voltage"), _BATTERIES, "battery"),
    *_variants(_current("battery_current", round_to=1), _BATTERIES, "battery"),
    *_variants(_power("battery_power"), _BATTERIES, "battery"),
    *_variants(_power("battery_charge_power"), _BATTERIES, "battery"),
    *_variants(_power("battery_discharge_power"), _BATTERIES, "battery"),
    *_variants(_voltage("bms_voltage"), _BATTERIES, "battery"),
    *_variants(_current("bms_current", round_to=1), _BATTERIES, "battery"),
    *_variants(
        _sensor("battery_soc", device_class=SensorDeviceClass.BATTERY, unit=PERCENTAGE),
        _BATTERIES,
        "battery",
    ),
    *_variants(_sensor("battery_soh", unit=PERCENTAGE), _BATTERIES, "battery"),
    *_variants(_temperature("battery_temperature"), _BATTERIES, "battery"),
    *(
        description
        for key in ("bms_cell_temperature_high", "bms_cell_temperature_low")
        for description in _variants(_temperature(key), _BATTERIES, "battery")
    ),
    *(
        description
        for key in ("bms_cell_voltage_high", "bms_cell_voltage_low")
        for description in _variants(
            _sensor(
                key,
                device_class=SensorDeviceClass.VOLTAGE,
                unit=UnitOfElectricPotential.MILLIVOLT,
                round_to=10,
            ),
            _BATTERIES,
            "battery",
        )
    ),
    _current("bms_max_charge_current", enabled=False),
    _current("bms_max_discharge_current", enabled=False),
    _sensor("bms_cycle_count"),
    *_variants(
        _sensor(
            "bms_energy_remaining",
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            unit=UnitOfEnergy.KILO_WATT_HOUR,
        ),
        _BATTERIES,
        "battery",
    ),
    _energy("bms_energy_throughput", enabled=False),
    _energy("solar_energy_today"),
    _energy("solar_energy_total"),
    _energy("battery_charge_energy_today"),
    replace(_energy("battery_charge_energy_total"), integrate="battery_charge_power"),
    _energy("battery_discharge_energy_today"),
    replace(_energy("battery_discharge_energy_total"), integrate="battery_discharge_power"),
    _energy("feed_in_energy_today"),
    replace(_energy("feed_in_energy_total"), integrate="feed_in_power"),
    _energy("grid_consumption_energy_today"),
    replace(_energy("grid_consumption_energy_total"), integrate="grid_consumption_power"),
    _energy("yield_energy_today"),
    _energy("yield_energy_total"),
    _energy("input_energy_today"),
    _energy("input_energy_total"),
    _energy("load_energy_today"),
    replace(_energy("load_energy_total"), integrate="load_power"),
    _sensor(
        "inverter_state",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        options=[state.value for state in InverterState],
    ),
    _sensor(
        "grid_status",
        device_class=SensorDeviceClass.ENUM,
        state_class=None,
        options=[status.value for status in GridStatus],
    ),
    _sensor("faults", state_class=None),
    _sensor("state_code", state_class=None, category=EntityCategory.DIAGNOSTIC),
    *(
        _sensor(f"{kind}_version", state_class=None, category=EntityCategory.DIAGNOSTIC)
        for kind in ("master", "slave", "manager")
    ),
)


def _served(inverter: FoxEssInverter, description: FoxEssSensorDescription) -> str | None:
    """The inverter value a sensor reads, or None if it has no sensor here."""
    if inverter.has(description.key):
        return description.key
    # The inverter does not keep this total: integrate the power, if it has it.
    if description.integrate is not None and inverter.has(description.integrate):
        return description.integrate
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FoxEssConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for each value this inverter serves."""
    inverter = entry.runtime_data.inverter
    entities: list[SensorEntity] = []
    for description in SENSORS:
        if (field := _served(inverter, description)) is None:
            continue
        if field != description.key:
            entities.append(FoxEssEnergySensor(entry, description, field))
        elif description.state_class in _TOTALS:
            entities.append(FoxEssTotalSensor(entry, description))
        else:
            entities.append(FoxEssSensor(entry, description))
    async_add_entities(entities)


class _Smoother:
    """Average the last few values, and only move in steps of ``step``."""

    def __init__(self, step: float) -> None:
        self._step = step
        self._samples: deque[float] = deque(maxlen=6)
        self._shown: float | None = None

    def add(self, value: float) -> float:
        self._samples.append(value)
        average = sum(self._samples) / len(self._samples)
        if self._shown is None or abs(average - self._shown) >= self._step:
            self._shown = self._step * round(average / self._step)
            self._samples.clear()
            self._samples.append(self._shown)
        return self._shown


def _state(value: Any) -> Any:
    """An inverter value as a sensor state."""
    if isinstance(value, list):
        return "; ".join(value) if value else "none"
    if isinstance(value, InverterState | GridStatus):
        return value.value
    if value is not None and not isinstance(value, int | float):
        return str(value)
    return value


class FoxEssSensor(FoxEssEntity, SensorEntity):
    """A measurement."""

    entity_description: FoxEssSensorDescription

    def __init__(self, entry: FoxEssConfigEntry, description: FoxEssSensorDescription) -> None:
        """Back the sensor with the inverter value of the same key."""
        super().__init__(entry, description)
        self._smoother = (
            _Smoother(description.round_to)
            if description.round_to is not None and entry.runtime_data.round_values
            else None
        )
        self._update_value()

    def _update_value(self) -> None:
        value = _state(self.inverter_value)
        if self._smoother is not None and isinstance(value, float | int):
            value = self._smoother.add(value)
        self._attr_native_value = value

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_value()
        super()._handle_coordinator_update()


class FoxEssTotalSensor(FoxEssEntity, RestoreSensor):
    """A long-term statistic.

    It holds its last value while the inverter is offline, as an inverter
    that powers down at night is routine. A gap would damage the long-term
    statistics and the energy dashboard.
    """

    entity_description: FoxEssSensorDescription

    @property
    def available(self) -> bool:
        """A total stays available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last value, then take the current one."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_value()
        super()._handle_coordinator_update()

    def _update_value(self) -> None:
        value = self.inverter_value
        if value is None:
            return
        last = self._attr_native_value
        if (
            self.entity_description.state_class is SensorStateClass.TOTAL_INCREASING
            and isinstance(last, int | float)
            and last * 0.99 <= value < last
        ):
            # Some firmwares dip a counter by a little. A real reset drops it
            # by far more.
            return
        self._attr_native_value = value


class FoxEssEnergySensor(FoxEssEntity, RestoreSensor):
    """Energy the inverter does not count itself: the power over time.

    It takes each power reading as holding until the next one.
    """

    entity_description: FoxEssSensorDescription

    def __init__(
        self,
        entry: FoxEssConfigEntry,
        description: FoxEssSensorDescription,
        power: str,
    ) -> None:
        """Integrate inverter value ``power``, in kW."""
        super().__init__(entry, description, power)
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._last: tuple[float, datetime] | None = None

    @property
    def available(self) -> bool:
        """A total stays available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the energy counted so far."""
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        value = last.native_value if last is not None else None
        self._attr_native_value = value if isinstance(value, int | float) else 0.0
        self._last = self._reading()

    def _reading(self) -> tuple[float, datetime] | None:
        """The power now, and when it was read."""
        power = self.inverter_value
        return (power, dt_util.utcnow()) if isinstance(power, int | float) else None

    @callback
    def _handle_coordinator_update(self) -> None:
        reading = self._reading()
        if self._last is not None and reading is not None and isinstance(self._attr_native_value, int | float):
            last_power, since = self._last
            seconds = (reading[1] - since).total_seconds()
            if 0 < seconds <= _MAX_INTEGRATION_GAP:
                self._attr_native_value = round(self._attr_native_value + last_power * seconds / 3600, 3)
        self._last = reading
        super()._handle_coordinator_update()
