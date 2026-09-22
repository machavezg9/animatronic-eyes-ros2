"""Autonomous idle behaviour.

Randomized gaze shifts plus auto-blink on independent timers, so the character
keeps a sense of life when nobody is driving it. Gaze wander is bounded to
`movement_range` of each axis, keeping idle motion away from the mechanical
extremes.
"""

from __future__ import annotations

import logging
import random
from enum import Enum, auto

from ..config.schema import IdleConfig
from ..module.eyes import EyeController, GazeTarget

log = logging.getLogger(__name__)


class Sequence(Enum):
    LOOK_LEFT = auto()
    LOOK_RIGHT = auto()
    LOOK_UP = auto()
    LOOK_DOWN = auto()
    LOOK_DIAGONAL = auto()


class IdleBehavior:
    """Picks a new gaze target every few seconds and blinks on its own timer."""

    def __init__(
        self,
        config: IdleConfig,
        eyes: EyeController,
        rng: random.Random | None = None,
    ) -> None:
        self._cfg = config
        self._eyes = eyes
        self._rng = rng or random.Random()
        self._time_to_next_sequence = 0.0
        self._time_to_next_blink = 0.0
        self._sequence: Sequence | None = None

    @property
    def sequence(self) -> Sequence | None:
        return self._sequence

    def enter(self) -> None:
        """Called on each transition into idle."""
        log.info("Entering idle mode")
        self._time_to_next_sequence = 0.5  # first shift shortly after settling
        self._time_to_next_blink = self._next_blink_delay()
        self._sequence = None
        self._eyes.center()

    def exit(self) -> None:
        log.info("Exiting idle mode")

    def update(self, dt: float) -> None:
        self._time_to_next_blink -= dt
        if self._time_to_next_blink <= 0.0:
            self._eyes.blink()
            self._time_to_next_blink = self._next_blink_delay()

        self._time_to_next_sequence -= dt
        if self._time_to_next_sequence <= 0.0:
            self._start_sequence()
            self._time_to_next_sequence = self._next_sequence_delay()

    # --- Target selection ---------------------------------------------------

    def _start_sequence(self) -> None:
        self._sequence = self._rng.choice(list(Sequence))
        span = self._cfg.movement_range

        if self._sequence is Sequence.LOOK_LEFT:
            target = GazeTarget(self._rng.uniform(-span, 0.0), 0.0)
        elif self._sequence is Sequence.LOOK_RIGHT:
            target = GazeTarget(self._rng.uniform(0.0, span), 0.0)
        elif self._sequence is Sequence.LOOK_UP:
            target = GazeTarget(0.0, self._rng.uniform(0.0, span))
        elif self._sequence is Sequence.LOOK_DOWN:
            target = GazeTarget(0.0, self._rng.uniform(-span, 0.0))
        else:
            target = GazeTarget(
                self._rng.uniform(-span, span), self._rng.uniform(-span, span)
            )

        self._eyes.look_at(target)
        log.debug(
            "Idle sequence %s -> (%.2f, %.2f)", self._sequence.name, target.x, target.y
        )

    # --- Timers -------------------------------------------------------------

    def _next_blink_delay(self) -> float:
        return self._rng.uniform(
            self._cfg.blink_interval_min_ms, self._cfg.blink_interval_max_ms
        ) / 1000.0

    def _next_sequence_delay(self) -> float:
        return self._rng.uniform(
            self._cfg.sequence_min_ms, self._cfg.sequence_max_ms
        ) / 1000.0
