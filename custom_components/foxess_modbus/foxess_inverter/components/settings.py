"""Settings: what the inverter is configured to do.

These only change when something writes them: this library, the FoxESS app
or an installer. Poll them less often than the readings.
"""

from __future__ import annotations

from modbus_connection.model import (
    Component,
    gauge,
    int32,
    integer,
    raw_register,
    uint32,
)


class Settings(Component):
    """The legacy settings block at 41000.

    The charge period registers hold a time as ``(hour << 8) | minute``. A
    period with start and end both 0 is disabled.
    """

    work_mode_code = integer(41000, signed=False, writable=True)
    charge_period_1_charge_from_grid_code = raw_register(41001, writable=True)
    charge_period_1_start_code = raw_register(41002, writable=True)
    charge_period_1_end_code = raw_register(41003, writable=True)
    charge_period_2_charge_from_grid_code = raw_register(41004, writable=True)
    charge_period_2_start_code = raw_register(41005, writable=True)
    charge_period_2_end_code = raw_register(41006, writable=True)
    max_charge_current = gauge(41007, 0.1, signed=False, writable=True, unit="A")
    max_discharge_current = gauge(41008, 0.1, signed=False, writable=True, unit="A")
    min_soc = integer(41009, signed=False, writable=True, unit="%")
    max_soc = integer(41010, signed=False, writable=True, unit="%")
    min_soc_on_grid = integer(41011, signed=False, writable=True, unit="%")


class InputSettings(Settings):
    """The settings block as the H1 G1 serves it over RS485: read from input
    registers. Writes go to the same addresses in holding registers.
    """

    register_space = "input"


class V2Settings(Component):
    """The settings of the newer protocol."""

    max_charge_current = gauge(46607, 0.1, signed=False, writable=True, unit="A")
    max_discharge_current = gauge(46608, 0.1, signed=False, writable=True, unit="A")
    min_soc = integer(46609, signed=False, writable=True, unit="%")
    max_soc = integer(46610, signed=False, writable=True, unit="%")
    min_soc_on_grid = integer(46611, signed=False, writable=True, unit="%")
    work_mode_code = integer(49203, signed=False, writable=True)


class PowerLimits(Component):
    """The grid import and export limits, in W."""

    import_power_limit = uint32(46501, writable=True, unit="W")
    export_power_limit = uint32(46616, writable=True, unit="W")


class BatteryChargeLimit(Component):
    """The power the BMS lets the battery charge with, in W.

    Read with the readings: remote control steers against it.
    """

    battery_charge_power_limit = int32(46018, unit="W")


class InputBatteryChargeLimit(Component):
    """The battery charge power limit of the H1 G1, in input registers."""

    register_space = "input"

    battery_charge_power_limit = integer(44012, unit="W")
