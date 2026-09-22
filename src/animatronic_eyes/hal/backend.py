"""PWM backend interface.

One interface, several platforms -- the pattern Marlin uses for its HAL, where
NATIVE_SIM and LINUX are supported platforms rather than test doubles. Same idea
here: MockBackend is a first-class backend, which is what makes the whole system
developable and testable on a machine with no PCA9685 attached.

The unit throughout is the PCA9685's raw 12-bit tick (0..4095), matching what the
Arduino build passed to pwm.setPWM(channel, 0, ticks). Keeping this unit all the
way down to the register write is what lets the existing calibration transfer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

TICK_MIN = 0
TICK_MAX = 4095


class PWMBackend(ABC):
    """Drives PWM channels in raw 12-bit ticks."""

    @abstractmethod
    def set_ticks(self, channel: int, ticks: int) -> None:
        """Set `channel`'s pulse width to `ticks` (0..4095)."""

    @abstractmethod
    def deinit(self) -> None:
        """Stop output and release the hardware. Must be idempotent."""

    def __enter__(self) -> PWMBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.deinit()
