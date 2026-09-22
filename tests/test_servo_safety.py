"""Safety enforcement in the servo layer."""

from __future__ import annotations

import pytest

from animatronic_eyes.config.schema import SafetyConfig
from animatronic_eyes.hal.mock import MockBackend
from animatronic_eyes.module.servo import Servo

SAFETY = SafetyConfig(
    absolute_min_ticks=100,
    absolute_max_ticks=650,
    max_delta_per_update=50,
    update_interval_ms=20,
)


@pytest.fixture
def servo(backend):
    return Servo(channel=0, min_ticks=200, max_ticks=400, safety=SAFETY, backend=backend)


def test_clamps_to_calibrated_bounds(servo):
    assert servo.snap_to(9999) == 400
    assert servo.snap_to(-9999) == 200


def test_absolute_limits_override_wider_calibration(backend):
    """A calibrated range wider than the absolute range is still clamped."""
    servo = Servo(channel=0, min_ticks=0, max_ticks=4095, safety=SAFETY, backend=backend)
    assert servo.snap_to(4095) == SAFETY.absolute_max_ticks
    assert servo.snap_to(0) == SAFETY.absolute_min_ticks


def test_slew_limit_caps_movement_per_update(servo):
    servo.snap_to(200)
    assert servo.write(400) == 250   # +50, not +200
    assert servo.write(400) == 300
    assert servo.write(400) == 350


def test_slew_limit_applies_in_both_directions(servo):
    servo.snap_to(400)
    assert servo.write(200) == 350
    assert servo.write(200) == 300


def test_slew_limited_motion_eventually_reaches_target(servo):
    servo.snap_to(200)
    for _ in range(20):
        servo.write(400)
    assert servo.position == 400


def test_snap_to_bypasses_slew_limit(servo):
    servo.snap_to(200)
    assert servo.snap_to(400) == 400


def test_first_write_is_not_slew_limited(servo):
    """With no previous position there is nothing to rate-limit against."""
    assert servo.write(400) == 400


def test_position_starts_unset(servo):
    assert servo.position is None


def test_inverted_bounds_are_normalized(backend):
    """min/max supplied the wrong way round should not disable clamping."""
    servo = Servo(channel=0, min_ticks=400, max_ticks=200, safety=SAFETY, backend=backend)
    assert servo.min_ticks == 200
    assert servo.max_ticks == 400
    assert servo.snap_to(9999) == 400


def test_every_write_reaches_the_backend(servo, backend):
    servo.snap_to(200)
    servo.write(250)
    servo.write(300)
    assert backend.writes_for(0) == [200, 250, 300]


def test_backend_rejects_out_of_range_ticks():
    backend = MockBackend()
    with pytest.raises(ValueError, match="out of PCA9685 range"):
        backend.set_ticks(0, 5000)
    with pytest.raises(ValueError, match="out of PCA9685 range"):
        backend.set_ticks(0, -1)


def test_deinit_is_idempotent():
    backend = MockBackend()
    backend.deinit()
    backend.deinit()
    assert backend.deinit_count == 2  # counted, but never raises


def test_backend_context_manager_deinits():
    with MockBackend() as backend:
        backend.set_ticks(0, 300)
    assert backend.deinit_count == 1
