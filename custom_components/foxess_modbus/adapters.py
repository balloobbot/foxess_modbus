"""The adapters that connect an inverter, and what each one needs."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum

from .const import PROTOCOL_RTU_OVER_TCP
from .const import PROTOCOL_SERIAL
from .const import PROTOCOL_TCP
from .const import PROTOCOL_UDP
from .foxess_inverter import ConnectionType

_WIKI = "https://github.com/nathanmarlor/foxess_modbus/wiki/"


class AdapterType(StrEnum):
    """How the adapter reaches the inverter."""

    DIRECT = "direct"
    SERIAL = "serial"
    NETWORK = "network"


@dataclass(frozen=True, kw_only=True)
class Adapter:
    """An adapter, and the defaults that suit it."""

    id: str
    type: AdapterType
    setup_link: str
    protocols: tuple[str, ...]
    recommended_protocol: str | None = None
    # The most registers the adapter serves in one read.
    max_read: int = 20
    # Seconds between polls, per protocol.
    poll_interval: dict[str, int] = field(default_factory=dict)
    default_device: str = "/dev/ttyUSB0"

    @property
    def connection_type(self) -> ConnectionType:
        """Only a direct connection uses the inverter's LAN port."""
        return ConnectionType.LAN if self.type is AdapterType.DIRECT else ConnectionType.AUX

    def default_poll_interval(self, protocol: str) -> int:
        """The seconds between polls this adapter copes with."""
        return self.poll_interval.get(protocol, 10)


# The USR-W610 drops reads of more than 8 registers, and needs more time
# between polls over TCP.
_W610_MAX_READ = 8
_W610_POLL_INTERVAL = {PROTOCOL_TCP: 15}
_NETWORK = (PROTOCOL_TCP, PROTOCOL_UDP)

# Stored in config entries: never rename or remove an id. The order here is
# the order the config flow shows.
ADAPTERS: dict[str, Adapter] = {
    adapter.id: adapter
    for adapter in (
        Adapter(
            id="direct",
            type=AdapterType.DIRECT,
            setup_link=_WIKI + "Direct-Ethernet-Connection-to-Inverter",
            protocols=(PROTOCOL_TCP,),
            max_read=100,
        ),
        Adapter(
            id="dsd_tech_sh_u10",
            type=AdapterType.SERIAL,
            setup_link=_WIKI + "DSD-TECH-SH-U10",
            protocols=(PROTOCOL_SERIAL,),
            max_read=100,
        ),
        Adapter(
            id="runcci_yun_usb_to_rs485_converter",
            type=AdapterType.SERIAL,
            setup_link=_WIKI + "RUNCCI-YUN-USB-to-RS485-Converter",
            protocols=(PROTOCOL_SERIAL,),
        ),
        Adapter(
            id="waveshare_usb_to_rs485_b",
            type=AdapterType.SERIAL,
            setup_link=_WIKI + "Waveshare-USB-to-RS485-%28B%29",
            protocols=(PROTOCOL_SERIAL,),
            max_read=100,
            default_device="/dev/ttyACM0",
        ),
        Adapter(
            id="serial_other",
            type=AdapterType.SERIAL,
            setup_link=_WIKI + "Other-Serial-Adapter",
            protocols=(PROTOCOL_SERIAL,),
        ),
        Adapter(
            id="elfin_ew11",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "Elfin-EW11",
            protocols=_NETWORK,
            max_read=100,
        ),
        Adapter(
            id="usr_tcp232_304",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "USR-TCP232-304",
            protocols=(PROTOCOL_RTU_OVER_TCP,),
            max_read=100,
        ),
        Adapter(
            id="usr_tcp232_410s",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "USR-TCP232-410s",
            protocols=_NETWORK,
            max_read=100,
        ),
        Adapter(
            id="usr_w610",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "USR-W610",
            protocols=_NETWORK,
            recommended_protocol=PROTOCOL_UDP,
            max_read=_W610_MAX_READ,
            poll_interval=_W610_POLL_INTERVAL,
        ),
        Adapter(
            id="waveshare_rs485_to_eth_b",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "Waveshare-RS485-to-ETH-%28B%29",
            protocols=_NETWORK,
            max_read=100,
        ),
        Adapter(
            id="ebyte_na111_series",
            type=AdapterType.NETWORK,
            setup_link="https://www.cdebyte.com/products/NA111-E",
            protocols=_NETWORK,
            max_read=100,
        ),
        Adapter(
            id="network_other",
            type=AdapterType.NETWORK,
            setup_link=_WIKI + "Other-Ethernet-Adapter",
            protocols=(*_NETWORK, PROTOCOL_RTU_OVER_TCP),
            max_read=_W610_MAX_READ,
            poll_interval=_W610_POLL_INTERVAL,
        ),
    )
}
