"""The model name and the firmware version registers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modbus_connection import ModbusExceptionError
from modbus_connection.model import Component, raw_register

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

MODEL_NAME_ADDRESS = 30000
MODEL_NAME_LENGTH = 15
# The SunSpec common block: "SunS" at 40000, then the model at 40020.
SUNSPEC_MARKER_ADDRESS = 40000
SUNSPEC_MARKER = [0x5375, 0x6E53]
SUNSPEC_MODEL_ADDRESS = 40020
SUNSPEC_MODEL_LENGTH = 16


def decode_model_name(words: list[int]) -> str:
    """Decode the model name from its registers.

    Most models put one ASCII character in the low byte of each register.
    Some (H1 G2, H3 Pro) pack two per register, high byte first. The name ends
    at the first character that is not printable. The H3 pads it with spaces.
    """
    if words and words[0] & 0xFF00:
        chars = [byte for word in words for byte in (word >> 8, word & 0xFF)]
    else:
        chars = words
    text = ""
    for char in chars:
        if not 0x20 <= char < 0x7F:
            break
        text += chr(char)
    return text.strip()


async def _async_read(
    unit: ModbusUnit, address: int, length: int, max_read: int | None
) -> list[int]:
    """Read holding registers in pieces of at most ``max_read``."""
    step = max_read or length
    words: list[int] = []
    for start in range(address, address + length, step):
        words += await unit.read_holding_registers(
            start, min(step, address + length - start)
        )
    return words


async def async_read_model_name(unit: ModbusUnit, max_read: int | None) -> str:
    """Read the inverter's model name.

    Every FoxESS inverter but the H1-US serves it at holding 30000. The H1-US
    leaves that empty, and serves it in its SunSpec common block instead.
    Read in pieces of at most ``max_read`` registers, for an adapter that
    cannot serve more in one read.
    """
    words = await _async_read(unit, MODEL_NAME_ADDRESS, MODEL_NAME_LENGTH, max_read)
    if name := decode_model_name(words):
        return name
    try:
        marker = await _async_read(unit, SUNSPEC_MARKER_ADDRESS, 2, max_read)
        if marker != SUNSPEC_MARKER:
            return ""
        words = await _async_read(
            unit, SUNSPEC_MODEL_ADDRESS, SUNSPEC_MODEL_LENGTH, max_read
        )
    except ModbusExceptionError:
        # Best effort: the caller reports an unknown model.
        return ""
    return decode_model_name(words)


class Versions(Component):
    """Firmware versions in the legacy holding block.

    How each register encodes its version differs per layout, so the raw
    words are kept and the layout decodes them.
    """

    master_version_code = raw_register(30016)
    slave_version_code = raw_register(30017)
    manager_version_code = raw_register(30018)


class InputVersions(Versions):
    """Firmware versions of the H1 G1 over RS485, in input registers."""

    register_space = "input"

    master_version_code = raw_register(10016)
    slave_version_code = raw_register(10017)
    manager_version_code = raw_register(10018)


class V2Versions(Versions):
    """Firmware versions in the block of the newer protocol."""

    master_version_code = raw_register(36001)
    slave_version_code = raw_register(36002)
    manager_version_code = raw_register(36003)
