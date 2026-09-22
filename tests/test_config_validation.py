"""Sanity checking rejects unsafe configurations with actionable messages."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
import yaml

from animatronic_eyes.config.loader import DEFAULT_CONFIG_PATH, load
from animatronic_eyes.config.sanity import ConfigError, validate


def test_shipped_config_is_valid(config):
    validate(config)


def test_axis_min_above_max_is_rejected(config):
    broken = replace(config, gaze=replace(
        config.gaze, horizontal=replace(config.gaze.horizontal, min_ticks=500, max_ticks=300)
    ))
    with pytest.raises(ConfigError, match="must be less than max_ticks"):
        validate(broken)


def test_center_outside_travel_is_rejected(config):
    broken = replace(config, gaze=replace(
        config.gaze, vertical=replace(config.gaze.vertical, center_ticks=999)
    ))
    with pytest.raises(ConfigError, match="must lie between"):
        validate(broken)


def test_bound_outside_absolute_range_is_rejected(config):
    broken = replace(config, gaze=replace(
        config.gaze, horizontal=replace(config.gaze.horizontal, max_ticks=4000)
    ))
    with pytest.raises(ConfigError, match="outside the absolute safety range"):
        validate(broken)


def test_lid_with_identical_endpoints_is_rejected(config):
    broken = replace(config, eyelids=replace(
        config.eyelids,
        left_upper=replace(config.eyelids.left_upper, open_ticks=300, closed_ticks=300),
    ))
    with pytest.raises(ConfigError, match="the lid would never move"):
        validate(broken)


def test_duplicate_channel_is_rejected(config):
    broken = replace(config, eyelids=replace(
        config.eyelids, left_upper=replace(config.eyelids.left_upper, channel=0)
    ))
    with pytest.raises(ConfigError, match="assigned to multiple servos"):
        validate(broken)


def test_channel_outside_pca9685_range_is_rejected(config):
    broken = replace(config, eyelids=replace(
        config.eyelids, right_lower=replace(config.eyelids.right_lower, channel=42)
    ))
    with pytest.raises(ConfigError, match="channels 0-15"):
        validate(broken)


def test_deadzone_swallowing_the_range_is_rejected(config):
    broken = replace(config, nunchuck=replace(config.nunchuck, deadzone=200))
    with pytest.raises(ConfigError, match="swallows the entire joystick range"):
        validate(broken)


def test_inverted_idle_blink_interval_is_rejected(config):
    broken = replace(config, idle=replace(
        config.idle, blink_interval_min_ms=9000, blink_interval_max_ms=2000
    ))
    with pytest.raises(ConfigError, match="must not exceed blink_interval_max_ms"):
        validate(broken)


def test_blinks_shorter_than_their_interval_are_rejected(config):
    broken = replace(config, blink=replace(config.blink, duration_ms=5000))
    with pytest.raises(ConfigError, match="blinks would overlap"):
        validate(broken)


def test_movement_range_outside_unit_interval_is_rejected(config):
    for bad in (0.0, 1.5, -0.2):
        broken = replace(config, idle=replace(config.idle, movement_range=bad))
        with pytest.raises(ConfigError, match="must be greater than 0 and at most 1.0"):
            validate(broken)


def test_non_servo_pwm_frequency_is_rejected(config):
    broken = replace(config, board=replace(config.board, pwm_frequency_hz=5))
    with pytest.raises(ConfigError, match="supports 24..1526 Hz"):
        validate(broken)


def test_all_problems_reported_at_once(config):
    broken = replace(
        config,
        blink=replace(config.blink, duration_ms=0),
        idle=replace(config.idle, movement_range=5.0),
    )
    with pytest.raises(ConfigError) as exc:
        validate(broken)
    assert "1." in str(exc.value)
    assert "2." in str(exc.value)


# --- Loading -----------------------------------------------------------------


def _write(tmp_path, data):
    path = tmp_path / "eyes.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.fixture
def raw():
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="Configuration file not found"):
        load(tmp_path / "nope.yaml")


def test_missing_section_is_reported(tmp_path, raw):
    del raw["motion"]
    with pytest.raises(ConfigError, match="missing the 'motion' section"):
        load(_write(tmp_path, raw))


def test_missing_key_is_reported_by_name(tmp_path, raw):
    del raw["gaze"]["horizontal"]["center_ticks"]
    with pytest.raises(ConfigError, match="missing required key\\(s\\): center_ticks"):
        load(_write(tmp_path, raw))


def test_unknown_key_is_reported_by_name(tmp_path, raw):
    raw["blink"]["durration_ms"] = 150
    with pytest.raises(ConfigError, match="unrecognised key\\(s\\): durration_ms"):
        load(_write(tmp_path, raw))


def test_malformed_yaml_is_reported(tmp_path):
    path = tmp_path / "eyes.yaml"
    path.write_text("board: {i2c_address: 0x40\n  bad indent")
    with pytest.raises(ConfigError, match="Could not parse"):
        load(path)


def test_roundtrip_of_shipped_config(tmp_path, raw):
    assert load(_write(tmp_path, copy.deepcopy(raw))) == load(DEFAULT_CONFIG_PATH)
