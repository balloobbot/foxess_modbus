"""The Modbus link parameters for a config entry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_DEVICE
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PORT
from modbus_connection import ModbusSerialParams
from modbus_connection import ModbusTcpParams
from modbus_connection import ModbusUdpParams

from .const import CONF_PROTOCOL
from .const import PROTOCOL_RTU_OVER_TCP
from .const import PROTOCOL_SERIAL
from .const import PROTOCOL_TCP

type ModbusParams = ModbusTcpParams | ModbusUdpParams | ModbusSerialParams

_SERIAL_BAUDRATE = 9600
# The line speed Home Assistant's modbus integration gives a serial framing
# carried over a socket. Matching it lets another integration on the same
# adapter share the connection.
_SOCKET_BAUDRATE = 115200
# Some serial adapters need a short pause between messages.
SERIAL_MESSAGE_SPACING = 0.03


def build_params(data: Mapping[str, Any]) -> ModbusParams:
    """Build the link parameters from config entry data."""
    protocol = data[CONF_PROTOCOL]
    if protocol == PROTOCOL_SERIAL:
        return ModbusSerialParams(device=data[CONF_DEVICE], baudrate=_SERIAL_BAUDRATE)
    host, port = data[CONF_HOST], data[CONF_PORT]
    if protocol == PROTOCOL_RTU_OVER_TCP:
        # RTU over TCP is a serial line forwarded over a socket.
        host = f"[{host}]" if ":" in host else host
        return ModbusSerialParams(device=f"socket://{host}:{port}", baudrate=_SOCKET_BAUDRATE)
    if protocol == PROTOCOL_TCP:
        return ModbusTcpParams(host=host, port=port)
    return ModbusUdpParams(host=host, port=port)
