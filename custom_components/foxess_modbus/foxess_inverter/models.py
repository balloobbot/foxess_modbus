"""The inverter models this library recognises, and the layout each one uses."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from .exceptions import UnsupportedInverterError
from .versions import FirmwareVersion


class ConnectionType(StrEnum):
    """How the inverter is reached.

    AUX is the RS485 port, directly or through an adapter. LAN is the
    inverter's own Ethernet port, which only the H1 family serves.
    """

    AUX = "aux"
    LAN = "lan"


class Layout(StrEnum):
    """A register layout: which blocks a model serves, and where."""

    H1_G1 = "h1_g1"
    H1_LAN = "h1_lan"
    H1_G2_PRE144 = "h1_g2_pre144"
    H1_G2 = "h1_g2"
    KH_PRE133 = "kh_pre133"
    KH = "kh"
    H3_PRE180 = "h3_pre180"
    H3 = "h3"
    AIO_H3_PRE101 = "aio_h3_pre101"
    AIO_H3 = "aio_h3"
    KUARA_H3 = "kuara_h3"
    H3_PRO_PRE122 = "h3_pro_pre122"
    H3_PRO = "h3_pro"
    H3_SMART = "h3_smart"
    EVO = "evo"
    H1_US = "h1_us"


@dataclass(frozen=True, kw_only=True)
class InverterModel:
    """One model family, matched on the model name the inverter reports."""

    name: str
    pattern: re.Pattern[str]
    # Layout per connection type, as {first firmware it does not apply to: layout}.
    # The None key holds the layout of the latest firmware.
    layouts: Mapping[ConnectionType, Mapping[FirmwareVersion | None, Layout]]
    # Capacity in W per value of the pattern's first group. A value not in the
    # map is read as kW, unless kw_fallback is False.
    capacity_map: Mapping[str, int] = field(default_factory=dict)
    kw_fallback: bool = True

    def capacity(self, model_name: str) -> int:
        """The inverter's rated power in W, from its model name."""
        match = self.pattern.match(model_name)
        if match is None:
            raise UnsupportedInverterError(model_name)
        value = match.group(1)
        if (capacity := self.capacity_map.get(value)) is not None:
            return capacity
        if not self.kw_fallback:
            raise UnsupportedInverterError(model_name)
        try:
            return int(float(value) * 1000)
        except ValueError as err:
            raise UnsupportedInverterError(model_name) from err

    def layout(
        self, connection_type: ConnectionType, manager_version: FirmwareVersion | None
    ) -> Layout:
        """The layout for this connection and manager firmware.

        An unknown firmware gets the latest layout. A connection type the model
        does not list falls back to AUX.
        """
        layouts = self.layouts.get(connection_type) or self.layouts[ConnectionType.AUX]
        if manager_version is not None:
            for before, layout in sorted(
                ((k, v) for k, v in layouts.items() if k is not None),
                key=lambda item: item[0],
            ):
                if manager_version < before:
                    return layout
        return layouts[None]

    @property
    def firmware_dependent(self) -> bool:
        """Whether the layout depends on the manager firmware."""
        return any(len(layouts) > 1 for layouts in self.layouts.values())


def _aux(
    layouts: Mapping[FirmwareVersion | None, Layout],
) -> dict[ConnectionType, Mapping[FirmwareVersion | None, Layout]]:
    return {ConnectionType.AUX: layouts}


_H1_CAPACITY = {"3.7": 3680}
_H1_G2 = _aux({FirmwareVersion(1, 44): Layout.H1_G2_PRE144, None: Layout.H1_G2})
_H1_G1: Mapping[ConnectionType, Mapping[FirmwareVersion | None, Layout]] = {
    ConnectionType.AUX: {None: Layout.H1_G1},
    ConnectionType.LAN: {None: Layout.H1_LAN},
}
_H3 = _aux({FirmwareVersion(1, 80): Layout.H3_PRE180, None: Layout.H3})
_H3_SMART = _aux({None: Layout.H3_SMART})
_H3_LEGACY = _aux({None: Layout.H3_PRE180})
_H3_PRO = _aux({FirmwareVersion(1, 22): Layout.H3_PRO_PRE122, None: Layout.H3_PRO})


def _model(
    name: str,
    pattern: str,
    layouts: Mapping[ConnectionType, Mapping[FirmwareVersion | None, Layout]],
    *,
    capacity_map: Mapping[str, int] | None = None,
    kw_fallback: bool = True,
) -> InverterModel:
    return InverterModel(
        name=name,
        pattern=re.compile(pattern),
        layouts=layouts,
        capacity_map=capacity_map or {},
        kw_fallback=kw_fallback,
    )


# Matched in order: the first pattern that matches wins, so a more specific
# pattern has to come before a more general one.
MODELS: tuple[InverterModel, ...] = (
    # E.g. H1-5.0-E-G2 or H1-5.0-E1-G2.
    _model("H1_G2", r"^H1-([\d\.]+)-E\d?-G2", _H1_G2, capacity_map=_H1_CAPACITY),
    # E.g. H1-5.0 and H1-5.0-E.
    _model("H1", r"^H1-([\d\.]+)", _H1_G1, capacity_map=_H1_CAPACITY),
    _model("AC1_G2", r"^AC1-([\d\.]+)-E-G2", _H1_G2, capacity_map=_H1_CAPACITY),
    # An OEM variant of the H1 G2.
    _model("P1", r"^P1-([\d\.]+)-E", _H1_G2, capacity_map=_H1_CAPACITY),
    _model("AC1", r"^AC1-([\d\.]+)", _H1_G1, capacity_map=_H1_CAPACITY),
    _model("AIO-H1", r"^AIO-H1-([\d\.]+)", _H1_G1, capacity_map=_H1_CAPACITY),
    _model(
        "AIO-AC1",
        r"^AIO-AC1-([\d\.]+)",
        _aux({None: Layout.H1_G1}),
        capacity_map=_H1_CAPACITY,
    ),
    # E.g. KH-10.5 and KH10.5.
    _model(
        "KH",
        r"^KH([\d\.]+)",
        _aux({FirmwareVersion(1, 33): Layout.KH_PRE133, None: Layout.KH}),
    ),
    # The -M suffix is an installer variant of the H3-Smart.
    # Some firmwares report SMART in upper case.
    _model("H3_SMART", r"^H3-([\d\.]+)-(?:(?i:Smart)|M)", _H3_SMART),
    _model("P3_SMART", r"^P3-([\d\.]+)-SH\d*$", _H3_SMART),
    _model("H3", r"^H3-([\d\.]+)", _H3),
    _model("AC3", r"^AC3-([\d\.]+)", _H3),
    _model(
        "AIO-H3",
        r"^AIO-H3-([\d\.]+)",
        _aux({FirmwareVersion(1, 1): Layout.AIO_H3_PRE101, None: Layout.AIO_H3}),
    ),
    # Kuara 6.0-3-H to 12.0-3-H are H3-6.0-E to H3-12.0-E.
    _model("KUARA-H3", r"^Kuara ([\d\.]+)-3-H$", _aux({None: Layout.KUARA_H3})),
    # Sonnenkraft SK-HWR-8 Smart is an H3-8.0-Smart.
    _model("SK-HWR-SMART", r"^SK-HWR-([\d\.]+) SMART", _H3_SMART),
    # Sonnenkraft SK-HWR-8 is an H3-8.0-E.
    _model("SK-HWR", r"^SK-HWR-([\d\.]+)", _H3_LEGACY),
    _model("STAR-H3", r"^STAR-H3-([\d\.]+)", _H3_LEGACY),
    # The number in 'SP R8KH3' does not give the power.
    _model(
        "SOLAVITA-SP",
        r"^SP R(\d+)KH3",
        _H3_LEGACY,
        capacity_map={"8": 10400, "10": 13000, "12": 15600},
        kw_fallback=False,
    ),
    _model("ATRONIX_AX", r"^AX ([\d\.]+)kW-3ph", _H3_LEGACY),
    _model("ATRONIX_AX_PLUS", r"^AX Plus ([\d\.]+)kW-3ph", _H3_SMART),
    # P3-Pro is the installer variant of the H3-Pro.
    _model(
        "H3_PRO",
        r"^[HP]3-Pro-([\d\.]+)",
        _H3_PRO,
    ),
    # EKD Ampere.StoragePro E3, e.g. ASP-12KW-3P-A-E3, is an H3-Pro.
    _model("AMPERE_STORAGE_PRO", r"^ASP-([\d\.]+)KW-3P", _H3_PRO),
    # Enpal I-X5 to I-X15.
    _model("ENPAL_IX", r"^I-X([\d\.]+)", _H3_SMART),
    # 1KOMMA5 1K5-HI-15-V1.
    _model("1KOMMA5", r"^1K5-HI-(\d+)-V1", _H3_SMART),
    # WEG SIW200H S series, an H1-US (split phase, 120/240 V). The number is
    # the power in 0.1 kW: S114 is 11.4 kW.
    _model(
        "WEG_SIW200H_US",
        r"^SIW200H S(\d+)",
        _aux({None: Layout.H1_US}),
        capacity_map={"114": 11400},
        kw_fallback=False,
    ),
    # E.g. EVO 10-5.0-H; the second number is the power.
    _model("EVO", r"^EVO \d+-([\d\.]+)-H$", _aux({None: Layout.EVO})),
    # Solarwatt Vision, e.g. VSN THREE 12KW, is an H3 Smart.
    _model("SOLARWATT_VISION", r"^VSN THREE ([\d\.]+)KW$", _H3_SMART),
)


def identify(model_name: str) -> InverterModel:
    """The model family of a model name, or raise UnsupportedInverterError."""
    for model in MODELS:
        if model.pattern.match(model_name):
            # Raises for a model name whose capacity cannot be read.
            model.capacity(model_name)
            return model
    raise UnsupportedInverterError(model_name)
