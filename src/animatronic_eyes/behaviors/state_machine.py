"""System state machine: STARTUP -> ACTIVE <-> IDLE.

Activity detection runs before state handling, every frame. That ordering is
what makes leaving idle feel instant: the frame that first sees input is also
the frame that acts on it, rather than the input being noticed a frame late.
"""

from __future__ import annotations

import logging
import random
from enum import Enum, auto

from ..config.schema import EyesConfig
from ..inputs.source import GazeCommand
from ..module.eyes import EyeController, GazeTarget
from .idle import IdleBehavior
from .startup import StartupSequence

log = logging.getLogger(__name__)


class State(Enum):
    STARTUP = auto()
    ACTIVE = auto()
    IDLE = auto()


class StateMachine:
    """Routes input to the behaviour that owns the current state."""

    def __init__(
        self,
        config: EyesConfig,
        eyes: EyeController,
        rng: random.Random | None = None,
    ) -> None:
        self._cfg = config
        self._eyes = eyes
        self._state = State.STARTUP
        self._startup = StartupSequence(config.startup, eyes)
        self._idle = IdleBehavior(config.idle, eyes, rng)
        self._time_since_activity = 0.0

    @property
    def state(self) -> State:
        return self._state

    @property
    def time_since_activity(self) -> float:
        return self._time_since_activity

    def update(self, command: GazeCommand, dt: float) -> None:
        # Activity detection first -- see module docstring.
        if self._state is not State.STARTUP:
            self._track_activity(command, dt)

        if self._state is State.STARTUP:
            self._run_startup(dt)
        elif self._state is State.ACTIVE:
            self._run_active(command, dt)
        else:
            self._run_idle(dt)

        self._eyes.update(dt)

    # --- Activity -----------------------------------------------------------

    def _track_activity(self, command: GazeCommand, dt: float) -> None:
        if command.active:
            if self._state is State.IDLE:
                self._enter_active()
            self._time_since_activity = 0.0
        else:
            self._time_since_activity += dt

    # --- States -------------------------------------------------------------

    def _run_startup(self, dt: float) -> None:
        self._startup.update(dt)
        if self._startup.complete:
            self._enter_active()

    def _run_active(self, command: GazeCommand, dt: float) -> None:
        if command.center:
            self._eyes.center()
        elif command.active:
            self._eyes.look_at(GazeTarget(command.x, command.y))

        if command.blink:
            self._eyes.blink()

        if self._time_since_activity >= self._cfg.idle.timeout_s:
            self._enter_idle()

    def _run_idle(self, dt: float) -> None:
        self._idle.update(dt)

    # --- Transitions --------------------------------------------------------

    def _enter_active(self) -> None:
        if self._state is State.IDLE:
            self._idle.exit()
        self._state = State.ACTIVE
        self._time_since_activity = 0.0

    def _enter_idle(self) -> None:
        self._state = State.IDLE
        self._idle.enter()
