"""Whole-configuration validation.

Individual fields are typed by the schema; this module checks the things that
are only wrong in combination -- a lid whose open and closed values overlap, a
calibrated bound outside the absolute safety range, two servos assigned the same
channel. Modelled on Marlin's SanityCheck.h: fail early, and say exactly what to
fix.
"""

from __future__ import annotations

from .schema import EyesConfig


class ConfigError(ValueError):
    """Raised when a configuration is internally inconsistent or unsafe."""


def _check_within_absolute(
    problems: list[str], cfg: EyesConfig, name: str, *values: tuple[str, int]
) -> None:
    lo = cfg.safety.absolute_min_ticks
    hi = cfg.safety.absolute_max_ticks
    for label, value in values:
        if not lo <= value <= hi:
            problems.append(
                f"{name}.{label} is {value}, outside the absolute safety range "
                f"{lo}..{hi}. Either recalibrate this servo or widen "
                f"safety.absolute_min_ticks / absolute_max_ticks (only if you have "
                f"verified the mechanism does not bind there)."
            )


def validate(cfg: EyesConfig) -> None:
    """Raise ConfigError describing every problem found, or return cleanly."""
    problems: list[str] = []

    # --- Safety envelope must itself be sane -------------------------------
    if cfg.safety.absolute_min_ticks >= cfg.safety.absolute_max_ticks:
        problems.append(
            f"safety.absolute_min_ticks ({cfg.safety.absolute_min_ticks}) must be "
            f"less than absolute_max_ticks ({cfg.safety.absolute_max_ticks})."
        )
    if cfg.safety.max_delta_per_update <= 0:
        problems.append("safety.max_delta_per_update must be greater than 0.")
    if cfg.safety.update_interval_ms <= 0:
        problems.append("safety.update_interval_ms must be greater than 0.")

    if cfg.board.pwm_frequency_hz not in range(24, 1527):
        problems.append(
            f"board.pwm_frequency_hz is {cfg.board.pwm_frequency_hz}; the PCA9685 "
            f"supports 24..1526 Hz. Analog servos expect 50-60 Hz, and the ported "
            f"calibration assumes 60."
        )

    # --- Gaze axes ---------------------------------------------------------
    for name, axis in (("gaze.horizontal", cfg.gaze.horizontal), ("gaze.vertical", cfg.gaze.vertical)):
        if axis.min_ticks >= axis.max_ticks:
            problems.append(
                f"{name}.min_ticks ({axis.min_ticks}) must be less than max_ticks "
                f"({axis.max_ticks})."
            )
        if not axis.min_ticks <= axis.center_ticks <= axis.max_ticks:
            problems.append(
                f"{name}.center_ticks ({axis.center_ticks}) must lie between "
                f"min_ticks ({axis.min_ticks}) and max_ticks ({axis.max_ticks})."
            )
        _check_within_absolute(
            problems,
            cfg,
            name,
            ("min_ticks", axis.min_ticks),
            ("center_ticks", axis.center_ticks),
            ("max_ticks", axis.max_ticks),
        )

    # --- Eyelids -----------------------------------------------------------
    lid_names = ("eyelids.left_upper", "eyelids.left_lower", "eyelids.right_upper", "eyelids.right_lower")
    for name, lid in zip(lid_names, cfg.eyelids.all()):
        if lid.open_ticks == lid.closed_ticks:
            problems.append(
                f"{name}.open_ticks and closed_ticks are both {lid.open_ticks}; the "
                f"lid would never move. Recalibrate this channel."
            )
        _check_within_absolute(
            problems,
            cfg,
            name,
            ("open_ticks", lid.open_ticks),
            ("closed_ticks", lid.closed_ticks),
        )

    # --- Channel assignment ------------------------------------------------
    assignments: dict[int, list[str]] = {}
    for name, channel in (
        ("gaze.horizontal", cfg.gaze.horizontal.channel),
        ("gaze.vertical", cfg.gaze.vertical.channel),
        *zip(lid_names, (lid.channel for lid in cfg.eyelids.all())),
    ):
        assignments.setdefault(channel, []).append(name)

    for channel, owners in sorted(assignments.items()):
        if not 0 <= channel <= 15:
            problems.append(
                f"{owners[0]}.channel is {channel}; the PCA9685 has channels 0-15."
            )
        if len(owners) > 1:
            problems.append(
                f"Channel {channel} is assigned to multiple servos: "
                f"{', '.join(owners)}. Each servo needs its own channel."
            )

    # --- Motion ------------------------------------------------------------
    if cfg.motion.gaze_tau_s <= 0 or cfg.motion.eyelid_tau_s <= 0:
        problems.append(
            "motion.gaze_tau_s and motion.eyelid_tau_s must be greater than 0. "
            "Smaller values respond faster; 0.15 and 0.09 reproduce the Arduino feel."
        )

    # --- Input -------------------------------------------------------------
    nc = cfg.nunchuck
    for label, lo, hi in (("x", nc.joy_x_min, nc.joy_x_max), ("y", nc.joy_y_min, nc.joy_y_max)):
        if lo >= hi:
            problems.append(
                f"nunchuck.joy_{label}_min ({lo}) must be less than joy_{label}_max ({hi})."
            )
        elif not lo < nc.center < hi:
            problems.append(
                f"nunchuck.center ({nc.center}) must lie strictly between "
                f"joy_{label}_min ({lo}) and joy_{label}_max ({hi})."
            )
    if nc.deadzone < 0:
        problems.append("nunchuck.deadzone cannot be negative.")
    else:
        half_span = min(nc.center - nc.joy_x_min, nc.joy_x_max - nc.center)
        if nc.deadzone >= half_span:
            problems.append(
                f"nunchuck.deadzone ({nc.deadzone}) swallows the entire joystick "
                f"range (half-span is {half_span}); the eyes would never move."
            )

    # --- Behaviors ---------------------------------------------------------
    if cfg.blink.duration_ms <= 0:
        problems.append("blink.duration_ms must be greater than 0.")

    idle = cfg.idle
    if idle.blink_interval_min_ms > idle.blink_interval_max_ms:
        problems.append(
            f"idle.blink_interval_min_ms ({idle.blink_interval_min_ms}) must not "
            f"exceed blink_interval_max_ms ({idle.blink_interval_max_ms})."
        )
    if idle.sequence_min_ms > idle.sequence_max_ms:
        problems.append(
            f"idle.sequence_min_ms ({idle.sequence_min_ms}) must not exceed "
            f"sequence_max_ms ({idle.sequence_max_ms})."
        )
    if not 0.0 < idle.movement_range <= 1.0:
        problems.append(
            f"idle.movement_range is {idle.movement_range}; it is a fraction of each "
            f"axis's range and must be greater than 0 and at most 1.0."
        )
    if idle.blink_interval_min_ms < cfg.blink.duration_ms:
        problems.append(
            f"idle.blink_interval_min_ms ({idle.blink_interval_min_ms}) is shorter "
            f"than blink.duration_ms ({cfg.blink.duration_ms}); blinks would overlap."
        )

    for label, value in (
        ("home_stagger_ms", cfg.startup.home_stagger_ms),
        ("eyes_closed_hold_ms", cfg.startup.eyes_closed_hold_ms),
        ("eyes_close_duration_ms", cfg.startup.eyes_close_duration_ms),
        ("eyes_open_duration_ms", cfg.startup.eyes_open_duration_ms),
        ("look_around_duration_ms", cfg.startup.look_around_duration_ms),
        ("return_to_center_ms", cfg.startup.return_to_center_ms),
    ):
        if value < 0:
            problems.append(f"startup.{label} cannot be negative.")

    if problems:
        raise ConfigError(
            "Configuration is not safe to run:\n\n"
            + "\n\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
        )
