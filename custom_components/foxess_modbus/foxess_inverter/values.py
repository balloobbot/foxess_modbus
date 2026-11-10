"""How raw readings turn into values: clamps, plausible ranges and BMS gating."""

from __future__ import annotations

import re
from collections.abc import Mapping

# A reading outside its range is a glitch, and reads as None. None is no bound.
PLAUSIBLE: Mapping[str, tuple[float | None, float | None]] = {
    "ambient_temperature": (-50, 100),
    "inverter_temperature": (-50, 100),
    "battery_temperature": (-50, 100),
    "bms_cell_temperature_high": (-50, 100),
    "bms_cell_temperature_low": (-50, 100),
    "battery_soc": (0, 100),
    "battery_soh": (0, 100),
    "bms_voltage": (0, None),
    "bms_current": (-100, 100),
    "bms_cell_voltage_high": (0, None),
    "bms_cell_voltage_low": (0, None),
    "bms_max_charge_current": (0, 100),
    "bms_max_discharge_current": (0, 100),
    "bms_cycle_count": (0, None),
    "bms_energy_remaining": (0, None),
    "bms_energy_throughput": (0, None),
    "battery_current": (-100, 100),
    "battery_power": (-100, 100),
    "battery_charge_power": (0, 100),
    "battery_discharge_power": (0, 100),
    "pv_current": (0, 100),
    "grid_voltage": (0, 300),
    "grid_frequency": (0, 60),
    "inverter_current": (0, 100),
    "inverter_power": (-100, 100),
    "inverter_reactive_power": (-100, 100),
    "inverter_apparent_power": (-100, 100),
    "eps_voltage": (0, 300),
    "eps_current": (0, 100),
    "eps_power": (-100, 100),
    "eps_frequency": (0, 60),
    "grid_ct_power": (-100, 100),
    "grid_ct_reactive_power": (-100, 100),
    "grid_ct_apparent_power": (-100, 100),
    "grid_ct_power_factor": (-1, 1),
    "ct2_power": (-100, 100),
    "feed_in_power": (0, 100),
    "grid_consumption_power": (0, 100),
    "load_power": (-100, 100),
    "solar_energy_today": (0, 1000),
    "battery_charge_energy_today": (0, 100),
    "battery_discharge_energy_today": (0, 100),
    "feed_in_energy_today": (0, 1000),
    "grid_consumption_energy_today": (0, 1000),
    "yield_energy_today": (-200, 200),
    "input_energy_today": (-1000, 1000),
    "load_energy_today": (-1000, 1000),
    "solar_energy_total": (0, None),
    "battery_charge_energy_total": (0, None),
    "battery_discharge_energy_total": (0, None),
    "feed_in_energy_total": (0, None),
    "grid_consumption_energy_total": (0, None),
    "yield_energy_total": (0, None),
    "input_energy_total": (0, None),
    "load_energy_total": (0, None),
    "max_charge_current": (0, 50),
    "max_discharge_current": (0, 50),
    "min_soc": (0, 100),
    "max_soc": (0, 100),
    "min_soc_on_grid": (0, 100),
    "import_power_limit": (0, 99999),
    "export_power_limit": (0, 99999),
}

# The single-phase EPS power reads a small negative value while idle.
PLAUSIBLE_EXACT: Mapping[str, tuple[float | None, float | None]] = {
    "eps_power": (0, 100),
    "eps_reactive_power": (0, 100),
    "eps_apparent_power": (0, 100),
}

# Negative readings of these are noise, and read as 0.
CLAMPED = re.compile(
    r"^(pv\d_current|pv\d_power|eps_power|eps_reactive_power|eps_apparent_power)$"
)

# These read None while the BMS is not connected.
GATED = frozenset(
    {
        "battery_soc",
        "battery_soh",
        "battery_temperature",
        "bms_max_charge_current",
        "bms_max_discharge_current",
        "bms_cell_temperature_high",
        "bms_cell_temperature_low",
        "bms_cell_voltage_high",
        "bms_cell_voltage_low",
        "bms_energy_remaining",
        "bms_cycle_count",
        "bms_energy_throughput",
    }
)

# BMS connect state: 0 is initial, 2 is not good. Any other value (the H3 has
# been seen to report 247) counts as connected.
BMS_NOT_CONNECTED = frozenset({0, 2})

_SUFFIX = re.compile(r"(_[rst]|_l?[12])$")
_PV = re.compile(r"^pv\d_")


def base_name(name: str) -> str:
    """The name without its phase or battery suffix, and with a PV string
    number replaced, to look it up in the tables above.
    """
    return _PV.sub("pv_", _SUFFIX.sub("", name))


def battery_suffix(name: str) -> str:
    """The battery suffix of a name: '_1', '_2' or ''."""
    return name[-2:] if name.endswith(("_1", "_2")) else ""


def plausible_range(name: str) -> tuple[float | None, float | None] | None:
    """The plausible range of a value, if it has one."""
    if (bounds := PLAUSIBLE_EXACT.get(name)) is not None:
        return bounds
    return PLAUSIBLE.get(base_name(name))
