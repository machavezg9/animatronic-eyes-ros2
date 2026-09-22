"""Eye mechanism controller: gaze, eyelids, blink.

Gaze targets are normalized (-1.0 .. 1.0 per axis) and eyelid closure is
0.0 (open) .. 1.0 (closed). Translation into calibrated ticks happens here, at
the last moment before the servo layer, so behaviours never deal in raw pulse
values and the whole stack above this point is hardware-independent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config.schema import EyesConfig
from ..hal.backend import PWMBackend
from .motion import Smoother
from .servo import Servo

log = logging.getLogger(__name__)

LID_OPEN = 0.0
LID_CLOSED = 1.0


@dataclass(frozen=True)
class GazeTarget:
    """Where the eyes should look, in normalized axis units."""

    x: float = 0.0
    y: float = 0.0


class EyeController:
    """Owns the six servos and the motion state between target and output."""

    def __init__(self, config: EyesConfig, backend: PWMBackend) -> None:
        self._cfg = config
        self._backend = backend

        gaze = config.gaze
        self._servo_h = Servo(
            channel=gaze.horizontal.channel,
            min_ticks=gaze.horizontal.min_ticks,
            max_ticks=gaze.horizontal.max_ticks,
            safety=config.safety,
            backend=backend,
            name="horizontal",
        )
        self._servo_v = Servo(
            channel=gaze.vertical.channel,
            min_ticks=gaze.vertical.min_ticks,
            max_ticks=gaze.vertical.max_ticks,
            safety=config.safety,
            backend=backend,
            name="vertical",
        )

        lid_names = ("left_upper", "left_lower", "right_upper", "right_lower")
        self._lid_servos = [
            Servo(
                channel=lid.channel,
                min_ticks=min(lid.open_ticks, lid.closed_ticks),
                max_ticks=max(lid.open_ticks, lid.closed_ticks),
                safety=config.safety,
                backend=backend,
                name=name,
            )
            for name, lid in zip(lid_names, config.eyelids.all())
        ]

        self._gaze_x = Smoother(config.motion.gaze_tau_s)
        self._gaze_y = Smoother(config.motion.gaze_tau_s)
        self._lid = Smoother(config.motion.eyelid_tau_s)

        self._target = GazeTarget()
        self._lid_target = LID_OPEN

        # Blink is a timed override on top of whatever the lids are doing.
        self._blinking = False
        self._blink_elapsed = 0.0

    # --- Commands -----------------------------------------------------------

    @property
    def target(self) -> GazeTarget:
        return self._target

    def look_at(self, target: GazeTarget) -> None:
        self._target = target

    def set_eyelids(self, closure: float) -> None:
        """Set lid target: 0.0 open, 0.5 half, 1.0 closed."""
        self._lid_target = max(LID_OPEN, min(LID_CLOSED, closure))

    def center(self) -> None:
        """Recentre the gaze target. Motion still eases there."""
        self._target = GazeTarget(0.0, 0.0)

    def blink(self) -> None:
        """Start a blink, if one is not already running."""
        if not self._blinking:
            self._blinking = True
            self._blink_elapsed = 0.0

    @property
    def is_blinking(self) -> bool:
        return self._blinking

    # --- Per-frame update ---------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance motion by `dt` seconds and drive the servos."""
        x = self._gaze_x.update(self._target.x, dt)
        y = self._gaze_y.update(self._target.y, dt)
        self._servo_h.write(self._cfg.gaze.horizontal.ticks_for(x))
        self._servo_v.write(self._cfg.gaze.vertical.ticks_for(y))

        closure = self._update_blink(dt)
        self._write_lids(closure)

    def _update_blink(self, dt: float) -> float:
        """Return this frame's lid closure, blink override included.

        The blink is a snap close, hold, snap open -- matching the Arduino
        build, whose closeEyes()/openEyes() wrote the endpoint values directly
        rather than interpolating.
        """
        if not self._blinking:
            return self._lid.update(self._lid_target, dt)

        self._blink_elapsed += dt
        if self._blink_elapsed >= self._cfg.blink.duration_s:
            self._blinking = False
            self._lid.snap(self._lid_target)
            return self._lid_target

        self._lid.snap(LID_CLOSED)
        return LID_CLOSED

    def _write_lids(self, closure: float) -> None:
        for servo, lid in zip(self._lid_servos, self._cfg.eyelids.all()):
            servo.write(lid.ticks_for(closure))

    # --- Discontinuous positioning -----------------------------------------

    def snap_to(self, target: GazeTarget, closure: float) -> None:
        """Place the mechanism immediately, bypassing smoothing and slew limits.

        For initial positioning and shutdown only.
        """
        self._target = target
        self._lid_target = closure
        self._blinking = False
        self._gaze_x.snap(target.x)
        self._gaze_y.snap(target.y)
        self._lid.snap(closure)

        self._servo_h.snap_to(self._cfg.gaze.horizontal.ticks_for(target.x))
        self._servo_v.snap_to(self._cfg.gaze.vertical.ticks_for(target.y))
        for servo, lid in zip(self._lid_servos, self._cfg.eyelids.all()):
            servo.snap_to(lid.ticks_for(closure))

    def rest(self) -> None:
        """Centre the gaze and open the lids. Safe state for shutdown."""
        self.snap_to(GazeTarget(0.0, 0.0), LID_OPEN)
        log.info("Eyes returned to rest position")
