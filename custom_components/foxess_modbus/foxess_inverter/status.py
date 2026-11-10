"""Fault codes and inverter states."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class FaultTable:
    """The fault each bit of each fault register stands for.

    Bit 0 is the least significant bit. A fault in ``masks`` hides the faults
    it implies.
    """

    registers: Sequence[Sequence[str | None]]
    masks: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def decode(self, words: Sequence[int]) -> list[str]:
        """The active faults, in register and bit order."""
        active = [
            fault
            for faults, word in zip(self.registers, words, strict=True)
            for bit, fault in enumerate(faults)
            if fault is not None and word & (1 << bit)
        ]
        hidden = {masked for fault in active for masked in self.masks.get(fault, ())}
        return [fault for fault in active if fault not in hidden]


# Fault codes 1, 2 and 4 to 8. Fault code 3 has no faults.
STANDARD_FAULTS = FaultTable(
    registers=(
        (
            "Grid Lost Fault",
            "Grid Voltage Fault",
            "Grid Frequency Fault",
            "Grid 10min Voltage Fault",
            "EPS Voltage Fault",
            "Software Inverter Over-current Fault",
            "DCI Fault",
            None,
            "Hardware Inverter Over-current Fault",
            "Software Bus Voltage Fault",
            "Battery Voltage Fault",
            "Software Battery Over-current Fault",
            "Isolation Fault",
            "Residual Over-current Fault",
            "PV Voltage Fault",
            "Software PV Over-current Fault",
        ),
        (
            "Inverter Temperature Fault",
            "Ground Connection Fault",
            "Inverter Overload Fault",
            "EPS Overload Fault",
            "Battery Power Low Fault",
            "Hardware Bus Voltage Fault",
            "Hardware PV Over-current Fault",
            "Hardware Battery Over-current Fault",
            "SCI Fault",
            "Master SPI Fault",
            "BMS Lost Fault",
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "Master Sample Detection Fault",
            "Residual Current Detection Fault",
            "Inverter EEPROM Fault",
            "PV Connection Direction Fault",
            "Battery Relay Open",
            "Battery Relay Short Circuit",
            "Battery Buck Fault",
            "Battery Boost Fault",
            "EPS Relay Fault",
            "Short EPS Load Fault",
            "Battery Connection Direction Fault",
            "Main Relay Open",
            "S1 Close Fault",
            "S2 Close Fault",
            "M1 Close Fault",
            "M2 Close Fault",
        ),
        (
            "Grid Voltage Consistency Fault",
            "Grid Frequency Consistency Fault",
            "DCI Consistency Fault",
            "Residual Current Consistency Fault",
            None,
            None,
            "Slave SPI Fault",
            "Slave Sample Fault",
            "RDSP SPI Fault",
            "RDSP Sample Fault",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "ARM EEPROM Fault",
            "Meter Lost Fault",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "BMS External Fault",
            "BMS Internal Fault",
            "Battery Over-voltage",
            "Battery under-voltage",
            "BMS Charge Over-current",
            "BMS Discharge Over-current",
            "BMS Over-temperature",
            "BMS Under-temperature",
            "BMS Cell Imbalance",
            "BMS Hardware Protection Fault",
            "BMS Circuit Fault",
            "BMS Insulation Fault",
            "BMS Voltage Sensor Fault",
            "BMS Temperature Sensor Fault",
            "BMS Current Sensor Fault",
            "BMS Relay Fault",
        ),
        (
            "BMS Type Mismatch",
            "BMS Version Mismatch",
            "BMS Manufacturer Mismatch",
            "BMS Software/Hardware Mismatch",
            "BMS Master/Slave Mismatch",
            "BMS Charge Request Not Acknowledged",
            "BMS Supply Fault",
            None,
            "BMS Self Check Fault",
            "BMS Cell Temperature Difference Fault",
            "BMS Cell Voltage Break Line Fault",
            "BMS Self Check Voltage Mismatch Fault",
            "BMS Precharge Fault",
            "BMS Self Check HVB Fault",
            "BMS Self Check Pack Current Fault",
            "BMS Self Check Sys Mismatch Fault",
        ),
    ),
    masks={
        "Grid Lost Fault": ("Grid Voltage Fault", "Grid Frequency Fault"),
    },
)


# The three fault registers of the newer protocol.
V2_FAULTS = FaultTable(
    registers=(
        (
            "PV Over-voltage",
            "DC arc fault",
            "String reverse connection",
            None,
            None,
            None,
            None,
            "Grid Lost Fault",
            "Grid Voltage Fault",
            None,
            None,
            "Grid Frequency Fault",
            None,
            None,
            "Output Over-current Fault",
            "Output DC Over-current Fault",
        ),
        (
            "Residual Current Consistency Fault",
            "Ground Connection Fault",
            "Low Insulation Resistante Fault",
            "Inverter Over-temperature Fault",
            None,
            None,
            None,
            None,
            None,
            "Energy Storage Equipment Abnormal Fault",
            "Isolated Island Fault",
            None,
            None,
            None,
            "Off-grid Output Overload Fault",
            None,
        ),
        (
            None,
            None,
            None,
            "External Fan Fault",
            "Energy Storage Reverse Connection Fault",
            None,
            None,
            None,
            None,
            "Meter Lost Fault",
            "BMS Lost Fault",
            None,
            None,
            None,
            None,
            None,
        ),
    ),
)


class InverterState(StrEnum):
    """What the inverter is doing."""

    SELF_TEST = "self_test"
    WAITING = "waiting"
    CHECKING = "checking"
    ON_GRID = "on_grid"
    OFF_GRID = "off_grid"
    RECOVERABLE_FAULT = "recoverable_fault"
    UNRECOVERABLE_FAULT = "unrecoverable_fault"
    STANDBY = "standby"
    FAULT = "fault"


class GridStatus(StrEnum):
    """Whether the H1-US sees grid voltage."""

    GRID_PRESENT = "grid_present"
    UNKNOWN = "unknown"
    GRID_LOST = "grid_lost"


# The H1-US grid status register holds an index into this.
H1_US_GRID_STATUSES = (
    GridStatus.GRID_PRESENT,
    GridStatus.UNKNOWN,
    GridStatus.GRID_LOST,
)

# The H1-US state register is a bit field. Only these values have been seen.
H1_US_STATES = {0x0800: InverterState.ON_GRID, 0x9100: InverterState.OFF_GRID}

# The state register of the H1 and KH holds an index into one of these.
H1_STATES = (
    InverterState.WAITING,
    InverterState.CHECKING,
    InverterState.ON_GRID,
    InverterState.OFF_GRID,
    InverterState.RECOVERABLE_FAULT,
    InverterState.UNRECOVERABLE_FAULT,
)
KH_STATES = (InverterState.SELF_TEST, *H1_STATES)


def decode_state_bits(status_1: int, off_grid: int) -> InverterState | None:
    """The state from the status registers of the newer protocol.

    Status 1: bit 0 standby, bit 2 operating, bit 6 fault. The off-grid
    status register: bit 0 off grid.
    """
    if status_1 & 0x40:
        return InverterState.FAULT
    if off_grid & 0x01:
        return InverterState.OFF_GRID
    if status_1 & 0x04:
        return InverterState.ON_GRID
    if status_1 & 0x01:
        return InverterState.STANDBY
    return None
