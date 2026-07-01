"""Config flow: initial setup (with immediate device add) + options (manage devices later)."""
from __future__ import annotations

import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATT_SENSOR,
    CONF_DEVICES,
    CONF_DEVICE_IS_WALLBOX,
    CONF_DEVICE_NAME,
    CONF_DEVICE_POWER_KW,
    CONF_DEVICE_POWER_SENSOR,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_SWITCH,
    CONF_LOAD_SENSOR,
    CONF_MIN_SOC,
    CONF_SOC_SENSOR,
    CONF_SOLAR_SENSOR,
    DOMAIN,
)


def _global_settings_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_SOLAR_SENSOR, default=d.get(CONF_SOLAR_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_LOAD_SENSOR, default=d.get(CONF_LOAD_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_SOC_SENSOR, default=d.get(CONF_SOC_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="battery")
        ),
        vol.Required(CONF_BATT_SENSOR, default=d.get(CONF_BATT_SENSOR)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_BATTERY_CAPACITY_KWH, default=d.get(CONF_BATTERY_CAPACITY_KWH, 13.8)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=0.1, unit_of_measurement="kWh")
        ),
        vol.Required(CONF_MIN_SOC, default=d.get(CONF_MIN_SOC, 20)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=5, max=50, step=1, unit_of_measurement="%")
        ),
    })


def _device_schema() -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_DEVICE_NAME): str,
        vol.Required(CONF_DEVICE_SWITCH): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Optional(CONF_DEVICE_POWER_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power")
        ),
        vol.Required(CONF_DEVICE_POWER_KW, default=0.15): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0.05, max=22.0, step=0.05, unit_of_measurement="kW")
        ),
        vol.Optional(CONF_DEVICE_IS_WALLBOX, default=False): bool,
    })


def _next_device(devices: list[dict], user_input: dict) -> dict:
    max_prio = max((d.get(CONF_DEVICE_PRIORITY, 0) for d in devices), default=0)
    return {**user_input, CONF_DEVICE_PRIORITY: max_prio + 1, "_id": str(uuid.uuid4())}


class PVSurplusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: global sensors, then loop to add devices right away."""

    VERSION = 1

    def __init__(self) -> None:
        self._global_data: dict = {}
        self._devices: list[dict] = []

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._global_data = user_input
            return await self.async_step_device_intro()

        return self.async_show_form(
            step_id="user",
            data_schema=_global_settings_schema(),
            errors=errors,
        )

    async def async_step_device_intro(self, user_input: dict | None = None):
        """First chance to add a device right after the base setup."""
        return self.async_show_menu(
            step_id="device_intro",
            menu_options=["add_device", "finish_setup"],
        )

    async def async_step_add_device(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._devices.append(_next_device(self._devices, user_input))
            return await self.async_step_add_another()

        return self.async_show_form(
            step_id="add_device",
            data_schema=_device_schema(),
            errors=errors,
            description_placeholders={"count": str(len(self._devices))},
        )

    async def async_step_add_another(self, user_input: dict | None = None):
        return self.async_show_menu(
            step_id="add_another",
            menu_options=["add_device", "finish_setup"],
        )

    async def async_step_finish_setup(self, user_input: dict | None = None):
        return self.async_create_entry(
            title="PV Surplus Manager",
            data={**self._global_data, CONF_DEVICES: self._devices},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PVSurplusOptionsFlow(config_entry)


class PVSurplusOptionsFlow(OptionsFlow):
    """Options flow: manage devices and global settings after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._devices: list[dict] = list(config_entry.data.get(CONF_DEVICES, []))

    async def async_step_init(self, user_input: dict | None = None):
        menu_options = ["add_device"]
        if self._devices:
            menu_options.append("remove_device")
        menu_options += ["global_settings", "finish"]
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_global_settings(self, user_input: dict | None = None):
        if user_input is not None:
            new_data = {**self._config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="global_settings",
            data_schema=_global_settings_schema(self._config_entry.data),
        )

    async def async_step_add_device(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._devices.append(_next_device(self._devices, user_input))
            new_data = {**self._config_entry.data, CONF_DEVICES: self._devices}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_device",
            data_schema=_device_schema(),
            errors=errors,
            description_placeholders={"count": str(len(self._devices))},
        )

    async def async_step_remove_device(self, user_input: dict | None = None):
        if not self._devices:
            return await self.async_step_init()

        if user_input is not None:
            target = user_input["device"]
            self._devices = [d for d in self._devices if d[CONF_DEVICE_SWITCH] != target]
            new_data = {**self._config_entry.data, CONF_DEVICES: self._devices}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return await self.async_step_init()

        options = {
            d[CONF_DEVICE_SWITCH]: f"{d.get(CONF_DEVICE_NAME)} (Prio {d.get(CONF_DEVICE_PRIORITY)})"
            for d in self._devices
        }
        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
        )

    async def async_step_finish(self, user_input: dict | None = None):
        return self.async_create_entry(title="", data={})
