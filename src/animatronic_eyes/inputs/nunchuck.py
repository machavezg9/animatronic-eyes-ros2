"""Wii Nunchuck over I2C.

Replaces the Arduino build's WiiChuck library. The nunchuck sits at 0x52,
clear of the PCA9685 at 0x40, so both share the bus.

Initialisation uses the unencrypted handshake (write 0xF0/0x55 then 0xFB/0x00)
rather than the older 0x40/0x00 form, so reports come back in the clear and need
no decoding.

Joystick calibration lives here and nowhere else: poll() emits normalized
-1.0..1.0 values, so nothing downstream knows this device's raw range.
"""

from __future__ import annotations

import logging
import time

from ..config.schema import NunchuckConfig
from .source import NEUTRAL, GazeCommand, InputSource

log = logging.getLogger(__name__)

_REPORT_LENGTH = 6
_BUTTON_Z_MASK = 0x01
_BUTTON_C_MASK = 0x02


class NunchuckError(RuntimeError):
    """The nunchuck could not be reached or returned unusable data."""


class NunchuckInput(InputSource):
    """Manual control input. Z blinks, C recentres."""

    def __init__(self, config: NunchuckConfig, bus_number: int = 1) -> None:
        self._cfg = config
        self._bus_number = bus_number
        self._bus = None
        self._last_z = False
        self._last_c = False

    def start(self) -> None:
        try:
            from smbus2 import SMBus  # type: ignore[import-not-found]
        except ImportError as exc:
            raise NunchuckError(
                "Nunchuck input needs smbus2. Install it with:\n"
                "    pip install smbus2"
            ) from exc

        try:
            self._bus = SMBus(self._bus_number)
            # Unencrypted handshake.
            self._bus.write_byte_data(self._cfg.i2c_address, 0xF0, 0x55)
            time.sleep(0.01)
            self._bus.write_byte_data(self._cfg.i2c_address, 0xFB, 0x00)
            time.sleep(0.01)
        except OSError as exc:
            self.stop()
            raise NunchuckError(
                f"No nunchuck responded at 0x{self._cfg.i2c_address:02X} on "
                f"/dev/i2c-{self._bus_number}. Check `i2cdetect -y "
                f"{self._bus_number}`. Note the Pi's I2C is 3.3 V with fixed "
                f"pull-ups; a nunchuck wired for a 5 V Arduino may need an "
                f"adapter. Run with --input null to work without it."
            ) from exc

        log.info("Nunchuck ready at 0x%02X", self._cfg.i2c_address)

    def poll(self) -> GazeCommand:
        if self._bus is None:
            return NEUTRAL

        try:
            self._bus.write_byte(self._cfg.i2c_address, 0x00)
            time.sleep(0.0001)
            data = self._bus.read_i2c_block_data(
                self._cfg.i2c_address, 0x00, _REPORT_LENGTH
            )
        except OSError:
            log.warning("Nunchuck read failed; treating this frame as neutral")
            return NEUTRAL

        if len(data) < _REPORT_LENGTH:
            return NEUTRAL

        joy_x, joy_y = data[0], data[1]
        # Buttons are active-low in the final byte.
        z_down = not (data[5] & _BUTTON_Z_MASK)
        c_down = not (data[5] & _BUTTON_C_MASK)

        x = self._cfg.normalize_x(joy_x)
        y = self._cfg.normalize_y(joy_y)

        # Edge-triggered, matching the Arduino's lastZ/lastC handling -- a held
        # button fires once, not every frame.
        z_pressed = z_down and not self._last_z
        c_pressed = c_down and not self._last_c
        self._last_z = z_down
        self._last_c = c_down

        return GazeCommand(
            x=x,
            y=y,
            blink=z_pressed,
            center=c_pressed,
            active=x != 0.0 or y != 0.0 or z_down or c_down,
        )

    def stop(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except OSError:
                pass
            self._bus = None
