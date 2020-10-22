# -*- coding: utf-8 -*-
"""
Support for Riello's Besmart thermostats.
Be aware the thermostat may require more then 3 minute to refresh its states.

The thermostats support the season switch however this control will be managed with a 
different control.

version: 2
tested with home-assistant >= 0.96

Configuration example:

climate:
  - platform: Besmart
    name: Besmart Thermostat
    username: USERNAME
    password: 10080
    room: Soggiorno
    scan_interval: 10

logging options:

logger:
  default: info
  logs:
    custom_components.climate.besmart: debug
"""
import logging
from datetime import datetime, timedelta

import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_LOW,
    PLATFORM_SCHEMA,
    ClimateDevice,
)
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_OFF,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
)
from homeassistant.const import (
    ATTR_STATE,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_ROOM,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)

_LOGGER = logging.getLogger(__name__)
DEPENDENCIES = ["switch", "sensor"]
REQUIREMENTS = ["requests"]

DEFAULT_NAME = "Besmart Thermostat"
DEFAULT_TIMEOUT = 3

ATTR_MODE = "mode"
STATE_UNKNOWN = "unknown"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_ROOM): cv.string,
    }
)

SUPPORT_FLAGS = (
    SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE_RANGE | SUPPORT_TARGET_TEMPERATURE
)


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Besmart thermostats."""
    client = Besmart(config.get(CONF_USERNAME), config.get(CONF_PASSWORD))
    client.rooms()  # force init
    add_devices([Thermostat(config.get(CONF_NAME), config.get(CONF_ROOM), client)])


# pylint: disable=abstract-method
# pylint: disable=too-many-instance-attributes
class Besmart(object):
    """Representation of a Besmart thermostat."""

    BASE_URL = "http://www.besmart-home.com/Android_vokera_20160516/"
    LOGIN = "login.php"
    ROOM_MODE = "setRoomMode.php"
    ROOM_LIST = "getRoomList.php?deviceId={0}"
    ROOM_DATA = "getRoomData196.php?therId={0}&deviceId={1}"
    ROOM_PROGRAM = "getProgram.php?roomId={0}"
    ROOM_TEMP = "setRoomTemp.php"
    ROOM_ECON_TEMP = "setEconTemp.php"
    ROOM_FROST_TEMP = "setFrostTemp.php"
    ROOM_CONF_TEMP = "setComfTemp.php"
    GET_SETTINGS = "getSetting.php"
    SET_SETTINGS = "setSetting.php"

    def __init__(self, username, password):
        """Initialize the thermostat."""
        self._username = username
        self._password = password
        self._lastupdate = None
        self._device = None
        self._rooms = None
        self._timeout = 30
        self._s = requests.Session()

    def _fahToCent(self, temp):
        return str(round((temp - 32.0) / 1.8, 1))

    def _centToFah(self, temp):
        return str(round(32.0 + (temp * 1.8), 1))

    def login(self):
        try:
            resp = self._s.post(
                self.BASE_URL + self.LOGIN,
                data={"un": self._username, "pwd": self._password, "version": "32"},
                timeout=self._timeout,
            )
            if resp.ok:
                self._device = resp.json()
        except Exception as ex:
            _LOGGER.warning(ex)
            self._device = None

    def rooms(self):
        if not self._device:
            self.login()

        try:
            if self._device:
                resp = self._s.post(
                    self.BASE_URL + self.ROOM_LIST.format(self._device.get("deviceId")),
                    timeout=self._timeout,
                )
                if resp.ok:
                    self._lastupdate = datetime.now()
                    self._rooms = dict(
                        (y.get("name").lower(), y)
                        for y in filter(lambda x: x.get("id") != None, resp.json())
                    )
                    _LOGGER.debug("rooms: {}".format(self._rooms))
                    if len(self._rooms) == 0:
                        self._device = None
                        self._lastupdate = None
                        return None

                    return self._rooms
                else:
                    _LOGGER.debug("get rooms failed!")
        except Exception as ex:
            _LOGGER.warning(ex)
            self._device = None

        return None

    def roomdata(self, room):
        self.login()
        try:
            if self._device:
                resp = self._s.get(
                    self.BASE_URL
                    + self.ROOM_DATA.format(
                        room.get("therId"), self._device.get("deviceId")
                    ),
                    timeout=self._timeout,
                )
                if resp.ok:
                    return resp.json()
                else:
                    _LOGGER.debug("refresh roomdata failed for: {}".format(room))
        except Exception as ex:
            _LOGGER.warning(ex)
            self._device = None

        return None

    def program(self, room):
        self.login()
        try:
            resp = self._s.get(
                self.BASE_URL + self.ROOM_PROGRAM.format(room.get("id")),
                timeout=self._timeout,
            )
            if resp.ok:
                return resp.json()
        except Exception as ex:
            _LOGGER.warning(ex)
            self._device = None
        return None

    def roomByName(self, name):
        if self._lastupdate is None or datetime.now() - self._lastupdate > timedelta(
            seconds=120
        ):
            _LOGGER.debug("refresh rooms state")
            self.rooms()

        if self._rooms:
            return self.roomdata(self._rooms.get(name.lower()))
        return None

    def setRoomMode(self, room_name, mode):
        room = self.roomByName(room_name)

        if self._device and room:
            data = {
                "deviceId": self._device.get("deviceId"),
                "therId": room.get("roomMark"),
                "mode": mode,
            }

            resp = self._s.post(
                self.BASE_URL + self.ROOM_MODE, data=data, timeout=self._timeout
            )
            if resp.ok:
                msg = resp.json()
                _LOGGER.debug("resp: {}".format(msg))
                if msg.get("error") == 1:
                    return True

        return None

    def setRoomConfortTemp(self, room_name, new_temp):
        return self.setRoomTemp(room_name, new_temp, self.ROOM_CONF_TEMP)

    def setRoomECOTemp(self, room_name, new_temp):
        return self.setRoomTemp(room_name, new_temp, self.ROOM_ECON_TEMP)

    def setRoomFrostTemp(self, room_name, new_temp):
        return self.setRoomTemp(room_name, new_temp, self.ROOM_FROST_TEMP)

    def setRoomTemp(self, room_name, new_temp, url=None):
        url = url or self.ROOM_TEMP
        room = self.roomByName(room_name)
        if room and self._device.get("deviceId"):
            new_temp = round(new_temp, 1)
            _LOGGER.debug("room: {}".format(room))

            if room.get("tempUnit") in {"N/A", "0"}:
                tpCInt, tpCIntFloat = str(new_temp).split(".")
            else:
                tpCInt, tpCIntFloat = self._fahToCent(new_temp).split(".")

            _LOGGER.debug(
                "setRoomTemp: {} - {} - {}".format(new_temp, tpCInt, tpCIntFloat)
            )

            data = {
                "deviceId": self._device.get("deviceId"),
                "therId": room.get("roomMark"),
                "tempSet": tpCInt + "",
                "tempSetFloat": tpCIntFloat + "",
            }
            _LOGGER.debug("url: {}".format(self.BASE_URL + url))
            _LOGGER.debug("data: {}".format(data))
            resp = self._s.post(self.BASE_URL + url, data=data, timeout=self._timeout)
            if resp.ok:
                msg = resp.json()
                _LOGGER.debug("resp: {}".format(msg))
                if msg.get("error") == 1:
                    return True
        else:
            _LOGGER.warning("error on get the room by name: {}".format(room_name))

        return None

    def getSettings(self, room_name):
        room = self.roomByName(room_name)

        if self._device and room:
            data = {
                "deviceId": self._device.get("deviceId"),
                "therId": room.get("roomMark"),
            }

            resp = self._s.post(
                self.BASE_URL + self.GET_SETTINGS, data=data, timeout=self._timeout
            )
            if resp.ok:
                msg = resp.json()
                _LOGGER.debug("resp: {}".format(msg))
                if msg.get("error") == 0:
                    return msg

        return None

    def setSettings(self, room_name, season):
        room = self.roomByName(room_name)

        if self._device and room:
            old_data = self.getSettings(room_name)
            if old_data.get("error") == 0:
                min_temp_set_point_ip, min_temp_set_point_fp = str(
                    old_data.get("minTempSetPoint", "30.0")
                ).split(".")
                max_temp_set_point_ip, max_temp_set_point_fp = str(
                    old_data.get("maxTempSetPoint", "30.0")
                ).split(".")
                temp_curver_ip, temp_curver_fp = str(
                    old_data.get("tempCurver", "0.0")
                ).split(".")
                data = {
                    "deviceId": self._device.get("deviceId"),
                    "therId": room.get("roomMark"),
                    "minTempSetPointIP": min_temp_set_point_ip,
                    "minTempSetPointFP": min_temp_set_point_fp,
                    "maxTempSetPointIP": max_temp_set_point_ip,
                    "maxTempSetPointFP": max_temp_set_point_fp,
                    "sensorInfluence": old_data.get("sensorInfluence", "0"),
                    "tempCurveIP": temp_curver_ip,
                    "tempCurveFP": temp_curver_fp,
                    "unit": old_data.get("unit", "0"),
                    "season": season,
                    "boilerIsOnline": old_data.get("boilerIsOnline", "0"),
                }

                resp = self._s.post(
                    self.BASE_URL + self.SET_SETTINGS, data=data, timeout=self._timeout
                )
                if resp.ok:
                    msg = resp.json()
                    _LOGGER.debug("resp: {}".format(msg))
                    if msg.get("error") == 0:
                        return msg
        return None


# pylint: disable=abstract-method
# pylint: disable=too-many-instance-attributes
class Thermostat(ClimateDevice):
    """Representation of a Besmart thermostat."""

    # BeSmart thModel = 5
    # BeSmart WorkMode
    AUTO = 0  # 'Auto'
    MANUAL = 1  # 'Manuale - Confort'
    ECONOMY = 2  # 'Holiday - Economy'
    PARTY = 3  # 'Party - Confort'
    IDLE = 4  # 'Spento - Antigelo'

    PRESET_HA_TO_BESMART = {
        "AUTO": AUTO,
        "MANUAL": MANUAL,
        "ECO": ECONOMY,
        "PARTY": PARTY,
        "IDLE": IDLE,
    }

    PRESET_BESMART_TO_HA = {
        AUTO: "AUTO",
        MANUAL: "MANUAL",
        ECONOMY: "ECO",
        PARTY: "PARTY",
        IDLE: "IDLE",
    }
    PRESET_MODE_LIST = list(PRESET_HA_TO_BESMART)

    HVAC_MODE_LIST = (HVAC_MODE_COOL, HVAC_MODE_HEAT)
    HVAC_MODE_BESMART_TO_HA = {"1": HVAC_MODE_HEAT, "0": HVAC_MODE_COOL}

    # BeSmart Season
    HVAC_MODE_HA_BESMART = {HVAC_MODE_HEAT: "1", HVAC_MODE_COOL: "0"}

    def __init__(self, name, room, client):
        """Initialize the thermostat."""
        self._name = name
        self._room_name = room
        self._cl = client
        self._current_temp = 0
        self._current_state = self.IDLE
        self._current_operation = ""
        self._current_unit = 0
        self._tempSetMark = 0
        self._heating_state = False
        self._battery = "0"
        self._frostT = 0
        self._saveT = 0
        self._comfT = 0
        self._season = "1"
        self.update()

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._comfT

    @property
    def target_temperature_high(self):
        return self._comfT

    @property
    def target_temperature_low(self):
        return self._saveT

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 0.2

    @property
    def should_poll(self):
        """Polling needed for thermostat."""
        _LOGGER.debug("Should_Poll called")
        return True

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    def update(self):
        """Update the data from the thermostat."""
        _LOGGER.debug("Update called")
        data = self._cl.roomByName(self._room_name)
        _LOGGER.debug(data)
        if data and data.get("error") == 0:
            try:
                # from Sunday (0) to Saturday (6)
                today = datetime.today().isoweekday() % 7
                # 48 slot per day
                index = datetime.today().hour * 2 + (
                    1 if datetime.today().minute > 30 else 0
                )
                programWeek = data["programWeek"]
                # delete programWeek to have less noise on debug output
                del data["programWeek"]

                self._tempSetMark = programWeek[today][index]
            except Exception as ex:
                _LOGGER.warning(ex)
                self._tempSetMark = "2"

            try:
                self._battery = bool(data.get("bat", "0"))
            except ValueError:
                self._battery = "0"

            try:
                self._frostT = float(data.get("frostT"))
            except ValueError:
                self._frostT = 5.0
            try:
                self._saveT = float(data.get("saveT"))
            except ValueError:
                self._saveT = 16.0

            try:
                self._comfT = float(data.get("comfT"))
            except ValueError:
                self._comfT = 20.0
            try:
                self._current_temp = float(data.get("tempNow"))
            except ValueError:
                self._current_temp = 20.0

            self._heating_state = data.get("heating", "") == "1"
            try:
                self._current_state = int(data.get("mode"))
            except ValueError:
                self._current_temp = 0
            self._current_unit = data.get("tempUnit")
            self._season = data.get("season")

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def device_state_attributes(self):
        """Return the device specific state attributes."""
        return {
            ATTR_MODE: self._current_state,
            "battery_state": self._battery,
            "frost_t": self._frostT,
            "confort_t": self._comfT,
            "save_t": self._saveT,
            "season_mode": self.hvac_mode,
            "heating_state": self._heating_state,
        }

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        if self._current_unit == "0":
            return TEMP_CELSIUS
        else:
            return TEMP_FAHRENHEIT

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temp

    @property
    def hvac_mode(self):
        """Current mode."""
        return self.HVAC_MODE_BESMART_TO_HA.get(self._season)

    @property
    def hvac_action(self):
        """Current mode."""
        if self._heating_state:
            mode = self.hvac_mode
            if mode == HVAC_MODE_HEAT:
                return CURRENT_HVAC_HEAT
            else:
                return CURRENT_HVAC_COOL
        else:
            return CURRENT_HVAC_OFF

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self.HVAC_MODE_LIST

    def set_hvac_mode(self, hvac_mode):
        """Set HVAC mode (COOL, HEAT)."""
        mode = self.HVAC_MODE_HA_BESMART.get(hvac_mode)
        self._cl.setSettings(self._room_name, mode)
        _LOGGER.debug("Set hvac_mode hvac_mode=%s(%s)", str(hvac_mode), str(mode))

    @property
    def preset_mode(self):
        """List of supported preset (comfort, home, sleep, Party, Off)."""

        return self.PRESET_BESMART_TO_HA.get(self._current_state, "IDLE")

    @property
    def preset_modes(self):
        """List of supported preset (comfort, home, sleep, Party, Off)."""

        return self.PRESET_MODE_LIST

    def set_preset_mode(self, preset_mode):
        """Set HVAC mode (comfort, home, sleep, Party, Off)."""

        mode = self.PRESET_HA_TO_BESMART.get(preset_mode, self.AUTO)
        self._cl.setRoomMode(self._room_name, mode)
        _LOGGER.debug("Set operation mode=%s(%s)", str(preset_mode), str(mode))

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        target_temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        target_temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)

        _LOGGER.debug(
            "temperature Frost: {} Eco: {} Conf: {}".format(
                temperature, target_temp_low, target_temp_high
            )
        )
        if temperature:
            self._cl.setRoomConfortTemp(self._room_name, temperature)
            # self._cl.setRoomFrostTemp(self._room_name, temperature)
        if target_temp_high:
            self._cl.setRoomConfortTemp(self._room_name, target_temp_high)
        if target_temp_low:
            self._cl.setRoomECOTemp(self._room_name, target_temp_low)
