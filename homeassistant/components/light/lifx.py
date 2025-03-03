
"""
homeassistant.components.light.lifx
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LIFX platform that implements lights

Configuration:

light:
  # platform name
  platform: lifx
  # optional server address
  # only needed if using more than one network interface
  # (omit if you are unsure)
  server: 192.168.1.3
  # optional broadcast address, set to reach all LIFX bulbs
  # (omit if you are unsure)
  broadcast: 192.168.1.255

"""
# pylint: disable=missing-docstring

import logging
import colorsys
from homeassistant.helpers.event import track_time_change
from homeassistant.components.light import \
    (Light, ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_COLOR_TEMP, ATTR_TRANSITION)

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['liffylights==0.9.0']
DEPENDENCIES = []

CONF_SERVER = "server"        # server address configuration item
CONF_BROADCAST = "broadcast"  # broadcast address configuration item
SHORT_MAX = 65535             # short int maximum
BYTE_MAX = 255                # byte maximum
TEMP_MIN = 2500               # lifx minimum temperature
TEMP_MAX = 9000               # lifx maximum temperature
TEMP_MIN_HASS = 154           # home assistant minimum temperature
TEMP_MAX_HASS = 500           # home assistant maximum temperature


class LIFX():
    def __init__(self, add_devices_callback,
                 server_addr=None, broadcast_addr=None):
        import liffylights

        self._devices = []

        self._add_devices_callback = add_devices_callback

        self._liffylights = liffylights.LiffyLights(
            self.on_device,
            self.on_power,
            self.on_color,
            server_addr,
            broadcast_addr)

    def find_bulb(self, ipaddr):
        bulb = None
        for device in self._devices:
            if device.ipaddr == ipaddr:
                bulb = device
                break
        return bulb

    # pylint: disable=too-many-arguments
    def on_device(self, ipaddr, name, power, hue, sat, bri, kel):
        bulb = self.find_bulb(ipaddr)

        if bulb is None:
            bulb = LIFXLight(self._liffylights, ipaddr, name,
                             power, hue, sat, bri, kel)
            self._devices.append(bulb)
            self._add_devices_callback([bulb])

    # pylint: disable=too-many-arguments
    def on_color(self, ipaddr, hue, sat, bri, kel):
        bulb = self.find_bulb(ipaddr)

        if bulb is not None:
            bulb.set_color(hue, sat, bri, kel)
            bulb.update_ha_state()

    def on_power(self, ipaddr, power):
        bulb = self.find_bulb(ipaddr)

        if bulb is not None:
            bulb.set_power(power)
            bulb.update_ha_state()

    # pylint: disable=unused-argument
    def poll(self, now):
        self.probe()

    def probe(self, address=None):
        self._liffylights.probe(address)


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    """ Set up platform. """
    server_addr = config.get(CONF_SERVER, None)
    broadcast_addr = config.get(CONF_BROADCAST, None)

    lifx_library = LIFX(add_devices_callback, server_addr, broadcast_addr)

    # register our poll service
    track_time_change(hass, lifx_library.poll, second=10)

    lifx_library.probe()


def convert_rgb_to_hsv(rgb):
    """ Convert HASS RGB values to HSV values. """
    red, green, blue = [_ / BYTE_MAX for _ in rgb]

    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)

    return [int(hue * SHORT_MAX),
            int(saturation * SHORT_MAX),
            int(brightness * SHORT_MAX)]


# pylint: disable=too-many-instance-attributes
class LIFXLight(Light):
    """ Provides LIFX light. """
    # pylint: disable=too-many-arguments
    def __init__(self, liffy, ipaddr, name, power, hue,
                 saturation, brightness, kelvin):
        _LOGGER.debug("LIFXLight: %s %s",
                      ipaddr, name)

        self._liffylights = liffy
        self._ip = ipaddr
        self.set_name(name)
        self.set_power(power)
        self.set_color(hue, saturation, brightness, kelvin)

    @property
    def should_poll(self):
        """ No polling needed for LIFX light. """
        return False

    @property
    def name(self):
        """ Returns the name of the device. """
        return self._name

    @property
    def ipaddr(self):
        """ Returns the ip of the device. """
        return self._ip

    @property
    def rgb_color(self):
        """ Returns RGB value. """
        _LOGGER.debug("rgb_color: [%d %d %d]",
                      self._rgb[0], self._rgb[1], self._rgb[2])

        return self._rgb

    @property
    def brightness(self):
        """ Returns brightness of this light between 0..255. """
        brightness = int(self._bri / (BYTE_MAX + 1))

        _LOGGER.debug("brightness: %d",
                      brightness)

        return brightness

    @property
    def color_temp(self):
        """ Returns color temperature. """
        temperature = int(TEMP_MIN_HASS + (TEMP_MAX_HASS - TEMP_MIN_HASS) *
                          (self._kel - TEMP_MIN) / (TEMP_MAX - TEMP_MIN))

        _LOGGER.debug("color_temp: %d",
                      temperature)

        return temperature

    @property
    def is_on(self):
        """ True if device is on. """
        _LOGGER.debug("is_on: %d",
                      self._power)

        return self._power != 0

    def turn_on(self, **kwargs):
        """ Turn the device on. """
        if ATTR_TRANSITION in kwargs:
            fade = kwargs[ATTR_TRANSITION] * 1000
        else:
            fade = 0

        if ATTR_RGB_COLOR in kwargs:
            hue, saturation, brightness = \
                convert_rgb_to_hsv(kwargs[ATTR_RGB_COLOR])
        else:
            hue = self._hue
            saturation = self._sat
            brightness = self._bri

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS] * (BYTE_MAX + 1)
        else:
            brightness = self._bri

        if ATTR_COLOR_TEMP in kwargs:
            kelvin = int(((TEMP_MAX - TEMP_MIN) *
                          (kwargs[ATTR_COLOR_TEMP] - TEMP_MIN_HASS) /
                          (TEMP_MAX_HASS - TEMP_MIN_HASS)) + TEMP_MIN)
        else:
            kelvin = self._kel

        _LOGGER.debug("turn_on: %s (%d) %d %d %d %d %d",
                      self._ip, self._power,
                      hue, saturation, brightness, kelvin, fade)

        if self._power == 0:
            self._liffylights.set_power(self._ip, 65535, fade)

        self._liffylights.set_color(self._ip, hue, saturation,
                                    brightness, kelvin, fade)

    def turn_off(self, **kwargs):
        """ Turn the device off. """
        if ATTR_TRANSITION in kwargs:
            fade = kwargs[ATTR_TRANSITION] * 1000
        else:
            fade = 0

        _LOGGER.debug("turn_off: %s %d",
                      self._ip, fade)

        self._liffylights.set_power(self._ip, 0, fade)

    def set_name(self, name):
        """ Set name. """
        self._name = name

    def set_power(self, power):
        """ Set power state value. """
        _LOGGER.debug("set_power: %d",
                      power)

        self._power = (power != 0)

    def set_color(self, hue, sat, bri, kel):
        """ Set color state values. """
        self._hue = hue
        self._sat = sat
        self._bri = bri
        self._kel = kel

        red, green, blue = colorsys.hsv_to_rgb(hue / SHORT_MAX,
                                               sat / SHORT_MAX,
                                               bri / SHORT_MAX)

        red = int(red * BYTE_MAX)
        green = int(green * BYTE_MAX)
        blue = int(blue * BYTE_MAX)

        _LOGGER.debug("set_color: %d %d %d %d [%d %d %d]",
                      hue, sat, bri, kel, red, green, blue)

        self._rgb = [red, green, blue]
