"""The H1-US, a split-phase (120/240 V) inverter sold as the WEG SIW200H.

It has its own input register map, unrelated to the other H1 maps. Its
32-bit values hold the low word first. Power is in kW.
"""

from __future__ import annotations

from modbus_connection.model import Component, gauge, int32, integer, uint32


class H1UsLive(Component):
    """PV, inverter output, EPS and battery."""

    register_space = "input"

    # Positive while charging, so inverted to read positive while discharging.
    battery_power = int32(5213, scale=-0.001, word_order="little", unit="kW")
    load_power = gauge(5217, 0.001, unit="kW")
    state_code = integer(5220, signed=False)
    inverter_power = gauge(5231, 0.001, unit="kW")
    pv_power = gauge(5235, 0.001, signed=False, unit="kW")
    grid_frequency = gauge(5241, 0.01, signed=False, unit="Hz")
    ambient_temperature = gauge(5244, 0.1, unit="°C")
    eps_voltage = gauge(5246, 0.1, signed=False, unit="V")
    eps_voltage_l2 = gauge(5247, 0.1, signed=False, unit="V")
    inverter_current = gauge(5249, 0.1, unit="A")
    inverter_current_l2 = gauge(5250, 0.1, unit="A")
    pv1_voltage = gauge(5252, 0.1, unit="V")
    pv1_current = gauge(5253, 0.01, unit="A")
    pv2_voltage = gauge(5254, 0.1, unit="V")
    pv2_current = gauge(5255, 0.01, unit="A")
    pv3_voltage = gauge(5256, 0.1, unit="V")
    pv3_current = gauge(5257, 0.01, unit="A")


class H1UsGrid(Component):
    """Grid voltage and status, temperature, and the battery at the inverter."""

    register_space = "input"

    grid_voltage = gauge(5983, 0.1, signed=False, unit="V")
    grid_voltage_l2 = gauge(5984, 0.1, signed=False, unit="V")
    inverter_temperature = gauge(5989, 0.1, unit="°C")
    # Follows the grid voltage at once, where the state waits to reconnect.
    grid_status_code = integer(6000, signed=False)
    battery_voltage = gauge(6001, 0.1, unit="V")
    battery_current = gauge(6002, 0.1, unit="A")


class H1UsMeter(Component):
    """The grid CT, in total and per leg."""

    register_space = "input"

    grid_ct_power = int32(5600, scale=0.001, word_order="little", unit="kW")
    grid_ct_power_l1 = int32(5602, scale=0.001, word_order="little", unit="kW")
    grid_ct_power_l2 = int32(5604, scale=0.001, word_order="little", unit="kW")


class H1UsBattery(Component):
    """The battery state."""

    register_space = "input"

    battery_soc = gauge(5632, 0.1, signed=False, unit="%")
    battery_soh = integer(5633, signed=False, unit="%")


class H1UsEnergy(Component):
    """The energy counters, in kWh."""

    register_space = "input"

    feed_in_energy_today = int32(5608, scale=0.1, word_order="little", unit="kWh")
    feed_in_energy_total = uint32(5610, scale=0.1, word_order="little", unit="kWh")
    grid_consumption_energy_today = int32(
        5612, scale=0.1, word_order="little", unit="kWh"
    )
    grid_consumption_energy_total = uint32(
        5614, scale=0.1, word_order="little", unit="kWh"
    )
    solar_energy_today = gauge(5659, 0.1, signed=False, unit="kWh")
    solar_energy_total = uint32(5660, scale=0.1, word_order="little", unit="kWh")
    battery_discharge_energy_today = gauge(5665, 0.1, unit="kWh")
    battery_discharge_energy_total = uint32(
        5666, scale=0.1, word_order="little", unit="kWh"
    )
    battery_charge_energy_today = gauge(5671, 0.1, unit="kWh")
    battery_charge_energy_total = uint32(
        5672, scale=0.1, word_order="little", unit="kWh"
    )
    input_energy_today = gauge(5678, 0.1, unit="kWh")
    input_energy_total = uint32(5679, scale=0.1, word_order="little", unit="kWh")
