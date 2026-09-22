"""The calibration values must survive the port unchanged.

These assert the exact numbers from the Arduino build's EyeConfig.h. If one of
these fails after a config edit, the mechanism's safe travel has changed and the
servos need recalibrating -- not the test updating.
"""

from __future__ import annotations

import pytest

ARDUINO_GAZE = {
    "horizontal": dict(channel=0, min_ticks=220, center_ticks=345, max_ticks=470, inverted=True),
    "vertical": dict(channel=1, min_ticks=260, center_ticks=342, max_ticks=440, inverted=False),
}

ARDUINO_LIDS = {
    "left_upper": dict(channel=2, open_ticks=300, closed_ticks=410, inverted=False),
    "left_lower": dict(channel=3, open_ticks=280, closed_ticks=400, inverted=True),
    "right_upper": dict(channel=4, open_ticks=255, closed_ticks=380, inverted=True),
    "right_lower": dict(channel=5, open_ticks=280, closed_ticks=395, inverted=False),
}


@pytest.mark.parametrize("name,expected", ARDUINO_GAZE.items())
def test_gaze_axis_matches_arduino(config, name, expected):
    axis = getattr(config.gaze, name)
    for field, value in expected.items():
        assert getattr(axis, field) == value, f"gaze.{name}.{field}"


@pytest.mark.parametrize("name,expected", ARDUINO_LIDS.items())
def test_eyelid_matches_arduino(config, name, expected):
    lid = getattr(config.eyelids, name)
    for field, value in expected.items():
        assert getattr(lid, field) == value, f"eyelids.{name}.{field}"


def test_safety_limits_match_arduino(config):
    assert config.safety.absolute_min_ticks == 100
    assert config.safety.absolute_max_ticks == 650
    assert config.safety.max_delta_per_update == 50
    assert config.safety.update_interval_ms == 20


def test_pwm_frequency_is_60hz(config):
    """Calibrated ticks are only meaningful at the frequency they were taken at."""
    assert config.board.pwm_frequency_hz == 60


def test_bonnet_address_not_arduino_shield_address(config):
    """The Bonnet #3416 ships unbridged at 0x40; the Arduino shield used 0x44."""
    assert config.board.i2c_address == 0x40


# --- Axis mapping ------------------------------------------------------------


def test_axis_extremes_and_center(config):
    h = config.gaze.horizontal
    # Horizontal is inverted, so +1.0 maps to the min end.
    assert h.ticks_for(0.0) == h.center_ticks
    assert h.ticks_for(1.0) == h.min_ticks
    assert h.ticks_for(-1.0) == h.max_ticks

    v = config.gaze.vertical
    assert v.ticks_for(0.0) == v.center_ticks
    assert v.ticks_for(1.0) == v.max_ticks
    assert v.ticks_for(-1.0) == v.min_ticks


def test_axis_clamps_beyond_unit_range(config):
    v = config.gaze.vertical
    assert v.ticks_for(5.0) == v.max_ticks
    assert v.ticks_for(-5.0) == v.min_ticks


def test_asymmetric_axis_maps_each_half_independently(config):
    """Center is not the midpoint of min/max, and both extremes must still hit."""
    v = config.gaze.vertical
    assert v.center_ticks - v.min_ticks != v.max_ticks - v.center_ticks
    assert v.ticks_for(1.0) == v.max_ticks
    assert v.ticks_for(-1.0) == v.min_ticks
    assert v.ticks_for(0.0) == v.center_ticks


@pytest.mark.parametrize("name", ARDUINO_LIDS)
def test_eyelid_closure_endpoints(config, name):
    lid = getattr(config.eyelids, name)
    if lid.inverted:
        assert lid.ticks_for(0.0) == lid.closed_ticks
        assert lid.ticks_for(1.0) == lid.open_ticks
    else:
        assert lid.ticks_for(0.0) == lid.open_ticks
        assert lid.ticks_for(1.0) == lid.closed_ticks


@pytest.mark.parametrize("name", ARDUINO_LIDS)
def test_eyelid_half_is_between_endpoints(config, name):
    lid = getattr(config.eyelids, name)
    lo, hi = sorted((lid.open_ticks, lid.closed_ticks))
    assert lo < lid.half_ticks < hi


@pytest.mark.parametrize("name", ARDUINO_LIDS)
def test_eyelid_closure_is_monotonic(config, name):
    lid = getattr(config.eyelids, name)
    values = [lid.ticks_for(i / 10) for i in range(11)]
    assert values == sorted(values) or values == sorted(values, reverse=True)


def test_all_channels_within_absolute_safety_range(config):
    lo, hi = config.safety.absolute_min_ticks, config.safety.absolute_max_ticks
    for axis in (config.gaze.horizontal, config.gaze.vertical):
        assert lo <= axis.min_ticks <= axis.max_ticks <= hi
    for lid in config.eyelids.all():
        assert lo <= min(lid.open_ticks, lid.closed_ticks)
        assert max(lid.open_ticks, lid.closed_ticks) <= hi


def test_channels_are_unique(config):
    channels = [config.gaze.horizontal.channel, config.gaze.vertical.channel]
    channels += [lid.channel for lid in config.eyelids.all()]
    assert sorted(channels) == [0, 1, 2, 3, 4, 5]


# --- Nunchuck normalization --------------------------------------------------


def test_nunchuck_center_is_deadzoned(config):
    nc = config.nunchuck
    assert nc.normalize_x(nc.center) == 0.0
    assert nc.normalize_x(nc.center + nc.deadzone) == 0.0
    assert nc.normalize_x(nc.center - nc.deadzone) == 0.0


def test_nunchuck_extremes_reach_unit_range(config):
    nc = config.nunchuck
    assert nc.normalize_x(nc.joy_x_max) == pytest.approx(1.0)
    assert nc.normalize_x(nc.joy_x_min) == pytest.approx(-1.0)
    assert nc.normalize_y(nc.joy_y_max) == pytest.approx(1.0)
    assert nc.normalize_y(nc.joy_y_min) == pytest.approx(-1.0)


def test_nunchuck_clamps_out_of_range_readings(config):
    nc = config.nunchuck
    assert nc.normalize_x(255) == pytest.approx(1.0)
    assert nc.normalize_x(0) == pytest.approx(-1.0)


def test_nunchuck_just_outside_deadzone_is_nonzero(config):
    nc = config.nunchuck
    assert nc.normalize_x(nc.center + nc.deadzone + 1) > 0.0
    assert nc.normalize_x(nc.center - nc.deadzone - 1) < 0.0
