"""Tests for turning the connection details stored in config into a Modbus connection"""

import pytest
from modbus_connection import ModbusSerialParams
from modbus_connection import ModbusTcpParams
from modbus_connection import ModbusUdpParams

from custom_components.foxess_modbus.common.types import ConnectionType
from custom_components.foxess_modbus.connection import build_connection
from custom_components.foxess_modbus.connection import build_params
from custom_components.foxess_modbus.connection import describe
from custom_components.foxess_modbus.const import RTU_OVER_TCP
from custom_components.foxess_modbus.const import SERIAL
from custom_components.foxess_modbus.const import TCP
from custom_components.foxess_modbus.const import UDP
from custom_components.foxess_modbus.inverter_adapters import ADAPTERS


def test_tcp_params() -> None:
    assert build_params(TCP, "1.2.3.4:502") == ModbusTcpParams(host="1.2.3.4", port=502)


def test_rtu_over_tcp_uses_rtu_framing() -> None:
    assert build_params(RTU_OVER_TCP, "1.2.3.4:502") == ModbusTcpParams(host="1.2.3.4", port=502, framer="rtu")


def test_udp_params() -> None:
    assert build_params(UDP, "1.2.3.4:8899") == ModbusUdpParams(host="1.2.3.4", port=8899)


def test_serial_params() -> None:
    assert build_params(SERIAL, "/dev/ttyUSB0") == ModbusSerialParams(device="/dev/ttyUSB0", baudrate=9600)


def test_unknown_protocol_is_rejected() -> None:
    with pytest.raises(AssertionError):
        build_params("carrier_pigeon", "1.2.3.4:502")


@pytest.mark.parametrize(
    ("protocol", "host", "expected"),
    [
        (TCP, "1.2.3.4:502", "tcp://1.2.3.4:502"),
        (RTU_OVER_TCP, "1.2.3.4:502", "rtu_over_tcp://1.2.3.4:502"),
        (UDP, "1.2.3.4:8899", "udp://1.2.3.4:8899"),
        (SERIAL, "/dev/ttyUSB0", "/dev/ttyUSB0"),
    ],
)
def test_describe(protocol: str, host: str, expected: str) -> None:
    # These end up in log messages and in the config flow's error details
    assert describe(build_params(protocol, host)) == expected


def test_lan_connections_pause_after_connecting_and_between_messages() -> None:
    # A direct connection to the inverter needs both gaps; see the comments in connection.py
    connection = build_connection(TCP, ADAPTERS["direct"], "1.2.3.4:502")

    assert ADAPTERS["direct"].connection_type == ConnectionType.LAN
    assert connection.connect_delay == 1.0
    assert connection.message_spacing == 0.03


def test_network_adapters_do_not_pause() -> None:
    connection = build_connection(TCP, ADAPTERS["network_other"], "1.2.3.4:502")

    assert connection.connect_delay == 0.0
    assert connection.message_spacing == 0.0


def test_serial_connections_pause_between_messages() -> None:
    connection = build_connection(SERIAL, ADAPTERS["serial_other"], "/dev/ttyUSB0")

    assert connection.connect_delay == 0.0
    assert connection.message_spacing == 0.03


async def test_connection_is_not_established_until_it_is_used() -> None:
    connection = build_connection(TCP, ADAPTERS["network_other"], "1.2.3.4:502")
    try:
        assert not connection.connected
    finally:
        await connection.close()
