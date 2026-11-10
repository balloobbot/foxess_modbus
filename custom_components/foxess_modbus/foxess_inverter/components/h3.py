"""The three-phase legacy blocks: H3, AC3, AIO-H3 and their OEM variants.

Power is in kW. The grid CT reads positive while exporting. Battery power
reads positive while discharging.
"""

from __future__ import annotations

from modbus_connection.model import Component, gauge, integer, raw_register


class H3Live(Component):
    """The holding block at 31000."""

    pv1_voltage = gauge(31000, 0.1, unit="V")
    pv1_current = gauge(31001, 0.1, unit="A")
    pv1_power = gauge(31002, 0.001, unit="kW")
    pv2_voltage = gauge(31003, 0.1, unit="V")
    pv2_current = gauge(31004, 0.1, unit="A")
    pv2_power = gauge(31005, 0.001, unit="kW")
    grid_voltage_r = gauge(31006, 0.1, signed=False, unit="V")
    grid_voltage_s = gauge(31007, 0.1, signed=False, unit="V")
    grid_voltage_t = gauge(31008, 0.1, signed=False, unit="V")
    inverter_current_r = gauge(31009, 0.1, unit="A")
    inverter_current_s = gauge(31010, 0.1, unit="A")
    inverter_current_t = gauge(31011, 0.1, unit="A")
    inverter_power_r = gauge(31012, 0.001, unit="kW")
    inverter_power_s = gauge(31013, 0.001, unit="kW")
    inverter_power_t = gauge(31014, 0.001, unit="kW")
    grid_frequency = gauge(31015, 0.01, signed=False, unit="Hz")
    eps_power_r = gauge(31022, 0.001, unit="kW")
    eps_power_s = gauge(31023, 0.001, unit="kW")
    eps_power_t = gauge(31024, 0.001, unit="kW")
    eps_frequency = gauge(31025, 0.01, signed=False, unit="Hz")
    grid_ct_power_r = gauge(31026, 0.001, unit="kW")
    grid_ct_power_s = gauge(31027, 0.001, unit="kW")
    grid_ct_power_t = gauge(31028, 0.001, unit="kW")
    load_power_r = gauge(31029, 0.001, unit="kW")
    load_power_s = gauge(31030, 0.001, unit="kW")
    load_power_t = gauge(31031, 0.001, unit="kW")
    inverter_temperature = gauge(31032, 0.1, unit="°C")
    ambient_temperature = gauge(31033, 0.1, unit="°C")
    bms_voltage = gauge(31034, 0.1, unit="V")
    bms_current = gauge(31035, 0.1, unit="A")
    battery_power = gauge(31036, 0.001, unit="kW")
    battery_temperature = gauge(31037, 0.1, unit="°C")
    battery_soc = integer(31038, signed=False, unit="%")
    state_code = integer(31041)
    bms_connect_state = integer(31042, signed=False)
    fault_code_1 = raw_register(31044)
    fault_code_2 = raw_register(31045)
    fault_code_4 = raw_register(31047)
    fault_code_5 = raw_register(31048)
    fault_code_6 = raw_register(31049)
    fault_code_7 = raw_register(31050)
    fault_code_8 = raw_register(31051)


class H3Bms(Component):
    """The BMS block that the H3 serves from manager firmware 1.80."""

    battery_soh = integer(31090, signed=False, unit="%")
    bms_cell_temperature_high = gauge(31102, 0.1, unit="°C")
    bms_cell_temperature_low = gauge(31103, 0.1, unit="°C")
    bms_energy_remaining = gauge(31123, 0.01, signed=False, unit="kWh")
    bms_cell_voltage_high = integer(31134, signed=False, unit="mV")
    bms_cell_voltage_low = integer(31135, signed=False, unit="mV")
