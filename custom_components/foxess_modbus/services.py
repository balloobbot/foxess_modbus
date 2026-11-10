"""Services: raw register access, and the charge periods."""

from __future__ import annotations

from datetime import time
from typing import Any

import probatio
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.core import ServiceResponse
from homeassistant.core import SupportsResponse
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_get_config_entry
from modbus_connection import ModbusError

from . import charge_periods
from .const import DOMAIN
from .coordinator import FoxEssConfigEntry
from .coordinator import FoxEssRuntimeData
from .foxess_inverter import ChargePeriod


def _values(value: Any) -> list[int]:
    """Values to write: a list, or a comma separated string."""
    if isinstance(value, str):
        value = [part for part in value.split(",") if part.strip()]
    return [probatio.All(probatio.Coerce(int), probatio.Range(-32768, 65535))(v) for v in value]


def _whole_minutes(value: Any) -> time:
    parsed: time = cv.time(value)
    if parsed.second:
        raise probatio.Invalid("charge periods start and end on a whole minute")
    return parsed


_PERIOD_SCHEMA = {
    probatio.Required("enable_force_charge"): cv.boolean,
    probatio.Required("enable_charge_from_grid"): cv.boolean,
    probatio.Optional("start"): _whole_minutes,
    probatio.Optional("end"): _whole_minutes,
}

READ_REGISTERS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required("start_address"): probatio.All(probatio.Coerce(int), probatio.Range(0, 65535)),
        probatio.Required("count"): probatio.All(probatio.Coerce(int), probatio.Range(1, 125)),
        probatio.Required("type"): probatio.In(["input", "holding"]),
    }
)
WRITE_REGISTERS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required("start_address"): probatio.All(probatio.Coerce(int), probatio.Range(0, 65535)),
        probatio.Required("values"): _values,
    }
)
UPDATE_CHARGE_PERIOD_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required("charge_period"): probatio.All(probatio.Coerce(int), probatio.In([1, 2])),
        **_PERIOD_SCHEMA,
    }
)
UPDATE_ALL_CHARGE_PERIODS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required("charge_periods"): probatio.All(
            cv.ensure_list, [probatio.Schema(_PERIOD_SCHEMA)], probatio.Length(2, 2)
        ),
    }
)


def _runtime_data(hass: HomeAssistant, call: ServiceCall) -> FoxEssRuntimeData:
    """The inverter a service call targets."""
    entry: FoxEssConfigEntry = async_get_config_entry(hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID])
    return entry.runtime_data


def _period(runtime_data: FoxEssRuntimeData, n: int, data: dict[str, Any]) -> ChargePeriod:
    """A charge period from service data. A disabled one keeps its times."""
    force = data["enable_force_charge"]
    if force and ("start" not in data or "end" not in data):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="charge_period_needs_times",
            translation_placeholders={"period": str(n)},
        )
    existing = charge_periods.current(runtime_data, n)
    return ChargePeriod(
        force_charge=force,
        charge_from_grid=data["enable_charge_from_grid"],
        start=data.get("start", existing.start),
        end=data.get("end", existing.end),
    )


def _has_charge_periods(runtime_data: FoxEssRuntimeData) -> None:
    if not runtime_data.inverter.has("charge_period_1_start"):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_charge_periods")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""

    async def read_registers(call: ServiceCall) -> ServiceResponse:
        runtime_data = _runtime_data(hass, call)
        start = call.data["start_address"]
        try:
            values = await runtime_data.inverter.async_read_registers(start, call.data["count"], call.data["type"])
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="read_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return {"values": {str(start + i): value for i, value in enumerate(values)}}

    async def write_registers(call: ServiceCall) -> None:
        runtime_data = _runtime_data(hass, call)
        try:
            await runtime_data.inverter.async_write_registers(call.data["start_address"], call.data["values"])
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def update_charge_period(call: ServiceCall) -> None:
        runtime_data = _runtime_data(hass, call)
        _has_charge_periods(runtime_data)
        n = call.data["charge_period"]
        await charge_periods.async_write(runtime_data, {n: _period(runtime_data, n, dict(call.data))})

    async def update_all_charge_periods(call: ServiceCall) -> None:
        runtime_data = _runtime_data(hass, call)
        _has_charge_periods(runtime_data)
        await charge_periods.async_write(
            runtime_data,
            {
                n: _period(runtime_data, n, data)
                for n, data in zip(charge_periods.PERIODS, call.data["charge_periods"], strict=True)
            },
        )

    hass.services.async_register(
        DOMAIN,
        "read_registers",
        read_registers,
        schema=READ_REGISTERS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, "write_registers", write_registers, schema=WRITE_REGISTERS_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        "update_charge_period",
        update_charge_period,
        schema=UPDATE_CHARGE_PERIOD_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "update_all_charge_periods",
        update_all_charge_periods,
        schema=UPDATE_ALL_CHARGE_PERIODS_SCHEMA,
    )
