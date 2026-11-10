"""The single-phase live blocks: H1, AC1, AIO-H1, H1 G2 and KH.

Power is in kW. The grid CT reads positive while exporting. Battery power
reads positive while discharging.
"""

from __future__ import annotations

from modbus_connection.model import Component, gauge, int32, integer, raw_register


class H1Live(Component):
    """The holding block at 31000, served by the H1 (LAN), H1 G2 and KH.

    The H1 G2 and the KH from firmware 1.33 read their PV strings from the
    newer block, so their layouts drop the PV fields here.
    """

    pv1_voltage = gauge(31000, 0.1, unit="V")
    pv1_current = gauge(31001, 0.1, unit="A")
    pv1_power = gauge(31002, 0.001, unit="kW")
    pv2_voltage = gauge(31003, 0.1, unit="V")
    pv2_current = gauge(31004, 0.1, unit="A")
    pv2_power = gauge(31005, 0.001, unit="kW")
    grid_voltage = gauge(31006, 0.1, signed=False, unit="V")
    inverter_current = gauge(31007, 0.1, unit="A")
    inverter_power = gauge(31008, 0.001, unit="kW")
    grid_frequency = gauge(31009, 0.01, signed=False, unit="Hz")
    eps_voltage = gauge(31010, 0.1, signed=False, unit="V")
    eps_current = gauge(31011, 0.1, unit="A")
    eps_power = gauge(31012, 0.001, unit="kW")
    eps_frequency = gauge(31013, 0.01, signed=False, unit="Hz")
    grid_ct_power = gauge(31014, 0.001, unit="kW")
    ct2_power = gauge(31015, 0.001, unit="kW")
    load_power = gauge(31016, 0.001, unit="kW")
    inverter_temperature = gauge(31018, 0.1, unit="°C")
    ambient_temperature = gauge(31019, 0.1, unit="°C")
    battery_voltage = gauge(31020, 0.1, unit="V")
    battery_current = gauge(31021, 0.1, unit="A")
    battery_power = gauge(31022, 0.001, unit="kW")
    battery_temperature = gauge(31023, 0.1, unit="°C")
    battery_soc = integer(31024, signed=False, unit="%")
    bms_max_charge_current = gauge(31025, 0.1, signed=False, unit="A")
    bms_max_discharge_current = gauge(31026, 0.1, signed=False, unit="A")
    inverter_state_code = integer(31027, signed=False)
    bms_connect_state = integer(31028, signed=False)


class H1LanLive(H1Live):
    """The H1 block as the LAN port serves it.

    The BMS state moves one register up, and the fault registers follow.
    """

    bms_connect_state = integer(31029, signed=False)
    fault_code_1 = raw_register(31031)
    fault_code_2 = raw_register(31032)
    fault_code_4 = raw_register(31034)
    fault_code_5 = raw_register(31035)
    fault_code_6 = raw_register(31036)
    fault_code_7 = raw_register(31037)
    fault_code_8 = raw_register(31038)


class KhLive(H1Live):
    """The KH block. Its CT2 reads inverted."""

    # The KH serves nothing from here to 31999.
    register_ranges = ((31000, 31054),)

    ct2_power = gauge(31015, -0.001, unit="kW")


class KhPre133Live(KhLive):
    """The KH block before firmware 1.33.

    It has four PV strings, and holds its powers as 32-bit values at the end
    of the block. The grid CT reads inverted.
    """

    pv3_voltage = gauge(31039, 0.1, unit="V")
    pv3_current = gauge(31040, 0.1, unit="A")
    pv3_power = gauge(31041, 0.001, unit="kW")
    pv4_voltage = gauge(31042, 0.1, unit="V")
    pv4_current = gauge(31043, 0.1, unit="A")
    pv4_power = gauge(31044, 0.001, unit="kW")
    inverter_power = int32(31045, scale=0.001, unit="kW")
    eps_power = int32(31047, scale=0.001, unit="kW")
    grid_ct_power = int32(31049, scale=-0.001, unit="kW")
    ct2_power = int32(31051, scale=-0.001, unit="kW")
    load_power = int32(31053, scale=0.001, unit="kW")


class H1InputLive(Component):
    """The input block at 11000 that the H1 G1 serves over RS485."""

    register_space = "input"

    pv1_voltage = gauge(11000, 0.1, unit="V")
    pv1_current = gauge(11001, 0.1, unit="A")
    pv1_power = gauge(11002, 0.001, unit="kW")
    pv2_voltage = gauge(11003, 0.1, unit="V")
    pv2_current = gauge(11004, 0.1, unit="A")
    pv2_power = gauge(11005, 0.001, unit="kW")
    battery_voltage = gauge(11006, 0.1, unit="V")
    battery_current = gauge(11007, 0.1, unit="A")
    battery_power = gauge(11008, 0.001, unit="kW")
    grid_voltage = gauge(11009, 0.1, signed=False, unit="V")
    inverter_current = gauge(11010, 0.1, unit="A")
    inverter_power = gauge(11011, 0.001, unit="kW")
    inverter_reactive_power = gauge(11012, 0.001, unit="kvar")
    inverter_apparent_power = gauge(11013, 0.001, unit="kVA")
    grid_frequency = gauge(11014, 0.01, signed=False, unit="Hz")
    eps_voltage = gauge(11015, 0.1, signed=False, unit="V")
    eps_current = gauge(11016, 0.1, unit="A")
    eps_power = gauge(11017, 0.001, unit="kW")
    eps_reactive_power = gauge(11018, 0.001, unit="kvar")
    eps_apparent_power = gauge(11019, 0.001, unit="kVA")
    eps_frequency = gauge(11020, 0.01, signed=False, unit="Hz")
    grid_ct_power = gauge(11021, 0.001, unit="kW")
    ct2_power = gauge(11022, 0.001, unit="kW")
    load_power = gauge(11023, 0.001, unit="kW")
    inverter_temperature = gauge(11024, 0.1, unit="°C")
    ambient_temperature = gauge(11025, 0.1, unit="°C")
    bms_voltage = gauge(11034, 0.1, unit="V")
    bms_current = gauge(11035, 0.1, unit="A")
    battery_soc = integer(11036, signed=False, unit="%")
    bms_energy_remaining = gauge(11037, 0.01, signed=False, unit="kWh")
    battery_temperature = gauge(11038, 0.1, unit="°C")
    bms_max_charge_current = gauge(11041, 0.1, signed=False, unit="A")
    bms_max_discharge_current = gauge(11042, 0.1, signed=False, unit="A")
    bms_cell_temperature_high = gauge(11043, 0.1, unit="°C")
    bms_cell_temperature_low = gauge(11044, 0.1, unit="°C")
    bms_cell_voltage_high = integer(11045, signed=False, unit="mV")
    bms_cell_voltage_low = integer(11046, signed=False, unit="mV")
    bms_cycle_count = integer(11048, signed=False)
    bms_energy_throughput = gauge(11049, 0.001, signed=False, unit="kWh")
    inverter_state_code = integer(11056, signed=False)
    bms_connect_state = integer(11058, signed=False)
    fault_code_1 = raw_register(11061)
    fault_code_2 = raw_register(11062)
    fault_code_4 = raw_register(11064)
    fault_code_5 = raw_register(11065)
    fault_code_6 = raw_register(11066)
    fault_code_7 = raw_register(11067)
    fault_code_8 = raw_register(11068)
