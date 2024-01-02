"""Polyaire AirTouch Climate Devices."""


import logging
from typing import Any, Optional

import pyairtouch
from homeassistant.components import climate
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import devices, entities
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up the AirTouch climate devices."""
    api_objects = hass.data[DOMAIN][config_entry.entry_id]

    discovered_entities: list[climate.ClimateEntity] = []

    for airtouch in api_objects:
        airtouch_device = devices.AirTouchDevice(hass, config_entry.entry_id, airtouch)

        for airtouch_ac in airtouch.air_conditioners:
            ac_device = airtouch_device.ac_device(airtouch_ac)
            ac_entity = AcClimateEntity(
                ac_device=ac_device,
                airtouch_ac=airtouch_ac,
            )
            discovered_entities.append(ac_entity)

            # Only zones with temperature sensors can be climate entities
            temp_zones = (zone for zone in airtouch_ac.zones if zone.has_temp_sensor)
            for airtouch_zone in temp_zones:
                zone_device = ac_device.zone_device(airtouch_zone)
                zone_entity = ZoneClimateEntity(
                    zone_device_info=zone_device,
                    airtouch_ac=airtouch_ac,
                    airtouch_zone=airtouch_zone,
                )
                discovered_entities.append(zone_entity)

    _LOGGER.debug("Found entities %s", discovered_entities)

    async_add_devices(discovered_entities)


_AC_TO_CLIMATE_HVAC_MODE = {
    pyairtouch.AcMode.AUTO: climate.HVACMode.HEAT_COOL,
    pyairtouch.AcMode.HEAT: climate.HVACMode.HEAT,
    pyairtouch.AcMode.DRY: climate.HVACMode.DRY,
    pyairtouch.AcMode.FAN: climate.HVACMode.FAN_ONLY,
    pyairtouch.AcMode.COOL: climate.HVACMode.COOL,
    pyairtouch.AcMode.AUTO_HEAT: climate.HVACMode.HEAT_COOL,
    pyairtouch.AcMode.AUTO_COOL: climate.HVACMode.HEAT_COOL,
}

# Excludes HVACMode.OFF which translates to a power control request for AirTouch.
_CLIMATE_TO_AC_HVAC_MODE = {
    climate.HVACMode.HEAT_COOL: pyairtouch.AcMode.AUTO,
    climate.HVACMode.HEAT: pyairtouch.AcMode.HEAT,
    climate.HVACMode.DRY: pyairtouch.AcMode.DRY,
    climate.HVACMode.FAN_ONLY: pyairtouch.AcMode.FAN,
    climate.HVACMode.COOL: pyairtouch.AcMode.COOL,
}

_AC_TO_CLIMATE_HVAC_ACTION = {
    pyairtouch.AcMode.AUTO: climate.HVACAction.IDLE,
    pyairtouch.AcMode.HEAT: climate.HVACAction.HEATING,
    pyairtouch.AcMode.DRY: climate.HVACAction.DRYING,
    pyairtouch.AcMode.FAN: climate.HVACAction.FAN,
    pyairtouch.AcMode.COOL: climate.HVACAction.COOLING,
    pyairtouch.AcMode.AUTO_HEAT: climate.HVACAction.HEATING,
    pyairtouch.AcMode.AUTO_COOL: climate.HVACAction.COOLING,
}

_AC_TO_CLIMATE_FAN_MODE = {
    pyairtouch.AcFanSpeed.AUTO: climate.FAN_AUTO,
    pyairtouch.AcFanSpeed.QUIET: "quiet",
    pyairtouch.AcFanSpeed.LOW: climate.FAN_LOW,
    pyairtouch.AcFanSpeed.MEDIUM: climate.FAN_MEDIUM,
    pyairtouch.AcFanSpeed.HIGH: climate.FAN_HIGH,
    pyairtouch.AcFanSpeed.POWERFUL: "powerful",
    pyairtouch.AcFanSpeed.TURBO: "turbo",
    pyairtouch.AcFanSpeed.INTELLIGENT_AUTO: "intelligent",
}
_CLIMATE_TO_AC_FAN_MODE = {value: key for key, value in _AC_TO_CLIMATE_FAN_MODE.items()}


class AcClimateEntity(entities.AirTouchAcEntity, climate.ClimateEntity):
    """A climate entity for an AirTouch Air Conditioner."""

    _attr_name = None  # Name comes from the device info
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        ac_device: devices.AcDevice,
        airtouch_ac: pyairtouch.AirConditioner,
    ) -> None:
        super().__init__(
            ac_device=ac_device,
            airtouch_ac=airtouch_ac,
        )

        self._attr_supported_features = (
            climate.ClimateEntityFeature.FAN_MODE
            | climate.ClimateEntityFeature.TARGET_TEMPERATURE
            | climate.ClimateEntityFeature.PRESET_MODE
        )

        # The Climate Entity groups the OFF Power State into the HVACMode
        self._attr_hvac_modes = [climate.HVACMode.OFF] + [
            _AC_TO_CLIMATE_HVAC_MODE[mode] for mode in airtouch_ac.supported_modes
        ]
        self._attr_fan_modes = [
            _AC_TO_CLIMATE_FAN_MODE[fan_speed]
            for fan_speed in airtouch_ac.supported_fan_speeds
        ]

    @property
    def preset_modes(self) -> list[str]:
        return [
            climate.PRESET_NONE,
            climate.PRESET_AWAY,
            climate.PRESET_SLEEP,
        ]

    @property
    def current_temperature(self) -> Optional[float]:
        return self._airtouch_ac.current_temp

    @property
    def target_temperature(self) -> Optional[float]:
        return self._airtouch_ac.set_point

    @property
    def max_temp(self) -> float:
        return self._airtouch_ac.max_set_point

    @property
    def min_temp(self) -> float:
        return self._airtouch_ac.min_set_point

    @property
    def fan_mode(self) -> str:
        return _AC_TO_CLIMATE_FAN_MODE[self._airtouch_ac.fan_speed]

    @property
    def hvac_mode(self) -> climate.HVACMode:
        match self._airtouch_ac.power_state:
            case pyairtouch.AcPowerState.OFF | pyairtouch.AcPowerState.OFF_AWAY:
                return climate.HVACMode.OFF
            case _:
                return _AC_TO_CLIMATE_HVAC_MODE[self._airtouch_ac.mode]

    @property
    def hvac_action(self) -> climate.HVACAction:
        match self._airtouch_ac.power_state:
            case pyairtouch.AcPowerState.OFF | pyairtouch.AcPowerState.OFF_AWAY:
                return climate.HVACAction.OFF
            case _:
                return _AC_TO_CLIMATE_HVAC_ACTION[self._airtouch_ac.mode]

    @property
    def preset_mode(self) -> str:
        match self._airtouch_ac.power_state:
            case pyairtouch.AcPowerState.OFF_AWAY | pyairtouch.AcPowerState.ON_AWAY:
                return climate.PRESET_AWAY
            case pyairtouch.AcPowerState.SLEEP:
                return climate.PRESET_SLEEP
            case _:
                return climate.PRESET_NONE

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._airtouch_ac.set_fan_speed(_CLIMATE_TO_AC_FAN_MODE[fan_mode])

    async def async_set_hvac_mode(self, hvac_mode: climate.HVACMode) -> None:
        if hvac_mode == climate.HVACMode.OFF:
            await self._airtouch_ac.set_power(pyairtouch.AcPowerControl.TURN_OFF)
        else:
            await self._airtouch_ac.set_mode(
                _CLIMATE_TO_AC_HVAC_MODE[hvac_mode], power_on=True
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        match preset_mode:
            case climate.PRESET_AWAY:
                await self._airtouch_ac.set_power(pyairtouch.AcPowerControl.SET_TO_AWAY)
            case climate.PRESET_SLEEP:
                await self._airtouch_ac.set_power(
                    pyairtouch.AcPowerControl.SET_TO_SLEEP
                )
            case _:
                _LOGGER.warning("Unsupported preset mode: %s", preset_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:  # noqa: ANN401
        temperature: float = kwargs[climate.ATTR_TEMPERATURE]
        await self._airtouch_ac.set_set_point(temperature)


_ZONE_TO_CLIMATE_FAN_MODE = {
    pyairtouch.ZonePowerState.OFF: climate.FAN_OFF,
    pyairtouch.ZonePowerState.ON: climate.FAN_ON,
    pyairtouch.ZonePowerState.TURBO: "turbo",
}
_CLIMATE_TO_ZONE_FAN_MODE = {
    value: key for key, value in _ZONE_TO_CLIMATE_FAN_MODE.items()
}


class ZoneClimateEntity(entities.AirTouchZoneEntity, climate.ClimateEntity):
    """A climate entity for an AirTouch Zone."""

    _attr_name = None  # Name comes from the device info
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        climate.ClimateEntityFeature.FAN_MODE
        | climate.ClimateEntityFeature.TARGET_TEMPERATURE
    )

    def __init__(
        self,
        zone_device_info: devices.ZoneDevice,
        airtouch_ac: pyairtouch.AirConditioner,
        airtouch_zone: pyairtouch.Zone,
    ) -> None:
        super().__init__(
            zone_device=zone_device_info,
            airtouch_zone=airtouch_zone,
        )
        self._airtouch_ac = airtouch_ac

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._airtouch_ac.subscribe_ac_state(self._async_on_ac_update)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        self._airtouch_ac.unsubscribe_ac_state(self._async_on_ac_update)

    @property
    def fan_modes(self) -> list[str]:
        return list(set(_ZONE_TO_CLIMATE_FAN_MODE.values()))

    @property
    def hvac_modes(self) -> list[climate.HVACMode]:
        # The Zone can either be off, or on in the current mode of the AC
        return [
            climate.HVACMode.OFF,
            _AC_TO_CLIMATE_HVAC_MODE[self._airtouch_ac.mode],
        ]

    @property
    def current_temperature(self) -> Optional[float]:
        return self._airtouch_zone.current_temp

    @property
    def target_temperature(self) -> Optional[float]:
        return self._airtouch_zone.set_point

    @property
    def fan_mode(self) -> str:
        return _ZONE_TO_CLIMATE_FAN_MODE[self._airtouch_zone.power_state]

    @property
    def hvac_mode(self) -> climate.HVACMode:
        if self._airtouch_zone.power_state == pyairtouch.ZonePowerState.OFF:
            return climate.HVACMode.OFF

        # If the Zone is on then the mode is as per the parent AC mode
        match self._airtouch_ac.power_state:
            case pyairtouch.AcPowerState.OFF | pyairtouch.AcPowerState.OFF_AWAY:
                return climate.HVACMode.OFF
            case _:
                return _AC_TO_CLIMATE_HVAC_MODE[self._airtouch_ac.mode]

    async def async_set_temperature(self, **kwargs: Any) -> None:  # noqa: ANN401
        temperature: float = kwargs[climate.ATTR_TEMPERATURE]
        await self._airtouch_zone.set_set_point(temperature)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._airtouch_zone.set_power(_CLIMATE_TO_ZONE_FAN_MODE[fan_mode])

    async def async_set_hvac_mode(self, hvac_mode: climate.HVACMode) -> None:
        # Any HVACMode other than OFF is a request to turn the zone on.
        power_state = pyairtouch.ZonePowerState.ON
        if hvac_mode == climate.HVACMode.OFF:
            power_state = pyairtouch.ZonePowerState.OFF
        await self._airtouch_zone.set_power(power_state)

    async def _async_on_ac_update(self, _: int) -> None:
        # We only really need to trigger an update if the AC Mode or Power State
        # have been updated. However this update isn't triggered that often and
        # Home Assistant filters no-change updates internally.
        self.async_schedule_update_ha_state()