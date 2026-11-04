"""Builds the Modbus connection to an adapter, which every inverter behind it shares"""

from modbus_connection import ModbusSerialParams
from modbus_connection import ModbusTcpParams
from modbus_connection import ModbusUdpParams
from modbus_connection.tmodbus import ModbusConnection

from .common.types import ConnectionType
from .const import RTU_OVER_TCP
from .const import SERIAL
from .const import TCP
from .const import UDP
from .inverter_adapters import InverterAdapter

ModbusParams = ModbusTcpParams | ModbusUdpParams | ModbusSerialParams

_SERIAL_BAUDRATE = 9600

_SOCKET_PREFIX = "socket://"

# Some serial devices need a short delay after polling. Also do this for the inverter, just in case it helps.
_MESSAGE_SPACING = 30 / 1000

# Delaying for a second after establishing a connection seems to help the inverter stability,
# see https://github.com/nathanmarlor/foxess_modbus/discussions/132
_LAN_CONNECT_DELAY = 1.0


class InverterConnection(ModbusConnection):
    """A connection which knows how to describe itself, for logs and error messages"""

    def __init__(self, params: ModbusParams, *, connect_delay: float, message_spacing: float) -> None:
        super().__init__(params, connect_delay=connect_delay, message_spacing=message_spacing)
        self.connect_delay = connect_delay
        self.message_spacing = message_spacing
        self.description = describe(params)

    def __str__(self) -> str:
        return self.description


def build_connection(protocol: str, adapter: InverterAdapter, host: str) -> InverterConnection:
    """Build the (unconnected) connection to an adapter"""

    is_lan = adapter.connection_type == ConnectionType.LAN
    return InverterConnection(
        build_params(protocol, host),
        connect_delay=_LAN_CONNECT_DELAY if is_lan else 0.0,
        message_spacing=_MESSAGE_SPACING if protocol == SERIAL or is_lan else 0.0,
    )


def build_params(protocol: str, host: str) -> ModbusParams:
    """Build the connection params for a protocol and the host as stored in config"""

    if protocol == SERIAL:
        return ModbusSerialParams(device=host, baudrate=_SERIAL_BAUDRATE)
    if protocol == RTU_OVER_TCP:
        # RTU over TCP is a serial line forwarded over a socket
        return ModbusSerialParams(device=f"{_SOCKET_PREFIX}{host}")

    hostname, _, port = host.partition(":")
    if protocol == TCP:
        return ModbusTcpParams(host=hostname, port=int(port))
    if protocol == UDP:
        return ModbusUdpParams(host=hostname, port=int(port))
    raise AssertionError(f"Unknown protocol {protocol}")


def describe(params: ModbusParams) -> str:
    """A short description of what a connection talks to, used in logs and error messages"""

    if isinstance(params, ModbusSerialParams):
        if params.device.startswith(_SOCKET_PREFIX):
            return f"{RTU_OVER_TCP}://{params.device.removeprefix(_SOCKET_PREFIX)}"
        return params.device
    return f"{params.endpoint[0]}://{params.host}:{params.port}"
