"""Firmware versions as the inverter reports them."""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering


@total_ordering
@dataclass(frozen=True)
class FirmwareVersion:
    """A firmware version, e.g. 1.44."""

    major: int
    minor: int

    @classmethod
    def decode(cls, word: int, *, hex_encoded: bool) -> FirmwareVersion:
        """Decode a version register.

        Some registers hold the version in decimal (144 is 1.44). Others hold
        it per byte in hex (0x144 is 1.44).
        """
        if hex_encoded:
            major, minor = f"{word >> 8:X}", f"{word & 0xFF:02X}"
            # A byte with a hex letter has no decimal reading; keep its value.
            if major.isdecimal() and minor.isdecimal():
                return cls(int(major), int(minor))
            return cls(word >> 8, word & 0xFF)
        return cls(word // 100, word % 100)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, FirmwareVersion):
            return NotImplemented
        return (self.major, self.minor) < (other.major, other.minor)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor:02d}"
