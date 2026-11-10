"""What each register layout reads, and from where.

A layout is a set of parts. Each part is one Component class, placed and
narrowed to the fields that layout serves. The inverter object exposes the
fields of all its parts by name, so a consumer does not need to know which
block a value comes from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from modbus_connection.model import Component

from .components.energy import Energy, InputEnergy, V2Energy, V2EnergyPre122
from .components.h1 import H1InputLive, H1LanLive, H1Live, KhLive, KhPre133Live
from .components.h1_us import (
    H1UsBattery,
    H1UsEnergy,
    H1UsGrid,
    H1UsLive,
    H1UsMeter,
)
from .components.h3 import H3Bms, H3Live
from .components.identity import InputVersions, V2Versions, Versions
from .components.settings import (
    BatteryChargeLimit,
    InputBatteryChargeLimit,
    InputSettings,
    PowerLimits,
    Settings,
    V2Settings,
)
from .components.v2 import (
    BMS_2_OFFSET,
    EvoBattery,
    V2Ac,
    V2Bms,
    V2GridCt,
    V2Meter,
    V2Pv,
    V2PvLowWord,
    V2Status,
)
from .models import Layout
from .status import (
    H1_US_GRID_STATUSES,
    H1_US_STATES,
    STANDARD_FAULTS,
    V2_FAULTS,
    FaultTable,
    GridStatus,
    InverterState,
)


class Poll(Enum):
    """When a part is read."""

    SETUP = "setup"
    READINGS = "readings"
    SETTINGS = "settings"


class WorkMode(StrEnum):
    """The inverter's work mode."""

    SELF_USE = "self_use"
    FEED_IN_FIRST = "feed_in_first"
    BACK_UP = "back_up"
    PEAK_SHAVING = "peak_shaving"


@dataclass(frozen=True, kw_only=True)
class Part:
    """One Component of a layout."""

    name: str
    component: type[Component]
    poll: Poll = Poll.READINGS
    # Keep only these fields, or drop these fields. Neither keeps all.
    only: tuple[str, ...] | None = None
    exclude: tuple[str, ...] = ()
    base_offset: int = 0
    # Appended to each field name, to tell apart repeated parts.
    suffix: str = ""
    # Read each register on its own: the inverter refuses block reads here.
    individual: bool = False


@dataclass(frozen=True, kw_only=True)
class RemoteControlRegisters:
    """The registers remote control writes."""

    enable: int
    timeout: int
    # The active power register. Two words hold a 32-bit value, high word first.
    active_power: int
    active_power_words: int = 1


@dataclass(frozen=True, kw_only=True)
class LayoutSpec:
    """Everything that differs per layout."""

    parts: tuple[Part, ...]
    # Whether the master, slave and manager versions are hex encoded.
    version_hex: tuple[bool, bool, bool] = (False, False, False)
    # The status register that holds the off-grid flag, for status bits.
    off_grid_status: str = "status_3"
    # Maps the state code to a state, where it is not an index.
    states: Mapping[int, InverterState] | None = None
    grid_statuses: tuple[GridStatus, ...] = ()
    # The fault table, and the fault code fields it decodes, in order.
    faults: tuple[FaultTable, tuple[str, ...]] | None = None
    work_modes: Mapping[int, WorkMode] = field(default_factory=dict)
    charge_periods: bool = False
    remote_control: RemoteControlRegisters | None = None


_PV_1_2 = tuple(f"pv{n}_{q}" for n in (1, 2) for q in ("voltage", "current", "power"))
_STANDARD_FAULT_CODES = tuple(f"fault_code_{n}" for n in (1, 2, 4, 5, 6, 7, 8))
_V2_FAULT_CODES = ("fault_code_1", "fault_code_2", "fault_code_3")
_CHARGE_PERIOD_FIELDS = tuple(
    f"charge_period_{n}_{q}"
    for n in (1, 2)
    for q in ("charge_from_grid_code", "start_code", "end_code")
)
_BMS_CELLS = (
    "bms_cell_temperature_high",
    "bms_cell_temperature_low",
    "bms_cell_voltage_high",
    "bms_cell_voltage_low",
)
_V2_BATTERY = (
    "bms_connect_state",
    "bms_voltage",
    "bms_current",
    "battery_temperature",
    "battery_soc",
    *_BMS_CELLS,
    "bms_energy_remaining",
)
_THREE_PHASE_V2_AC = tuple(
    name
    for name in V2Ac.declared_fields
    if name not in ("ambient_temperature", "eps_frequency")
)

_LEGACY_WORK_MODES = {
    0: WorkMode.SELF_USE,
    1: WorkMode.FEED_IN_FIRST,
    2: WorkMode.BACK_UP,
}
_PEAK_SHAVING_WORK_MODES = {**_LEGACY_WORK_MODES, 4: WorkMode.PEAK_SHAVING}
_V2_WORK_MODES = {
    1: WorkMode.SELF_USE,
    2: WorkMode.FEED_IN_FIRST,
    3: WorkMode.BACK_UP,
    4: WorkMode.PEAK_SHAVING,
}

_LEGACY_REMOTE_CONTROL = RemoteControlRegisters(
    enable=44000, timeout=44001, active_power=44002
)
_H3_REMOTE_CONTROL = RemoteControlRegisters(
    enable=44000, timeout=44001, active_power=44002, active_power_words=2
)
_V2_REMOTE_CONTROL = RemoteControlRegisters(
    enable=46001, timeout=46002, active_power=46003, active_power_words=2
)


def _v2_pv(count: int, component: type[Component] = V2Pv) -> Part:
    return Part(
        name="pv",
        component=component,
        only=tuple(
            f"pv{n}_{q}"
            for n in range(1, count + 1)
            for q in ("voltage", "current", "power")
        ),
    )


def _settings(*, charge_periods: bool, individual: bool = True) -> Part:
    return Part(
        name="settings",
        component=Settings,
        poll=Poll.SETTINGS,
        exclude=() if charge_periods else _CHARGE_PERIOD_FIELDS,
        individual=individual,
    )


def _h1_g2(*, with_faults: bool, bms: tuple[str, ...]) -> LayoutSpec:
    return LayoutSpec(
        parts=(
            Part(name="versions", component=V2Versions, poll=Poll.SETUP),
            Part(
                name="live",
                component=H1Live,
                exclude=(*_PV_1_2, "inverter_state_code"),
            ),
            _v2_pv(2, V2PvLowWord),
            Part(
                name="status",
                component=V2Status,
                only=(
                    "status_1",
                    "status_3",
                    *(_V2_FAULT_CODES if with_faults else ()),
                ),
            ),
            Part(name="bms", component=V2Bms, only=bms),
            Part(name="energy", component=Energy),
            _settings(charge_periods=True),
        ),
        version_hex=(True, True, True),
        faults=(V2_FAULTS, _V2_FAULT_CODES) if with_faults else None,
        work_modes=_PEAK_SHAVING_WORK_MODES,
        charge_periods=True,
        remote_control=_LEGACY_REMOTE_CONTROL,
    )


def _h3(*, bms: bool, settings: bool, remote_control: bool) -> LayoutSpec:
    return LayoutSpec(
        parts=(
            Part(name="versions", component=Versions, poll=Poll.SETUP),
            Part(name="live", component=H3Live),
            *((Part(name="bms", component=H3Bms),) if bms else ()),
            Part(name="energy", component=Energy),
            *((_settings(charge_periods=False),) if settings else ()),
        ),
        version_hex=(False, False, True),
        faults=(STANDARD_FAULTS, _STANDARD_FAULT_CODES),
        work_modes=_PEAK_SHAVING_WORK_MODES if settings else {},
        remote_control=_H3_REMOTE_CONTROL if remote_control else None,
    )


def _h3_pro(*, pre122: bool) -> LayoutSpec:
    meter_fields = tuple(
        name
        for name in V2Meter.declared_fields
        if not pre122
        or not name.startswith(
            ("grid_ct_reactive", "grid_ct_apparent", "grid_ct_power_factor")
        )
    )
    if not pre122:
        meter_fields = tuple(name for name in meter_fields if name != "grid_frequency")
    return LayoutSpec(
        parts=(
            Part(name="versions", component=V2Versions, poll=Poll.SETUP),
            Part(name="status", component=V2Status, exclude=("status_4",)),
            _v2_pv(6),
            Part(
                name="ac",
                component=V2Ac,
                only=tuple(
                    name
                    for name in _THREE_PHASE_V2_AC
                    if not (pre122 and name == "grid_frequency")
                ),
            ),
            Part(name="meter", component=V2Meter, only=meter_fields),
            Part(name="bms_1", component=V2Bms, only=_V2_BATTERY, suffix="_1"),
            Part(
                name="bms_2",
                component=V2Bms,
                only=_V2_BATTERY,
                suffix="_2",
                base_offset=BMS_2_OFFSET,
            ),
            Part(name="charge_limit", component=BatteryChargeLimit),
            Part(name="energy", component=V2EnergyPre122 if pre122 else V2Energy),
            Part(name="settings", component=V2Settings, poll=Poll.SETTINGS),
            Part(
                name="power_limits",
                component=PowerLimits,
                poll=Poll.SETTINGS,
                only=("export_power_limit",),
            ),
        ),
        version_hex=(not pre122, not pre122, True),
        faults=(V2_FAULTS, _V2_FAULT_CODES),
        work_modes=_V2_WORK_MODES,
        remote_control=_V2_REMOTE_CONTROL,
    )


LAYOUTS: Mapping[Layout, LayoutSpec] = {
    Layout.H1_G1: LayoutSpec(
        parts=(
            Part(name="versions", component=InputVersions, poll=Poll.SETUP),
            Part(name="live", component=H1InputLive),
            Part(name="charge_limit", component=InputBatteryChargeLimit),
            Part(name="energy", component=InputEnergy),
            Part(name="settings", component=InputSettings, poll=Poll.SETTINGS),
        ),
        version_hex=(False, False, False),
        faults=(STANDARD_FAULTS, _STANDARD_FAULT_CODES),
        work_modes=_LEGACY_WORK_MODES,
        charge_periods=True,
        remote_control=_LEGACY_REMOTE_CONTROL,
    ),
    Layout.H1_LAN: LayoutSpec(
        parts=(
            Part(name="versions", component=Versions, poll=Poll.SETUP),
            Part(name="live", component=H1LanLive),
        ),
        version_hex=(False, False, False),
        faults=(STANDARD_FAULTS, _STANDARD_FAULT_CODES),
        remote_control=_LEGACY_REMOTE_CONTROL,
    ),
    Layout.H1_G2_PRE144: _h1_g2(with_faults=False, bms=("bms_energy_remaining",)),
    Layout.H1_G2: _h1_g2(
        with_faults=True,
        bms=(
            "bms_voltage",
            "bms_current",
            *_BMS_CELLS,
            "battery_soh",
            "bms_energy_remaining",
        ),
    ),
    Layout.KH_PRE133: LayoutSpec(
        parts=(
            Part(name="versions", component=Versions, poll=Poll.SETUP),
            Part(name="live", component=KhPre133Live),
            Part(name="energy", component=Energy),
            _settings(charge_periods=False),
        ),
        version_hex=(True, True, True),
        work_modes=_LEGACY_WORK_MODES,
        remote_control=_LEGACY_REMOTE_CONTROL,
    ),
    Layout.KH: LayoutSpec(
        parts=(
            Part(name="versions", component=V2Versions, poll=Poll.SETUP),
            Part(
                name="live",
                component=KhLive,
                exclude=(*_PV_1_2, "grid_ct_power", "bms_connect_state"),
            ),
            _v2_pv(4),
            Part(name="grid_ct", component=V2GridCt),
            Part(name="status", component=V2Status, only=_V2_FAULT_CODES),
            Part(
                name="bms",
                component=V2Bms,
                only=(
                    "bms_connect_state",
                    *_BMS_CELLS,
                    "battery_soh",
                    "bms_energy_remaining",
                ),
            ),
            Part(name="energy", component=Energy),
            _settings(charge_periods=False),
            Part(name="power_limits", component=PowerLimits, poll=Poll.SETTINGS),
        ),
        version_hex=(True, True, True),
        faults=(V2_FAULTS, _V2_FAULT_CODES),
        work_modes=_LEGACY_WORK_MODES,
        remote_control=_LEGACY_REMOTE_CONTROL,
    ),
    Layout.H3_PRE180: _h3(bms=False, settings=True, remote_control=True),
    Layout.H3: _h3(bms=True, settings=True, remote_control=True),
    Layout.AIO_H3_PRE101: _h3(bms=False, settings=False, remote_control=False),
    Layout.AIO_H3: _h3(bms=False, settings=True, remote_control=False),
    Layout.KUARA_H3: _h3(bms=False, settings=True, remote_control=False),
    Layout.H3_PRO_PRE122: _h3_pro(pre122=True),
    Layout.H3_PRO: _h3_pro(pre122=False),
    Layout.H3_SMART: LayoutSpec(
        parts=(
            Part(name="versions", component=V2Versions, poll=Poll.SETUP),
            Part(name="status", component=V2Status, exclude=("status_3",)),
            _v2_pv(4),
            Part(
                name="ac", component=V2Ac, only=(*_THREE_PHASE_V2_AC, "eps_frequency")
            ),
            Part(
                name="meter",
                component=V2Meter,
                only=tuple(
                    name
                    for name in V2Meter.declared_fields
                    if name.startswith(("grid_ct_power", "ct2_power"))
                    and not name.startswith("grid_ct_power_factor")
                ),
            ),
            Part(
                name="bms_1",
                component=V2Bms,
                only=(*_V2_BATTERY, "battery_soh"),
                suffix="_1",
                individual=True,
            ),
            Part(
                name="bms_2",
                component=V2Bms,
                only=(*_V2_BATTERY, "battery_soh"),
                suffix="_2",
                base_offset=BMS_2_OFFSET,
            ),
            Part(name="charge_limit", component=BatteryChargeLimit),
            Part(name="energy", component=V2Energy),
            Part(name="settings", component=V2Settings, poll=Poll.SETTINGS),
            Part(name="power_limits", component=PowerLimits, poll=Poll.SETTINGS),
        ),
        version_hex=(True, True, True),
        off_grid_status="status_4",
        faults=(V2_FAULTS, _V2_FAULT_CODES),
        work_modes=_V2_WORK_MODES,
        remote_control=_V2_REMOTE_CONTROL,
    ),
    Layout.EVO: LayoutSpec(
        parts=(
            Part(name="versions", component=V2Versions, poll=Poll.SETUP),
            _v2_pv(3),
            Part(
                name="ac",
                component=V2Ac,
                only=(
                    "grid_voltage_r",
                    "inverter_current_r",
                    "inverter_power",
                    "grid_frequency",
                    "inverter_temperature",
                    "ambient_temperature",
                    "eps_voltage_r",
                    "eps_current_r",
                    "eps_frequency",
                    "load_power",
                    "battery_voltage_1",
                    "battery_current_1",
                    "battery_power_1",
                    "battery_power",
                ),
            ),
            Part(name="grid_ct", component=V2GridCt),
            Part(name="bms", component=V2Bms, only=("bms_connect_state",)),
            Part(name="battery", component=EvoBattery),
            Part(name="energy", component=V2Energy),
            Part(
                name="charge_periods",
                component=Settings,
                poll=Poll.SETTINGS,
                only=_CHARGE_PERIOD_FIELDS,
            ),
            Part(name="settings", component=V2Settings, poll=Poll.SETTINGS),
        ),
        version_hex=(True, True, True),
        work_modes=_V2_WORK_MODES,
        charge_periods=True,
    ),
    Layout.H1_US: LayoutSpec(
        parts=(
            Part(name="live", component=H1UsLive),
            Part(name="grid", component=H1UsGrid),
            Part(name="meter", component=H1UsMeter),
            Part(name="battery", component=H1UsBattery),
            Part(name="energy", component=H1UsEnergy),
        ),
        states=H1_US_STATES,
        grid_statuses=H1_US_GRID_STATUSES,
    ),
}
