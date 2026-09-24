"""Typed configuration schema.

Every position in this module is a raw PCA9685 12-bit tick value, matching the
units the Arduino build calibrated in. Nothing here converts to angles or
microseconds -- that conversion is what would invalidate the calibration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoardConfig:
    i2c_address: int
    pwm_frequency_hz: int


@dataclass(frozen=True)
class SafetyConfig:
    absolute_min_ticks: int
    absolute_max_ticks: int
    max_delta_per_update: int
    update_interval_ms: int

    @property
    def update_interval_s(self) -> float:
        return self.update_interval_ms / 1000.0


@dataclass(frozen=True)
class AxisConfig:
    """A gaze axis: travels between min and max, rests at center."""

    channel: int
    min_ticks: int
    center_ticks: int
    max_ticks: int
    inverted: bool

    def ticks_for(self, normalized: float) -> int:
        """Map -1.0..1.0 to calibrated ticks, honouring inversion.

        The axis is mapped in two halves around center, so an asymmetric
        mechanism (center not at the midpoint of min/max) still returns exactly
        center_ticks at 0.0 and hits both extremes at -1.0 and 1.0.
        """
        value = -normalized if self.inverted else normalized
        value = max(-1.0, min(1.0, value))
        if value >= 0.0:
            span = self.max_ticks - self.center_ticks
        else:
            span = self.center_ticks - self.min_ticks
        return round(self.center_ticks + value * span)


@dataclass(frozen=True)
class EyelidConfig:
    """A single eyelid: travels between fully open and fully closed."""

    channel: int
    open_ticks: int
    closed_ticks: int
    inverted: bool

    def ticks_for(self, closure: float) -> int:
        """Map 0.0 (open) .. 1.0 (closed) to calibrated ticks."""
        value = max(0.0, min(1.0, closure))
        if self.inverted:
            value = 1.0 - value
        return round(self.open_ticks + (self.closed_ticks - self.open_ticks) * value)

    @property
    def half_ticks(self) -> int:
        return self.ticks_for(0.5)


@dataclass(frozen=True)
class GazeConfig:
    horizontal: AxisConfig
    vertical: AxisConfig


@dataclass(frozen=True)
class EyelidsConfig:
    left_upper: EyelidConfig
    left_lower: EyelidConfig
    right_upper: EyelidConfig
    right_lower: EyelidConfig

    def all(self) -> tuple[EyelidConfig, ...]:
        return (self.left_upper, self.left_lower, self.right_upper, self.right_lower)


@dataclass(frozen=True)
class MotionConfig:
    gaze_tau_s: float
    eyelid_tau_s: float


@dataclass(frozen=True)
class NunchuckConfig:
    i2c_address: int
    joy_x_min: int
    joy_x_max: int
    joy_y_min: int
    joy_y_max: int
    center: int
    deadzone: int

    def normalize(self, raw: int, lo: int, hi: int) -> float:
        """Map a raw joystick reading to -1.0..1.0, with deadzone around center."""
        if abs(raw - self.center) <= self.deadzone:
            return 0.0
        if raw > self.center:
            span = hi - self.center
            return min(1.0, (raw - self.center) / span) if span > 0 else 0.0
        span = self.center - lo
        return max(-1.0, (raw - self.center) / span) if span > 0 else 0.0

    def normalize_x(self, raw: int) -> float:
        return self.normalize(raw, self.joy_x_min, self.joy_x_max)

    def normalize_y(self, raw: int) -> float:
        return self.normalize(raw, self.joy_y_min, self.joy_y_max)


@dataclass(frozen=True)
class BlinkConfig:
    duration_ms: int

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0


@dataclass(frozen=True)
class StartupConfig:
    home_stagger_ms: int
    eyes_closed_hold_ms: int
    eyes_close_duration_ms: int
    eyes_open_duration_ms: int
    look_around_duration_ms: int
    return_to_center_ms: int

    @property
    def home_stagger_s(self) -> float:
        return self.home_stagger_ms / 1000.0


@dataclass(frozen=True)
class IdleConfig:
    timeout_ms: int
    blink_interval_min_ms: int
    blink_interval_max_ms: int
    sequence_min_ms: int
    sequence_max_ms: int
    movement_range: float

    @property
    def timeout_s(self) -> float:
        return self.timeout_ms / 1000.0


@dataclass(frozen=True)
class EyesConfig:
    board: BoardConfig
    safety: SafetyConfig
    gaze: GazeConfig
    eyelids: EyelidsConfig
    motion: MotionConfig
    nunchuck: NunchuckConfig
    blink: BlinkConfig
    startup: StartupConfig
    idle: IdleConfig
