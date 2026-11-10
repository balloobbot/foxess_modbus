"""Config flow for FoxESS - Modbus."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigFlow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.config_entries import OptionsFlow
from homeassistant.const import CONF_DEVICE
from homeassistant.const import CONF_HOST
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import NumberSelector
from homeassistant.helpers.selector import NumberSelectorConfig
from homeassistant.helpers.selector import NumberSelectorMode
from homeassistant.helpers.selector import SelectSelector
from homeassistant.helpers.selector import SelectSelectorConfig
from homeassistant.helpers.selector import SelectSelectorMode
from homeassistant.helpers.selector import SerialPortSelector
from modbus_connection import ModbusConnectionError
from modbus_connection import ModbusError
from modbus_connection import ModbusTimeoutError

from .adapters import ADAPTERS
from .adapters import Adapter
from .adapters import AdapterType
from .connection import SERIAL_MESSAGE_SPACING
from .connection import build_params
from .const import CONF_ADAPTER
from .const import CONF_MAX_READ
from .const import CONF_POLL_INTERVAL
from .const import CONF_PROTOCOL
from .const import CONF_ROUND_VALUES
from .const import CONF_UNIT_ID
from .const import DEFAULT_PORT
from .const import DEFAULT_UNIT_ID
from .const import DOMAIN
from .const import PROTOCOL_SERIAL
from .foxess_inverter import FoxEssInverter
from .foxess_inverter import UnsupportedInverterError

_UNIT_ID_SELECTOR = NumberSelector(NumberSelectorConfig(min=1, max=247, mode=NumberSelectorMode.BOX))


def _unique_id(data: dict[str, Any]) -> str:
    """Name the inverter by how it is reached: there is no serial number."""
    if data[CONF_PROTOCOL] == PROTOCOL_SERIAL:
        where = data[CONF_DEVICE]
    else:
        where = f"{data[CONF_HOST]}:{data[CONF_PORT]}"
    return f"{data[CONF_PROTOCOL]}:{where}:{data[CONF_UNIT_ID]}"


async def _async_probe(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """The model name of the inverter, or raise why it cannot be reached."""
    adapter = ADAPTERS[data[CONF_ADAPTER]]
    async with async_get_temporary_unit(hass, build_params(data), data[CONF_UNIT_ID]) as unit:
        if data[CONF_PROTOCOL] == PROTOCOL_SERIAL:
            unit.set_message_spacing(SERIAL_MESSAGE_SPACING)
        inverter = FoxEssInverter(unit, connection_type=adapter.connection_type, max_read=adapter.max_read)
        await inverter.async_ensure_setup()
    assert inverter.model_name is not None
    return inverter.model_name


class FoxEssConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a FoxESS inverter."""

    VERSION = 2

    def __init__(self) -> None:
        """Start with no adapter chosen."""
        self._adapter: Adapter | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The options flow."""
        return FoxEssOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask how the inverter is connected."""
        if user_input is not None:
            adapter_type = AdapterType(user_input["adapter_type"])
            adapters = [a for a in ADAPTERS.values() if a.type is adapter_type]
            if len(adapters) == 1:
                self._adapter = adapters[0]
                return await self.async_step_connection()
            return await self.async_step_adapter(None, adapters=[a.id for a in adapters])
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required("adapter_type"): SelectSelector(
                        SelectSelectorConfig(
                            options=[t.value for t in AdapterType],
                            translation_key="adapter_type",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change how the inverter is connected."""
        return await self.async_step_user(user_input)

    async def async_step_adapter(
        self,
        user_input: dict[str, Any] | None = None,
        adapters: list[str] | None = None,
    ) -> ConfigFlowResult:
        """Ask which adapter it is."""
        if user_input is not None:
            self._adapter = ADAPTERS[user_input[CONF_ADAPTER]]
            return await self.async_step_connection()
        return self.async_show_form(
            step_id="adapter",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_ADAPTER): SelectSelector(
                        SelectSelectorConfig(
                            options=adapters or [],
                            translation_key="adapter",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask where the adapter is, and the inverter's unit id."""
        adapter = self._adapter
        assert adapter is not None
        errors: dict[str, str] = {}
        placeholders = {"setup_link": adapter.setup_link, "model": ""}
        if user_input is not None:
            data = {
                CONF_ADAPTER: adapter.id,
                CONF_PROTOCOL: adapter.protocols[0],
                CONF_PORT: DEFAULT_PORT,
                **user_input,
            }
            data[CONF_UNIT_ID] = int(data[CONF_UNIT_ID])
            if CONF_PORT in data:
                data[CONF_PORT] = int(data[CONF_PORT])
            try:
                model_name = await _async_probe(self.hass, data)
            except UnsupportedInverterError as err:
                errors["base"] = "unsupported_model"
                placeholders["model"] = err.model_name
            except (ModbusConnectionError, ModbusTimeoutError):
                errors["base"] = "cannot_connect"
            except ModbusError:
                errors["base"] = "cannot_communicate"
            except HomeAssistantError:
                errors["base"] = "link_in_use"
            else:
                return await self._async_finish(model_name, data)
        return self.async_show_form(
            step_id="serial" if adapter.type is AdapterType.SERIAL else "network",
            data_schema=self.add_suggested_values_to_schema(
                self._connection_schema(adapter), user_input or self._suggested()
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async_step_network = async_step_connection
    async_step_serial = async_step_connection

    def _suggested(self) -> dict[str, Any]:
        """Suggest the current settings when reconfiguring."""
        if self.source != SOURCE_RECONFIGURE:
            return {}
        return dict(self._get_reconfigure_entry().data)

    def _connection_schema(self, adapter: Adapter) -> probatio.Schema:
        if adapter.type is AdapterType.SERIAL:
            return probatio.Schema(
                {
                    probatio.Required(CONF_DEVICE, default=adapter.default_device): SerialPortSelector(),
                    probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _UNIT_ID_SELECTOR,
                }
            )
        schema: dict[Any, Any] = {}
        if len(adapter.protocols) > 1:
            schema[probatio.Required(CONF_PROTOCOL, default=adapter.recommended_protocol or adapter.protocols[0])] = (
                SelectSelector(SelectSelectorConfig(options=list(adapter.protocols), translation_key="protocol"))
            )
        schema[probatio.Required(CONF_HOST)] = str
        if adapter.type is AdapterType.NETWORK:
            schema[probatio.Required(CONF_PORT, default=DEFAULT_PORT)] = NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            )
        schema[probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID)] = _UNIT_ID_SELECTOR
        return probatio.Schema(schema)

    async def _async_finish(self, model_name: str, data: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(_unique_id(data))
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if self.unique_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(entry, unique_id=self.unique_id, data=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=model_name, data=data)


class FoxEssOptionsFlow(OptionsFlow):
    """Tune polling."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the poll interval, the read size and rounding."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        adapter = ADAPTERS[self.config_entry.data[CONF_ADAPTER]]
        protocol = self.config_entry.data[CONF_PROTOCOL]
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(
                    {
                        probatio.Optional(CONF_POLL_INTERVAL): NumberSelector(
                            NumberSelectorConfig(
                                min=1,
                                max=3600,
                                unit_of_measurement="s",
                                mode=NumberSelectorMode.BOX,
                            )
                        ),
                        probatio.Optional(CONF_MAX_READ): NumberSelector(
                            NumberSelectorConfig(min=1, max=125, mode=NumberSelectorMode.BOX)
                        ),
                        probatio.Optional(CONF_ROUND_VALUES, default=False): bool,
                    }
                ),
                self.config_entry.options,
            ),
            description_placeholders={
                "default_poll_interval": str(adapter.default_poll_interval(protocol)),
                "default_max_read": str(adapter.max_read),
            },
        )
