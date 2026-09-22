"""YAML -> typed config, with validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .sanity import ConfigError, validate
from .schema import (
    AxisConfig,
    BlinkConfig,
    BoardConfig,
    EyelidConfig,
    EyelidsConfig,
    EyesConfig,
    GazeConfig,
    IdleConfig,
    MotionConfig,
    NunchuckConfig,
    SafetyConfig,
    StartupConfig,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "eyes.yaml"


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        value = data[name]
    except KeyError:
        raise ConfigError(f"Configuration is missing the '{name}' section.") from None
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration section '{name}' must be a mapping.")
    return value


def _build(cls: type, data: dict[str, Any], where: str) -> Any:
    """Construct a frozen dataclass, reporting missing/unknown keys by name."""
    fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    missing = fields - data.keys()
    unknown = data.keys() - fields
    if missing:
        raise ConfigError(f"{where} is missing required key(s): {', '.join(sorted(missing))}.")
    if unknown:
        raise ConfigError(
            f"{where} has unrecognised key(s): {', '.join(sorted(unknown))}. "
            f"Expected only: {', '.join(sorted(fields))}."
        )
    return cls(**data)


def load(path: Path | str | None = None) -> EyesConfig:
    """Load, type, and validate the configuration.

    Raises ConfigError with an actionable message on any problem.
    """
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a top-level mapping.")

    eyelids_raw = _section(raw, "eyelids")
    cfg = EyesConfig(
        board=_build(BoardConfig, _section(raw, "board"), "board"),
        safety=_build(SafetyConfig, _section(raw, "safety"), "safety"),
        gaze=GazeConfig(
            horizontal=_build(
                AxisConfig, _section(_section(raw, "gaze"), "horizontal"), "gaze.horizontal"
            ),
            vertical=_build(
                AxisConfig, _section(_section(raw, "gaze"), "vertical"), "gaze.vertical"
            ),
        ),
        eyelids=EyelidsConfig(
            left_upper=_build(EyelidConfig, _section(eyelids_raw, "left_upper"), "eyelids.left_upper"),
            left_lower=_build(EyelidConfig, _section(eyelids_raw, "left_lower"), "eyelids.left_lower"),
            right_upper=_build(EyelidConfig, _section(eyelids_raw, "right_upper"), "eyelids.right_upper"),
            right_lower=_build(EyelidConfig, _section(eyelids_raw, "right_lower"), "eyelids.right_lower"),
        ),
        motion=_build(MotionConfig, _section(raw, "motion"), "motion"),
        nunchuck=_build(NunchuckConfig, _section(raw, "nunchuck"), "nunchuck"),
        blink=_build(BlinkConfig, _section(raw, "blink"), "blink"),
        startup=_build(StartupConfig, _section(raw, "startup"), "startup"),
        idle=_build(IdleConfig, _section(raw, "idle"), "idle"),
    )

    validate(cfg)
    return cfg
