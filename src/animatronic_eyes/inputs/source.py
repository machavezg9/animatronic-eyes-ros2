"""Input source interface.

Everything upstream of the motion stack speaks GazeCommand: gaze in normalized
axis units, plus discrete requests. Calibration specific to a device (the
nunchuck's 26..226 joystick range, say) stays inside that device's driver, so
swapping input has no effect on anything below.

This is the seam the vision system plugs into. A ROS 2 node subscribing to the
Jetson's person-position topic becomes another InputSource implementation, and
the controller, behaviours, and servo layer are untouched by its arrival.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GazeCommand:
    """One frame of input."""

    x: float = 0.0
    y: float = 0.0
    blink: bool = False
    center: bool = False
    active: bool = False
    """True when this frame carries real input; drives the idle timeout."""


NEUTRAL = GazeCommand()


class InputSource(ABC):
    """Produces a GazeCommand per frame."""

    @abstractmethod
    def poll(self) -> GazeCommand:
        """Read the current input state. Must not block."""

    def start(self) -> None:
        """Optional setup hook."""

    def stop(self) -> None:
        """Optional teardown hook. Must be idempotent."""

    @property
    def name(self) -> str:
        return type(self).__name__
