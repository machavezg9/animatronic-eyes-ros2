"""Startup choreography.

Close -> hold -> open -> look around (L, R, U, D) -> centre. Roughly 5.8 s with
the shipped timings.

All phase durations come from configuration. The Arduino version hardcoded the
look-around segment boundaries at 500/1000/1500/2000 ms and ramped the lids by a
magic 0.02 per iteration, which left its EYES_OPEN_DURATION setting unused; here
the four segments are derived from look_around_duration_ms and the lid ramps
from the close/open durations.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

from ..config.schema import StartupConfig
from ..module.eyes import LID_CLOSED, LID_OPEN, EyeController, GazeTarget

log = logging.getLogger(__name__)

_LOOK_AROUND_TARGETS = (
    GazeTarget(-1.0, 0.0),  # left
    GazeTarget(1.0, 0.0),   # right
    GazeTarget(0.0, 1.0),   # up
    GazeTarget(0.0, -1.0),  # down
)


class Phase(Enum):
    CLOSE_EYES = auto()
    HOLD_CLOSED = auto()
    OPEN_EYES = auto()
    LOOK_AROUND = auto()
    CENTER = auto()
    COMPLETE = auto()


class StartupSequence:
    """Runs once at boot, then reports complete."""

    def __init__(self, config: StartupConfig, eyes: EyeController) -> None:
        self._cfg = config
        self._eyes = eyes
        self._phase = Phase.CLOSE_EYES
        self._elapsed = 0.0
        self._entered = False

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def complete(self) -> bool:
        return self._phase is Phase.COMPLETE

    def update(self, dt: float) -> None:
        if self._phase is Phase.COMPLETE:
            return

        if not self._entered:
            self._on_enter()
            self._entered = True

        self._elapsed += dt
        handler = getattr(self, f"_run_{self._phase.name.lower()}")
        handler()

    # --- Phases -------------------------------------------------------------

    def _run_close_eyes(self) -> None:
        duration = self._ms(self._cfg.eyes_close_duration_ms)
        self._eyes.set_eyelids(LID_CLOSED)
        if self._elapsed >= duration:
            self._advance(Phase.HOLD_CLOSED)

    def _run_hold_closed(self) -> None:
        if self._elapsed >= self._ms(self._cfg.eyes_closed_hold_ms):
            self._advance(Phase.OPEN_EYES)

    def _run_open_eyes(self) -> None:
        self._eyes.set_eyelids(LID_OPEN)
        if self._elapsed >= self._ms(self._cfg.eyes_open_duration_ms):
            self._advance(Phase.LOOK_AROUND)

    def _run_look_around(self) -> None:
        total = self._ms(self._cfg.look_around_duration_ms)
        if total <= 0:
            self._advance(Phase.CENTER)
            return

        segment = total / len(_LOOK_AROUND_TARGETS)
        index = min(int(self._elapsed / segment), len(_LOOK_AROUND_TARGETS) - 1)
        self._eyes.look_at(_LOOK_AROUND_TARGETS[index])

        if self._elapsed >= total:
            self._advance(Phase.CENTER)

    def _run_center(self) -> None:
        self._eyes.center()
        if self._elapsed >= self._ms(self._cfg.return_to_center_ms):
            self._advance(Phase.COMPLETE)

    # --- Transitions --------------------------------------------------------

    def _advance(self, phase: Phase) -> None:
        self._phase = phase
        self._elapsed = 0.0
        self._entered = False
        if phase is Phase.COMPLETE:
            log.info("Startup sequence complete")

    def _on_enter(self) -> None:
        messages = {
            Phase.CLOSE_EYES: "Closing eyes...",
            Phase.HOLD_CLOSED: "Eyes closed",
            Phase.OPEN_EYES: "Opening eyes...",
            Phase.LOOK_AROUND: "Looking around...",
            Phase.CENTER: "Centering...",
        }
        if message := messages.get(self._phase):
            log.info(message)

    @staticmethod
    def _ms(value: int) -> float:
        return value / 1000.0
