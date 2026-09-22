"""In-memory PWM backend.

A supported platform, not a test fixture. It is how the system runs on any
machine without a PCA9685 -- including development boards where the I2C bus
isn't even enabled -- and it records every write so behaviour can be asserted
on without servos attached.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .backend import TICK_MAX, TICK_MIN, PWMBackend

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Write:
    channel: int
    ticks: int


@dataclass
class MockBackend(PWMBackend):
    """Records channel writes; optionally logs each one."""

    verbose: bool = False
    writes: list[Write] = field(default_factory=list)
    positions: dict[int, int] = field(default_factory=dict)
    deinit_count: int = 0

    def set_ticks(self, channel: int, ticks: int) -> None:
        if not TICK_MIN <= ticks <= TICK_MAX:
            raise ValueError(
                f"ticks={ticks} out of PCA9685 range {TICK_MIN}..{TICK_MAX} "
                f"on channel {channel}"
            )
        self.writes.append(Write(channel, ticks))
        self.positions[channel] = ticks
        if self.verbose:
            log.debug("ch%-2d -> %4d", channel, ticks)

    def deinit(self) -> None:
        self.deinit_count += 1
        if self.verbose:
            log.debug("deinit (all channels released)")

    # --- Inspection helpers -------------------------------------------------

    def writes_for(self, channel: int) -> list[int]:
        return [w.ticks for w in self.writes if w.channel == channel]

    def clear(self) -> None:
        self.writes.clear()
