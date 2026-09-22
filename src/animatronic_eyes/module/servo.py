"""Per-channel servo output with safety enforcement.

Every tick written to the hardware passes through here, in a fixed order:

    calibrated clamp -> absolute clamp -> slew limit -> write

The calibrated clamp keeps the servo inside its mechanically-verified travel.
The absolute clamp is a second, configuration-independent net. The slew limit
caps how far a channel may move in one update, so a bad target cannot translate
into a full-speed slam against a hard stop.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.schema import SafetyConfig
from ..hal.backend import PWMBackend


@dataclass
class Servo:
    """One PCA9685 channel, bounded and rate-limited."""

    channel: int
    min_ticks: int
    max_ticks: int
    safety: SafetyConfig
    backend: PWMBackend
    name: str = ""

    _last_ticks: int | None = None

    def __post_init__(self) -> None:
        if self.min_ticks > self.max_ticks:
            self.min_ticks, self.max_ticks = self.max_ticks, self.min_ticks

    @property
    def position(self) -> int | None:
        """Last value written, or None if this channel has never been driven."""
        return self._last_ticks

    def write(self, ticks: int) -> int:
        """Clamp, rate-limit, and write. Returns the value actually sent."""
        target = self._clamp(ticks)

        if self._last_ticks is not None:
            delta = target - self._last_ticks
            limit = self.safety.max_delta_per_update
            if delta > limit:
                target = self._last_ticks + limit
            elif delta < -limit:
                target = self._last_ticks - limit

        self.backend.set_ticks(self.channel, target)
        self._last_ticks = target
        return target

    def snap_to(self, ticks: int) -> int:
        """Write without the slew limit.

        Only for deliberate discontinuities -- initial positioning at startup
        and the recentre on shutdown -- where the rate limit would otherwise
        stretch a single intended jump across many update cycles.
        """
        target = self._clamp(ticks)
        self.backend.set_ticks(self.channel, target)
        self._last_ticks = target
        return target

    def _clamp(self, ticks: int) -> int:
        ticks = max(self.min_ticks, min(self.max_ticks, int(round(ticks))))
        return max(
            self.safety.absolute_min_ticks,
            min(self.safety.absolute_max_ticks, ticks),
        )
