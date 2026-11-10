"""The top-level object for a FoxESS inverter."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any, Literal

from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusError,
    ModbusExceptionError,
)
from modbus_connection.model import (
    Component,
    Device,
    Raw,
    RegisterField,
    UpdateReport,
)

from .components.identity import async_read_model_name
from .exceptions import FoxEssError
from .layouts import LAYOUTS, LayoutSpec, Part, Poll, WorkMode
from .models import ConnectionType, InverterModel, Layout, identify
from .status import (
    H1_STATES,
    KH_STATES,
    GridStatus,
    InverterState,
    decode_state_bits,
)
from .values import (
    BMS_NOT_CONNECTED,
    CLAMPED,
    GATED,
    base_name,
    battery_suffix,
    plausible_range,
)
from .versions import FirmwareVersion

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

_LOGGER = logging.getLogger(__name__)

# The inverter takes a while to read back a written value. Until then, a read
# gives the value that was written.
WRITE_ECHO_SECONDS = 5.0

# The LAN port needs a pause after connecting, and quiet between messages.
LAN_CONNECT_DELAY = 1.0
LAN_MESSAGE_SPACING = 0.03

_PHASES = ("", "_r", "_s", "_t")
_BATTERIES = ("", "_1", "_2")


@dataclass(frozen=True, kw_only=True)
class ChargePeriod:
    """A period in which the inverter charges its battery."""

    force_charge: bool
    charge_from_grid: bool
    start: dt_time
    end: dt_time


def decode_time(code: int) -> dt_time | None:
    """Decode a charge period time, ``(hour << 8) | minute``."""
    hour, minute = code >> 8, code & 0xFF
    if hour > 23 or minute > 59:
        return None
    return dt_time(hour, minute)


def encode_time(value: dt_time) -> int:
    """Encode a charge period time."""
    return (value.hour << 8) | value.minute


@dataclass(frozen=True)
class _Field:
    """Where a value the inverter exposes comes from."""

    part: str
    attribute: str | None  # None for a derived value


class FoxEssInverter(Device):
    """A FoxESS inverter reached through a ``ModbusUnit``.

    Setup reads the model name and the firmware version, picks the register
    layout, and builds the parts that layout reads. Every value is then
    available by name through ``get()``, whatever part it comes from.
    """

    def __init__(
        self,
        unit: ModbusUnit,
        *,
        connection_type: ConnectionType = ConnectionType.AUX,
        max_read: int | None = None,
    ) -> None:
        """Set up the inverter on ``unit``.

        ``max_read`` caps the registers in one read, for an adapter that
        cannot serve more.
        """
        super().__init__(unit)
        self.connection_type = connection_type
        self.max_read = max_read
        if connection_type is ConnectionType.LAN:
            unit.require_connect_delay(LAN_CONNECT_DELAY)
            unit.set_message_spacing(LAN_MESSAGE_SPACING)

        self.model_name: str | None = None
        self.model: InverterModel | None = None
        self.layout: Layout | None = None
        self.spec: LayoutSpec | None = None
        self.parts: dict[str, Part] = {}
        # Fields a part dropped at setup because the inverter refused them.
        self.refused_fields: dict[str, list[str]] = {}
        self._fields: dict[str, _Field] = {}
        self._derived: dict[str, Any] = {}
        self._echo: dict[str, tuple[Any, float]] = {}

    # -- setup ---------------------------------------------------------------

    async def _async_setup(self) -> None:
        """Identify the inverter and build the parts of its layout."""
        name = await async_read_model_name(self.modbus_unit, self.max_read)
        model = identify(name)
        layout = await self._async_detect_layout(model)
        self.model_name, self.model = name, model
        self._build(layout)

        for part in self.parts.values():
            if part.poll is Poll.SETUP:
                try:
                    await getattr(self, part.name).async_update(notify=False)
                except ModbusExceptionError as err:
                    _LOGGER.debug("%s: %s refused: %s", name, part.name, err)
        await self._async_narrow_refused()

    async def _async_detect_layout(self, model: InverterModel) -> Layout:
        """Pick the layout from the manager firmware version.

        Each layout of the model may hold its versions in another block. Try
        them newest first: the first that answers gives the version.
        """
        layouts = (
            model.layouts.get(self.connection_type) or model.layouts[ConnectionType.AUX]
        )
        candidates = [layouts[None], *(v for k, v in layouts.items() if k is not None)]
        if len(candidates) == 1:
            return candidates[0]
        tried: set[type[Component]] = set()
        for candidate in candidates:
            spec = LAYOUTS[candidate]
            versions = next(p for p in spec.parts if p.name == "versions")
            if versions.component in tried:
                continue
            tried.add(versions.component)
            component = versions.component(self.modbus_unit)
            if self.max_read is not None:
                component.max_span = self.max_read
            try:
                await component.async_update(notify=False)
            except ModbusExceptionError:
                continue
            code = component.manager_version_code  # type: ignore[attr-defined]
            if code is None:
                continue
            version = FirmwareVersion.decode(code, hex_encoded=spec.version_hex[2])
            return model.layout(self.connection_type, version)
        return candidates[0]

    def _build(self, layout: Layout) -> None:
        """Create the parts of ``layout`` and index their fields."""
        spec = LAYOUTS[layout]
        self.layout, self.spec = layout, spec
        for part in spec.parts:
            component = part.component(self.modbus_unit, base_offset=part.base_offset)
            self._narrow(component, part)
            setattr(self, part.name, component)
            self.parts[part.name] = part
            for attribute in component.resolved_fields:
                self._add_field(attribute + part.suffix, _Field(part.name, attribute))
        self._add_derived()

    def _narrow(
        self, component: Component, part: Part, drop: Iterable[str] = ()
    ) -> None:
        """Restrict ``component`` to what ``part`` reads, and size its reads."""
        declared = component.declared_fields
        keep = part.only if part.only is not None else tuple(declared)
        keep = tuple(
            name for name in keep if name not in part.exclude and name not in drop
        )
        if keep != tuple(declared):
            component.restrict_fields(keep)
        if part.individual:
            component.register_ranges = tuple(
                (
                    declared[name].address,
                    declared[name].address + declared[name].count - 1,
                )
                for name in keep
            )
        if self.max_read is not None:
            component.max_span = self.max_read

    async def _async_narrow_refused(self) -> None:
        """Drop the fields of a part that the inverter refuses.

        A refused register fails its whole block read. Probe a refusing part
        field by field once, and keep the fields that answer, so one missing
        register does not take the whole part down.
        """
        for part in self.parts.values():
            if part.poll is Poll.SETUP:
                continue
            component: Component = getattr(self, part.name)
            try:
                await component.async_update(notify=False)
            except IllegalDataAddressError:
                pass
            except ModbusConnectionError:
                raise
            except ModbusError:
                # Not a refusal. The poll reports it if it lasts.
                continue
            else:
                continue
            refused = []
            for attribute, resolved in component.resolved_fields.items():
                read = (
                    self.modbus_unit.read_input_registers
                    if component.register_space == "input"
                    else self.modbus_unit.read_holding_registers
                )
                try:
                    await read(resolved.address, resolved.field.count)
                except IllegalDataAddressError:
                    refused.append(attribute)
            if not refused or len(refused) == len(component.resolved_fields):
                continue
            _LOGGER.warning(
                "%s: %s refuses %s, reading without them",
                self.model_name,
                part.name,
                ", ".join(refused),
            )
            self.refused_fields[part.name] = refused
            replacement = part.component(self.modbus_unit, base_offset=part.base_offset)
            self._narrow(replacement, part, drop=refused)
            setattr(self, part.name, replacement)
            for attribute in refused:
                self._fields.pop(attribute + part.suffix, None)
            self._add_derived()

    def _add_field(self, name: str, field: _Field) -> None:
        if name in self._fields and self._fields[name] != field:
            raise FoxEssError(f"{name} is served by two parts")
        self._fields[name] = field

    def _add_derived(self) -> None:
        """Index the values derived from other fields."""
        assert self.spec is not None
        self._derived = {}

        def derive(name: str, source: str, fn: Any) -> None:
            if source in self._fields and self._fields[source].attribute is not None:
                self._fields[name] = _Field(self._fields[source].part, None)
                self._derived[name] = fn

        for phase in _PHASES:
            ct = f"grid_ct_power{phase}"
            derive(f"feed_in_power{phase}", ct, lambda s=ct: _positive(self.get(s)))
            derive(
                f"grid_consumption_power{phase}",
                ct,
                lambda s=ct: _negative(self.get(s)),
            )
        for battery in _BATTERIES:
            power = f"battery_power{battery}"
            derive(
                f"battery_discharge_power{battery}",
                power,
                lambda s=power: _positive(self.get(s)),
            )
            derive(
                f"battery_charge_power{battery}",
                power,
                lambda s=power: _negative(self.get(s)),
            )
        pv_powers = [
            f"pv{n}_power" for n in range(1, 7) if f"pv{n}_power" in self._fields
        ]
        if pv_powers:
            derive(
                "pv_power", pv_powers[0], lambda: _sum(self.get(n) for n in pv_powers)
            )
        for kind in ("master", "slave", "manager"):
            derive(
                f"{kind}_version",
                f"{kind}_version_code",
                lambda kind=kind: self._version(kind),
            )
        if self.spec.grid_statuses:
            derive("grid_status", "grid_status_code", self._decode_grid_status)
        if self.spec.faults is not None:
            table, codes = self.spec.faults
            derive("faults", codes[0], lambda: self._decode_faults(table, codes))
        if "status_1" in self._fields:
            derive("inverter_state", "status_1", self._decode_state_bits)
        elif self.spec.states is not None:
            derive("inverter_state", "state_code", self._decode_state_map)
        elif "inverter_state_code" in self._fields:
            derive("inverter_state", "inverter_state_code", self._decode_state_code)
        if self.spec.work_modes:
            derive("work_mode", "work_mode_code", self._decode_work_mode)
        if self.spec.charge_periods:
            for n in (1, 2):
                prefix = f"charge_period_{n}"
                for end in ("start", "end"):
                    code = f"{prefix}_{end}_code"
                    derive(f"{prefix}_{end}", code, lambda s=code: _time(self.get(s)))
                derive(
                    f"{prefix}_force_charge",
                    f"{prefix}_start_code",
                    lambda n=n: self._force_charge(n),
                )
                derive(
                    f"{prefix}_charge_from_grid",
                    f"{prefix}_charge_from_grid_code",
                    lambda s=f"{prefix}_charge_from_grid_code": _flag(self.get(s)),
                )

    # -- reading -------------------------------------------------------------

    @property
    def capacity(self) -> int | None:
        """The rated power in W."""
        if self.model is None or self.model_name is None:
            return None
        return self.model.capacity(self.model_name)

    @property
    def fields(self) -> list[str]:
        """The names of every value this inverter serves."""
        return list(self._fields)

    def has(self, name: str) -> bool:
        """Whether this inverter serves ``name``."""
        return name in self._fields

    def part_of(self, name: str) -> str:
        """The part a value is read with, as an UpdateReport names it."""
        return self._fields[name].part

    def get(self, name: str) -> Any:
        """The current value of ``name``, or None if it has no value."""
        field = self._fields.get(name)
        if field is None:
            return None
        if (echo := self._echo.get(name)) is not None:
            value, written_at = echo
            if time.monotonic() - written_at < WRITE_ECHO_SECONDS:
                return value
            del self._echo[name]
        if field.attribute is None:
            return self._derived[name]()
        value = getattr(getattr(self, field.part), field.attribute)
        return self._condition(name, value)

    def _condition(self, name: str, value: Any) -> Any:
        """Clamp, check and gate a raw reading."""
        if value is None:
            return None
        if CLAMPED.match(name) and value < 0:
            value = 0
        bounds = plausible_range(name)
        component = getattr(self, self._fields[name].part)
        override = getattr(component, "plausible", {}).get(name)
        if override is not None:
            bounds = override
        if bounds is not None:
            low, high = bounds
            if (low is not None and value < low) or (high is not None and value > high):
                _LOGGER.debug("%s: %s out of range: %s", self.model_name, name, value)
                return None
        if base_name(name) in GATED:
            gate = f"bms_connect_state{battery_suffix(name)}"
            if gate not in self._fields:
                gate = "bms_connect_state"
            state = self.get(gate) if gate in self._fields else None
            if state in BMS_NOT_CONNECTED:
                return None
        return value

    def _version(self, kind: str) -> FirmwareVersion | None:
        assert self.spec is not None
        code = self.get(f"{kind}_version_code")
        if code is None:
            return None
        index = ("master", "slave", "manager").index(kind)
        return FirmwareVersion.decode(code, hex_encoded=self.spec.version_hex[index])

    @property
    def manager_version(self) -> FirmwareVersion | None:
        """The manager firmware version."""
        return self._version("manager")

    def _decode_faults(self, table: Any, codes: Sequence[str]) -> list[str] | None:
        words = [self.get(code) for code in codes]
        if any(word is None for word in words):
            return None
        decoded: list[str] = table.decode(words)
        return decoded

    def _decode_state_bits(self) -> InverterState | None:
        assert self.spec is not None
        status_1 = self.get("status_1")
        off_grid = self.get(self.spec.off_grid_status)
        if status_1 is None or off_grid is None:
            return None
        return decode_state_bits(status_1, off_grid)

    def _decode_state_map(self) -> InverterState | None:
        assert self.spec is not None and self.spec.states is not None
        code = self.get("state_code")
        return None if code is None else self.spec.states.get(code)

    def _decode_grid_status(self) -> GridStatus | None:
        assert self.spec is not None
        code: int | None = self.get("grid_status_code")
        if code is None or code >= len(self.spec.grid_statuses):
            return None
        return self.spec.grid_statuses[code]

    def _decode_state_code(self) -> InverterState | None:
        code = self.get("inverter_state_code")
        states = (
            KH_STATES if self.layout in (Layout.KH, Layout.KH_PRE133) else H1_STATES
        )
        if code is None or code >= len(states):
            return None
        return states[code]

    def _decode_work_mode(self) -> WorkMode | None:
        assert self.spec is not None
        code = self.get("work_mode_code")
        if code is None:
            return None
        mode = self.spec.work_modes.get(code)
        if mode is None:
            _LOGGER.warning("%s: unknown work mode %s", self.model_name, code)
        return mode

    def _force_charge(self, n: int) -> bool | None:
        start = self.get(f"charge_period_{n}_start_code")
        end = self.get(f"charge_period_{n}_end_code")
        if start is None or end is None:
            return None
        return bool(start or end)

    @property
    def work_modes(self) -> list[WorkMode]:
        """The work modes this inverter offers."""
        assert self.spec is not None
        return list(self.spec.work_modes.values())

    # -- polling -------------------------------------------------------------

    def _names(self, poll: Poll) -> tuple[str, ...]:
        return tuple(name for name, part in self.parts.items() if part.poll is poll)

    async def async_update_readings(self) -> UpdateReport:
        """Refresh what the inverter measures."""
        await self.async_ensure_setup()
        return await self.async_poll(self._names(Poll.READINGS))

    async def async_update_settings(self) -> UpdateReport:
        """Refresh what the inverter has been configured to do."""
        await self.async_ensure_setup()
        return await self.async_poll(self._names(Poll.SETTINGS))

    async def async_update_versions(self) -> UpdateReport:
        """Read the firmware versions again."""
        await self.async_ensure_setup()
        return await self.async_poll(self._names(Poll.SETUP))

    async def async_update(self) -> UpdateReport:
        """Refresh readings and settings."""
        report = await self.async_update_readings()
        return await self.async_poll(self._names(Poll.SETTINGS), report)

    async def async_read_raw(self, names: Iterable[str] | None = None) -> Raw:
        """Every register this inverter reads, undecoded, for diagnostics."""
        await self.async_ensure_setup()
        return await super().async_read_raw(self.parts if names is None else names)

    # -- writing -------------------------------------------------------------

    def is_writable(self, name: str) -> bool:
        """Whether ``name`` can be set with ``async_set()``."""
        field = self._fields.get(name)
        if field is None or field.attribute is None:
            return False
        component: Component = getattr(self, field.part)
        return bool(component.resolved_fields[field.attribute].field.writable)

    async def async_set(self, name: str, value: Any) -> None:
        """Write a setting."""
        field = self._fields[name]
        if field.attribute is None:
            raise FoxEssError(f"{name} is derived and cannot be written")
        writer = self._writer(field.part)
        await writer.write(field.attribute, value)
        # Echo the value as a read gives it back: scaled, and of its type.
        codec = writer.resolved_fields[field.attribute].field
        if isinstance(codec, RegisterField):
            value = codec.decode(codec.encode(value))
        self._echo[name] = (value, time.monotonic())

    def _writer(self, part_name: str) -> Component:
        """The component to write a part's fields with.

        A part read from input registers is written in holding registers at
        the same addresses.
        """
        component: Component = getattr(self, part_name)
        if component.register_space == "holding":
            return component
        part = self.parts[part_name]
        holding: type[Component] = type(
            f"{part.component.__name__}Writer",
            (part.component,),
            {"register_space": "holding"},
        )
        return holding(self.modbus_unit, base_offset=part.base_offset)

    async def async_set_work_mode(self, mode: WorkMode) -> None:
        """Set the work mode."""
        assert self.spec is not None
        code = next(
            (code for code, m in self.spec.work_modes.items() if m is mode), None
        )
        if code is None:
            raise FoxEssError(f"{self.model_name} has no work mode {mode}")
        await self.async_set("work_mode_code", code)
        self._echo["work_mode"] = (mode, time.monotonic())

    def charge_period(self, n: int) -> ChargePeriod | None:
        """Charge period 1 or 2 as last read, or None if it is unknown."""
        start, end = (
            self.get(f"charge_period_{n}_start"),
            self.get(f"charge_period_{n}_end"),
        )
        force = self.get(f"charge_period_{n}_force_charge")
        grid = self.get(f"charge_period_{n}_charge_from_grid")
        if start is None or end is None or force is None or grid is None:
            return None
        return ChargePeriod(
            force_charge=force, charge_from_grid=grid, start=start, end=end
        )

    async def async_set_charge_periods(self, periods: Sequence[ChargePeriod]) -> None:
        """Write both charge periods in one request.

        The inverter takes the six registers of the two periods together. A
        period without force charge is written with start and end 0.
        """
        assert self.spec is not None
        if not self.spec.charge_periods:
            raise FoxEssError(f"{self.model_name} has no charge periods")
        if len(periods) != 2:
            raise FoxEssError("give both charge periods")
        values: list[int] = []
        for period in periods:
            values += [
                int(period.charge_from_grid),
                encode_time(period.start) if period.force_charge else 0,
                encode_time(period.end) if period.force_charge else 0,
            ]
        field = self._fields["charge_period_1_charge_from_grid_code"]
        component: Component = getattr(self, field.part)
        address = component.resolved_fields[field.attribute or ""].address
        await self.modbus_unit.write_registers(address, values)
        now = time.monotonic()
        for n in (1, 2):
            prefix = f"charge_period_{n}"
            codes = values[(n - 1) * 3 : n * 3]
            for suffix, code in zip(
                ("charge_from_grid_code", "start_code", "end_code"), codes, strict=True
            ):
                self._echo[f"{prefix}_{suffix}"] = (code, now)

    async def async_read_registers(
        self, address: int, count: int, space: Literal["holding", "input"]
    ) -> list[int]:
        """Read raw registers."""
        if space == "input":
            return await self.modbus_unit.read_input_registers(address, count)
        return await self.modbus_unit.read_holding_registers(address, count)

    async def async_write_registers(self, address: int, values: Sequence[int]) -> None:
        """Write raw holding registers: one with FC06, more with FC16."""
        words = [value & 0xFFFF for value in values]
        if len(words) == 1:
            await self.modbus_unit.write_register(address, words[0])
        else:
            await self.modbus_unit.write_registers(address, words)

    def describe(self, name: str) -> Mapping[str, Any]:
        """Where a field sits on the device: space, address, words, scale, sign."""
        field = self._fields[name]
        if field.attribute is None:
            raise FoxEssError(f"{name} is derived")
        component: Component = getattr(self, field.part)
        resolved = component.resolved_fields[field.attribute]
        return {
            "space": component.register_space,
            "address": resolved.address,
            "count": resolved.field.count,
            "scale": getattr(resolved.field, "scale", None),
            "signed": getattr(resolved.field, "signed", None),
            "word_order": getattr(resolved.field, "word_order", "big"),
        }


def _positive(value: float | None) -> float | None:
    return None if value is None else max(value, 0)


def _negative(value: float | None) -> float | None:
    return None if value is None else (abs(value) if value < 0 else 0)


def _sum(values: Iterable[float | None]) -> float | None:
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += value
    return round(total, 3)


def _time(code: int | None) -> dt_time | None:
    return None if code is None else decode_time(code)


def _flag(code: int | None) -> bool | None:
    return None if code is None else code > 0
