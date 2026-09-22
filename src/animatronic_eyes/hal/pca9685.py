"""PCA9685 backend (Adafruit PWM/Servo Bonnet #3416, or the Arduino shield).

Writes raw 12-bit ticks. The Adafruit CircuitPython driver exposes a 16-bit
duty_cycle, so ticks are shifted left by 4: duty_cycle = ticks << 4 is exactly
equivalent to the Arduino's pwm.setPWM(channel, 0, ticks).

Deliberately not used: adafruit_motor.servo, or any angle/microsecond API. Those
re-derive pulse widths from their own assumptions and would discard the
per-servo calibration this project depends on.

Hardware dependencies are imported lazily so the rest of the package remains
importable on machines without Blinka installed.
"""

from __future__ import annotations

import logging

from .backend import TICK_MAX, TICK_MIN, PWMBackend

log = logging.getLogger(__name__)

TICKS_TO_DUTY_SHIFT = 4
_DUTY_FULL = 0xFFFF


class PCA9685Backend(PWMBackend):
    """Real hardware backend over I2C."""

    def __init__(self, i2c_address: int = 0x40, pwm_frequency_hz: int = 60) -> None:
        try:
            import board  # type: ignore[import-not-found]
            import busio  # type: ignore[import-not-found]
            from adafruit_pca9685 import PCA9685  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "PCA9685 backend needs the hardware extras. Install them with:\n"
                "    pip install 'animatronic-eyes[hardware]'\n"
                "On a Raspberry Pi, also enable I2C (raspi-config, or "
                "dtparam=i2c_arm=on) and confirm the board appears in "
                "`i2cdetect -y 1`."
            ) from exc

        self._i2c = busio.I2C(board.SCL, board.SDA)
        try:
            self._pca = PCA9685(self._i2c, address=i2c_address)
        except ValueError as exc:
            raise RuntimeError(
                f"No PCA9685 responded at I2C address 0x{i2c_address:02X}. "
                f"Run `i2cdetect -y 1` to see what is actually on the bus -- the "
                f"Bonnet #3416 ships unbridged at 0x40, while the Arduino shield "
                f"in this project had A2 bridged for 0x44."
            ) from exc

        self._pca.frequency = pwm_frequency_hz
        self._closed = False
        log.info(
            "PCA9685 ready at 0x%02X, %d Hz", i2c_address, pwm_frequency_hz
        )

    def set_ticks(self, channel: int, ticks: int) -> None:
        if not TICK_MIN <= ticks <= TICK_MAX:
            raise ValueError(
                f"ticks={ticks} out of PCA9685 range {TICK_MIN}..{TICK_MAX} "
                f"on channel {channel}"
            )
        self._pca.channels[channel].duty_cycle = min(
            ticks << TICKS_TO_DUTY_SHIFT, _DUTY_FULL
        )

    def deinit(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            for channel in self._pca.channels:
                channel.duty_cycle = 0
            self._pca.deinit()
        finally:
            self._i2c.deinit()
        log.info("PCA9685 released")
