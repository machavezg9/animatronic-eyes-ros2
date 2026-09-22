"""Frame-rate independent smoothing.

Position follows target exponentially with a time constant, not a per-iteration
fraction:

    alpha = 1 - exp(-dt / tau)
    position += (target - position) * alpha

Expressing it against elapsed time rather than loop count means motion looks the
same whether the loop runs at 50 Hz or stutters -- which matters on a
general-purpose Linux board in a way it never did on bare-metal AVR.

Tau is the time to close ~63% of the remaining distance. The configured defaults
(0.150 s gaze, 0.090 s eyelid) reproduce the feel of the Arduino build's
smoothing factors of 8 and 5 at its 50 Hz loop rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Smoother:
    """Exponential position follower over a normalized or tick-valued signal."""

    tau_s: float
    position: float = 0.0

    def __post_init__(self) -> None:
        if self.tau_s <= 0:
            raise ValueError(f"tau_s must be positive, got {self.tau_s}")

    def update(self, target: float, dt: float) -> float:
        """Advance toward `target` over `dt` seconds. Returns the new position."""
        if dt <= 0:
            return self.position
        alpha = 1.0 - math.exp(-dt / self.tau_s)
        self.position += (target - self.position) * alpha
        return self.position

    def snap(self, value: float) -> float:
        """Jump straight to `value`, bypassing the filter."""
        self.position = value
        return self.position


def tau_from_arduino_smoothing(smoothing: int, loop_period_s: float = 0.020) -> float:
    """Time constant equivalent to the Arduino's `current += delta / smoothing`.

    That loop closed a 1/smoothing fraction of the gap per iteration, so the
    per-iteration retention is (smoothing - 1) / smoothing and

        tau = loop_period / ln(smoothing / (smoothing - 1))

    Kept as a documented conversion so recalibrating against the original
    firmware's tuning values stays a one-liner.
    """
    if smoothing <= 1:
        raise ValueError(f"smoothing must be greater than 1, got {smoothing}")
    return loop_period_s / math.log(smoothing / (smoothing - 1))
