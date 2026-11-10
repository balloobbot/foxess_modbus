"""The energy counters, in kWh.

Each counter has a lifetime total and a total for today. The today counters
reset at midnight, inverter time.
"""

from __future__ import annotations

from modbus_connection.model import Component, gauge, int32, uint32


class Energy(Component):
    """The legacy counter block at holding 32000."""

    solar_energy_total = uint32(32000, scale=0.1, unit="kWh")
    solar_energy_today = gauge(32002, 0.1, signed=False, unit="kWh")
    battery_charge_energy_total = uint32(32003, scale=0.1, unit="kWh")
    battery_charge_energy_today = gauge(32005, 0.1, unit="kWh")
    battery_discharge_energy_total = uint32(32006, scale=0.1, unit="kWh")
    battery_discharge_energy_today = gauge(32008, 0.1, unit="kWh")
    feed_in_energy_total = uint32(32009, scale=0.1, unit="kWh")
    feed_in_energy_today = gauge(32011, 0.1, unit="kWh")
    grid_consumption_energy_total = uint32(32012, scale=0.1, unit="kWh")
    grid_consumption_energy_today = gauge(32014, 0.1, unit="kWh")
    yield_energy_total = uint32(32015, scale=0.1, unit="kWh")
    yield_energy_today = gauge(32017, 0.1, unit="kWh")
    input_energy_total = uint32(32018, scale=0.1, unit="kWh")
    input_energy_today = gauge(32020, 0.1, unit="kWh")
    load_energy_total = uint32(32021, scale=0.1, unit="kWh")
    load_energy_today = gauge(32023, 0.1, unit="kWh")


class InputEnergy(Component):
    """The same counters in the H1 G1 input block, without the load total."""

    register_space = "input"

    solar_energy_total = uint32(11069, scale=0.1, unit="kWh")
    solar_energy_today = gauge(11071, 0.1, signed=False, unit="kWh")
    battery_charge_energy_total = uint32(11072, scale=0.1, unit="kWh")
    battery_charge_energy_today = gauge(11074, 0.1, unit="kWh")
    battery_discharge_energy_total = uint32(11075, scale=0.1, unit="kWh")
    battery_discharge_energy_today = gauge(11077, 0.1, unit="kWh")
    feed_in_energy_total = uint32(11078, scale=0.1, unit="kWh")
    feed_in_energy_today = gauge(11080, 0.1, unit="kWh")
    grid_consumption_energy_total = uint32(11081, scale=0.1, unit="kWh")
    grid_consumption_energy_today = gauge(11083, 0.1, unit="kWh")
    yield_energy_total = uint32(11084, scale=0.1, unit="kWh")
    yield_energy_today = gauge(11086, 0.1, unit="kWh")
    input_energy_total = uint32(11087, scale=0.1, unit="kWh")
    input_energy_today = gauge(11089, 0.1, unit="kWh")
    load_energy_today = gauge(11092, 0.1, unit="kWh")


class V2Energy(Component):
    """The counter block of the newer protocol, all 32-bit, in 0.01 kWh."""

    solar_energy_total = uint32(39601, scale=0.01, unit="kWh")
    solar_energy_today = uint32(39603, scale=0.01, unit="kWh")
    battery_charge_energy_total = uint32(39605, scale=0.01, unit="kWh")
    battery_charge_energy_today = int32(39607, scale=0.01, unit="kWh")
    battery_discharge_energy_total = uint32(39609, scale=0.01, unit="kWh")
    battery_discharge_energy_today = int32(39611, scale=0.01, unit="kWh")
    feed_in_energy_total = uint32(39613, scale=0.01, unit="kWh")
    feed_in_energy_today = int32(39615, scale=0.01, unit="kWh")
    grid_consumption_energy_total = uint32(39617, scale=0.01, unit="kWh")
    grid_consumption_energy_today = int32(39619, scale=0.01, unit="kWh")
    yield_energy_total = uint32(39621, scale=0.01, unit="kWh")
    yield_energy_today = int32(39623, scale=0.01, unit="kWh")
    input_energy_total = uint32(39625, scale=0.01, unit="kWh")
    input_energy_today = int32(39627, scale=0.01, unit="kWh")
    load_energy_total = uint32(39629, scale=0.01, unit="kWh")
    load_energy_today = int32(39631, scale=0.01, unit="kWh")


class V2EnergyPre122(V2Energy):
    """The same block before H3 Pro firmware 1.22, in 0.1 kWh."""

    solar_energy_total = uint32(39601, scale=0.1, unit="kWh")
    solar_energy_today = uint32(39603, scale=0.1, unit="kWh")
    battery_charge_energy_total = uint32(39605, scale=0.1, unit="kWh")
    battery_charge_energy_today = int32(39607, scale=0.1, unit="kWh")
    battery_discharge_energy_total = uint32(39609, scale=0.1, unit="kWh")
    battery_discharge_energy_today = int32(39611, scale=0.1, unit="kWh")
    feed_in_energy_total = uint32(39613, scale=0.1, unit="kWh")
    feed_in_energy_today = int32(39615, scale=0.1, unit="kWh")
    grid_consumption_energy_total = uint32(39617, scale=0.1, unit="kWh")
    grid_consumption_energy_today = int32(39619, scale=0.1, unit="kWh")
    yield_energy_total = uint32(39621, scale=0.1, unit="kWh")
    yield_energy_today = int32(39623, scale=0.1, unit="kWh")
    input_energy_total = uint32(39625, scale=0.1, unit="kWh")
    input_energy_today = int32(39627, scale=0.1, unit="kWh")
    load_energy_total = uint32(39629, scale=0.1, unit="kWh")
    load_energy_today = int32(39631, scale=0.1, unit="kWh")
