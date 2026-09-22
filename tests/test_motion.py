"""Smoothing behaviour and its equivalence to the Arduino tuning."""

from __future__ import annotations

import math

import pytest

from animatronic_eyes.module.motion import Smoother, tau_from_arduino_smoothing


def test_converges_toward_target():
    s = Smoother(tau_s=0.15)
    for _ in range(200):
        s.update(1.0, 0.02)
    assert s.position == pytest.approx(1.0, abs=1e-3)


def test_one_tau_closes_63_percent():
    s = Smoother(tau_s=0.15)
    s.update(1.0, 0.15)
    assert s.position == pytest.approx(1.0 - math.exp(-1.0), abs=1e-9)


def test_never_overshoots():
    s = Smoother(tau_s=0.15)
    for _ in range(500):
        s.update(1.0, 0.02)
        assert s.position <= 1.0


def test_frame_rate_independence():
    """Same elapsed time, different step sizes, same result."""
    coarse = Smoother(tau_s=0.15)
    fine = Smoother(tau_s=0.15)
    coarse.update(1.0, 0.10)
    for _ in range(10):
        fine.update(1.0, 0.01)
    assert coarse.position == pytest.approx(fine.position, abs=1e-9)


def test_zero_and_negative_dt_are_noops():
    s = Smoother(tau_s=0.15, position=0.25)
    assert s.update(1.0, 0.0) == 0.25
    assert s.update(1.0, -0.5) == 0.25


def test_snap_bypasses_filter():
    s = Smoother(tau_s=0.15)
    assert s.snap(0.8) == 0.8
    assert s.position == 0.8


def test_tracks_a_moving_target():
    s = Smoother(tau_s=0.05)
    for i in range(100):
        s.update(i * 0.01, 0.02)
    assert s.position == pytest.approx(0.99, abs=0.05)


def test_rejects_non_positive_tau():
    with pytest.raises(ValueError, match="tau_s must be positive"):
        Smoother(tau_s=0.0)
    with pytest.raises(ValueError, match="tau_s must be positive"):
        Smoother(tau_s=-1.0)


# --- Equivalence with the Arduino tuning -------------------------------------


@pytest.mark.parametrize("smoothing,expected", [(8, 0.150), (5, 0.090)])
def test_configured_taus_match_arduino_smoothing(smoothing, expected):
    assert tau_from_arduino_smoothing(smoothing) == pytest.approx(expected, abs=0.001)


def test_config_uses_the_derived_taus(config):
    assert config.motion.gaze_tau_s == pytest.approx(
        tau_from_arduino_smoothing(8), abs=0.001
    )
    assert config.motion.eyelid_tau_s == pytest.approx(
        tau_from_arduino_smoothing(5), abs=0.001
    )


def test_matches_arduino_step_at_its_loop_rate():
    """One 20 ms step should close the same fraction the Arduino's `delta / 8` did."""
    s = Smoother(tau_s=tau_from_arduino_smoothing(8))
    s.update(1.0, 0.020)
    assert s.position == pytest.approx(1.0 / 8, abs=1e-9)


def test_arduino_conversion_rejects_degenerate_smoothing():
    with pytest.raises(ValueError, match="greater than 1"):
        tau_from_arduino_smoothing(1)
