"""The blocks of the newer protocol: H3 Pro, H3 Smart and EVO.

The H1 G2 and the KH from firmware 1.33 serve some of these blocks next to
their legacy one. Power is in kW. The grid CT reads positive while
exporting. Battery power reads positive while discharging.
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

# Battery 2's BMS block is battery 1's, this many registers further on.
BMS_2_OFFSET = 698


class V2Status(Component):
    """The status and fault registers."""

    status_1 = raw_register(39063)
    status_3 = raw_register(39065)
    # The H3 Smart holds its off-grid flag here rather than in status 3.
    status_4 = raw_register(39066)
    fault_code_1 = raw_register(39067)
    fault_code_2 = raw_register(39068)
    fault_code_3 = raw_register(39069)


class V2Pv(Component):
    """Up to six PV strings: voltage and current, then the 32-bit powers."""

    pv1_voltage = gauge(39070, 0.1, unit="V")
    pv1_current = gauge(39071, 0.01, unit="A")
    pv2_voltage = gauge(39072, 0.1, unit="V")
    pv2_current = gauge(39073, 0.01, unit="A")
    pv3_voltage = gauge(39074, 0.1, unit="V")
    pv3_current = gauge(39075, 0.01, unit="A")
    pv4_voltage = gauge(39076, 0.1, unit="V")
    pv4_current = gauge(39077, 0.01, unit="A")
    pv5_voltage = gauge(39078, 0.1, unit="V")
    pv5_current = gauge(39079, 0.01, unit="A")
    pv6_voltage = gauge(39080, 0.1, unit="V")
    pv6_current = gauge(39081, 0.01, unit="A")
    pv1_power = int32(39279, scale=0.001, unit="kW")
    pv2_power = int32(39281, scale=0.001, unit="kW")
    pv3_power = int32(39283, scale=0.001, unit="kW")
    pv4_power = int32(39285, scale=0.001, unit="kW")
    pv5_power = int32(39287, scale=0.001, unit="kW")
    pv6_power = int32(39289, scale=0.001, unit="kW")


class V2PvLowWord(V2Pv):
    """The PV block of the H1 G2, which only writes the low word of each power."""

    pv1_power = gauge(39280, 0.001, unit="kW")
    pv2_power = gauge(39282, 0.001, unit="kW")


class V2Ac(Component):
    """Grid, inverter output, EPS, load and battery, per phase.

    The EVO is single-phase and serves the R phase only.
    """

    grid_voltage_r = gauge(39123, 0.1, signed=False, unit="V")
    grid_voltage_s = gauge(39124, 0.1, signed=False, unit="V")
    grid_voltage_t = gauge(39125, 0.1, signed=False, unit="V")
    inverter_current_r = int32(39126, scale=0.001, unit="A")
    inverter_current_s = int32(39128, scale=0.001, unit="A")
    inverter_current_t = int32(39130, scale=0.001, unit="A")
    inverter_power = int32(39134, scale=0.001, unit="kW")
    inverter_reactive_power = int32(39136, scale=0.001, unit="kvar")
    grid_frequency = gauge(39139, 0.01, signed=False, unit="Hz")
    inverter_temperature = gauge(39141, 0.1, unit="°C")
    ambient_temperature = gauge(39142, 0.1, unit="°C")
    eps_voltage_r = gauge(39201, 0.1, signed=False, unit="V")
    eps_voltage_s = gauge(39202, 0.1, signed=False, unit="V")
    eps_voltage_t = gauge(39203, 0.1, signed=False, unit="V")
    eps_current_r = int32(39204, scale=0.001, unit="A")
    eps_current_s = int32(39206, scale=0.001, unit="A")
    eps_current_t = int32(39208, scale=0.001, unit="A")
    eps_power_r = int32(39210, scale=0.001, unit="kW")
    eps_power_s = int32(39212, scale=0.001, unit="kW")
    eps_power_t = int32(39214, scale=0.001, unit="kW")
    eps_frequency = gauge(39218, 0.01, signed=False, unit="Hz")
    load_power_r = int32(39219, scale=0.001, unit="kW")
    load_power_s = int32(39221, scale=0.001, unit="kW")
    load_power_t = int32(39223, scale=0.001, unit="kW")
    load_power = int32(39225, scale=0.001, unit="kW")
    battery_voltage_1 = gauge(39227, 0.1, unit="V")
    battery_current_1 = int32(39228, scale=0.001, unit="A")
    battery_power_1 = int32(39230, scale=0.001, unit="kW")
    battery_voltage_2 = gauge(39232, 0.1, unit="V")
    battery_current_2 = int32(39233, scale=0.001, unit="A")
    battery_power_2 = int32(39235, scale=0.001, unit="kW")
    battery_power = int32(39237, scale=0.001, unit="kW")
    inverter_power_r = int32(39248, scale=0.001, unit="kW")
    inverter_power_s = int32(39250, scale=0.001, unit="kW")
    inverter_power_t = int32(39252, scale=0.001, unit="kW")
    inverter_reactive_power_r = int32(39256, scale=0.001, unit="kvar")
    inverter_reactive_power_s = int32(39258, scale=0.001, unit="kvar")
    inverter_reactive_power_t = int32(39260, scale=0.001, unit="kvar")
    inverter_apparent_power_r = int32(39264, scale=0.001, unit="kVA")
    inverter_apparent_power_s = int32(39266, scale=0.001, unit="kVA")
    inverter_apparent_power_t = int32(39268, scale=0.001, unit="kVA")


class V2GridCt(Component):
    """The grid CT of the EVO and the KH from firmware 1.33."""

    grid_ct_power = int32(39168, scale=0.001, unit="kW")


class EvoBattery(Component):
    """The battery health register of the EVO."""

    battery_soh = integer(39423, signed=False, unit="%")


class V2Meter(Component):
    """The grid meter block of the H3 Pro and H3 Smart, in 0.1 W."""

    grid_ct_power = int32(38814, scale=0.0001, unit="kW")
    grid_ct_power_r = int32(38816, scale=0.0001, unit="kW")
    grid_ct_power_s = int32(38818, scale=0.0001, unit="kW")
    grid_ct_power_t = int32(38820, scale=0.0001, unit="kW")
    grid_ct_reactive_power = int32(38822, scale=0.0001, unit="kvar")
    grid_ct_reactive_power_r = int32(38824, scale=0.0001, unit="kvar")
    grid_ct_reactive_power_s = int32(38826, scale=0.0001, unit="kvar")
    grid_ct_reactive_power_t = int32(38828, scale=0.0001, unit="kvar")
    grid_ct_apparent_power = int32(38830, scale=0.0001, unit="kVA")
    grid_ct_apparent_power_r = int32(38832, scale=0.0001, unit="kVA")
    grid_ct_apparent_power_s = int32(38834, scale=0.0001, unit="kVA")
    grid_ct_apparent_power_t = int32(38836, scale=0.0001, unit="kVA")
    grid_ct_power_factor = int32(38838, scale=0.00001)
    grid_ct_power_factor_r = int32(38840, scale=0.00001)
    grid_ct_power_factor_s = int32(38842, scale=0.00001)
    grid_ct_power_factor_t = int32(38844, scale=0.00001)
    # Before H3 Pro firmware 1.22 the grid frequency is here, not in V2Ac.
    grid_frequency = uint32(38846, scale=0.01, unit="Hz")
    ct2_power = int32(38914, scale=0.0001, unit="kW")
    ct2_power_r = int32(38916, scale=0.0001, unit="kW")
    ct2_power_s = int32(38918, scale=0.0001, unit="kW")
    ct2_power_t = int32(38920, scale=0.0001, unit="kW")


class V2Bms(Component):
    """One battery's BMS block.

    Battery 1 sits at the declared addresses. Battery 2 is the same block at
    ``base_offset=BMS_2_OFFSET``.
    """

    bms_connect_state = integer(37002, signed=False)
    bms_voltage = gauge(37609, 0.1, unit="V")
    bms_current = gauge(37610, 0.1, unit="A")
    battery_temperature = gauge(37611, 0.1, unit="°C")
    battery_soc = integer(37612, signed=False, unit="%")
    bms_cell_temperature_high = gauge(37617, 0.1, unit="°C")
    bms_cell_temperature_low = gauge(37618, 0.1, unit="°C")
    bms_cell_voltage_high = integer(37619, signed=False, unit="mV")
    bms_cell_voltage_low = integer(37620, signed=False, unit="mV")
    battery_soh = integer(37624, signed=False, unit="%")
    bms_energy_remaining = gauge(37632, 0.01, signed=False, unit="kWh")
