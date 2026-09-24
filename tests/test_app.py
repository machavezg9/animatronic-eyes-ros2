"""Application loop wiring, shutdown guarantees, and the input abstraction."""

from __future__ import annotations

import pytest

from animatronic_eyes.app import Application
from animatronic_eyes.behaviors.state_machine import State
from animatronic_eyes.inputs.mock import NullInput, ScriptedInput
from animatronic_eyes.inputs.source import NEUTRAL, GazeCommand, InputSource
from animatronic_eyes.module.eyes import LID_OPEN


def test_null_input_never_reports_activity():
    assert NullInput().poll().active is False


def test_scripted_input_replays_then_repeats():
    source = ScriptedInput([GazeCommand(x=0.1), GazeCommand(x=0.2)])
    assert source.poll().x == 0.1
    assert source.poll().x == 0.2
    assert source.poll().x == 0.2
    assert source.exhausted


def test_empty_scripted_input_yields_neutral():
    assert ScriptedInput([]).poll() == NEUTRAL


def test_app_runs_for_the_requested_duration(config, backend):
    app = Application(config, backend, NullInput())
    app.run(duration=0.2)
    assert backend.writes


def test_app_drives_all_six_channels(config, backend):
    app = Application(config, backend, NullInput())
    app.run(duration=0.2)
    assert set(backend.positions) == {0, 1, 2, 3, 4, 5}


def test_shutdown_releases_the_backend(config, backend):
    Application(config, backend, NullInput()).run(duration=0.1)
    assert backend.deinit_count == 1


def test_shutdown_leaves_eyes_centered_and_open(config, backend):
    Application(config, backend, NullInput()).run(duration=0.1)
    assert backend.positions[config.gaze.horizontal.channel] == (
        config.gaze.horizontal.center_ticks
    )
    assert backend.positions[config.gaze.vertical.channel] == (
        config.gaze.vertical.center_ticks
    )
    for lid in config.eyelids.all():
        assert backend.positions[lid.channel] == lid.ticks_for(LID_OPEN)


def test_shutdown_stops_the_input_source(config, backend):
    class Tracking(NullInput):
        started = False
        stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    source = Tracking()
    Application(config, backend, source).run(duration=0.1)
    assert source.started and source.stopped


def test_backend_is_released_even_if_input_start_fails(config, backend):
    class Failing(InputSource):
        def start(self):
            raise RuntimeError("no hardware")

        def poll(self):
            return NEUTRAL

    with pytest.raises(RuntimeError, match="no hardware"):
        Application(config, backend, Failing()).run(duration=0.1)
    assert backend.deinit_count == 1


def test_backend_is_released_even_if_input_stop_fails(config, backend):
    class BadStop(NullInput):
        def stop(self):
            raise RuntimeError("stuck")

    Application(config, backend, BadStop()).run(duration=0.1)
    assert backend.deinit_count == 1


def test_app_never_writes_outside_the_safety_envelope(config, backend):
    Application(config, backend, NullInput()).run(duration=1.0)
    lo = config.safety.absolute_min_ticks
    hi = config.safety.absolute_max_ticks
    assert all(lo <= w.ticks <= hi for w in backend.writes)


def test_app_respects_per_channel_calibrated_bounds(config, backend):
    Application(config, backend, NullInput()).run(duration=1.0)
    bounds = {
        config.gaze.horizontal.channel: (
            config.gaze.horizontal.min_ticks, config.gaze.horizontal.max_ticks
        ),
        config.gaze.vertical.channel: (
            config.gaze.vertical.min_ticks, config.gaze.vertical.max_ticks
        ),
    }
    for lid in config.eyelids.all():
        bounds[lid.channel] = (
            min(lid.open_ticks, lid.closed_ticks),
            max(lid.open_ticks, lid.closed_ticks),
        )
    for write in backend.writes:
        lo, hi = bounds[write.channel]
        assert lo <= write.ticks <= hi


def test_app_reaches_active_state(config, backend):
    app = Application(config, backend, NullInput())
    app.run(duration=7.0)
    assert app.state_machine.state in (State.ACTIVE, State.IDLE)


def test_stop_ends_the_loop(config, backend):
    class StopsItself(NullInput):
        def __init__(self, app_ref):
            self.app_ref = app_ref
            self.calls = 0

        def poll(self):
            self.calls += 1
            if self.calls > 5:
                self.app_ref[0].stop()
            return NEUTRAL

    ref: list = [None]
    source = StopsItself(ref)
    app = Application(config, backend, source)
    ref[0] = app
    app.run(duration=60.0)
    assert source.calls < 20


# --- Homing ------------------------------------------------------------------


def test_home_drives_every_channel_once(config, eyes, backend):
    eyes.home()
    assert sorted(w.channel for w in backend.writes) == [0, 1, 2, 3, 4, 5]


def test_home_brings_channels_up_one_at_a_time(config, eyes, backend):
    """A bind should be attributable to a single channel, not a chorus of six."""
    order = []
    eyes.home(on_channel=lambda name, ch, ticks: order.append((ch, len(backend.writes))))
    # Each callback fires after exactly one more write than the last.
    assert [n for _, n in order] == [1, 2, 3, 4, 5, 6]


def test_home_centers_gaze(config, eyes, backend):
    """Centre is the point furthest from either mechanical stop."""
    eyes.home()
    assert backend.positions[config.gaze.horizontal.channel] == (
        config.gaze.horizontal.center_ticks
    )
    assert backend.positions[config.gaze.vertical.channel] == (
        config.gaze.vertical.center_ticks
    )


def test_home_defaults_lids_closed(config, eyes, backend):
    from animatronic_eyes.module.eyes import LID_CLOSED

    eyes.home()
    for lid in config.eyelids.all():
        assert backend.positions[lid.channel] == lid.ticks_for(LID_CLOSED)


def test_home_respects_requested_closure(config, eyes, backend):
    from animatronic_eyes.module.eyes import LID_OPEN

    eyes.home(LID_OPEN)
    for lid in config.eyelids.all():
        assert backend.positions[lid.channel] == lid.ticks_for(LID_OPEN)


def test_home_cancels_any_blink(config, eyes):
    eyes.blink()
    eyes.home()
    assert not eyes.is_blinking


def test_app_homes_lids_closed_not_open(config, backend):
    """The startup sequence begins closed; homing open would reverse instantly."""
    from animatronic_eyes.module.eyes import LID_CLOSED

    app = Application(config, backend, NullInput())
    app.run(duration=0.05)
    lid = config.eyelids.left_upper
    first = next(w for w in backend.writes if w.channel == lid.channel)
    assert first.ticks == lid.ticks_for(LID_CLOSED)


def test_app_homing_is_staggered(config, backend, monkeypatch):
    import animatronic_eyes.app as app_module

    slept: list[float] = []
    monkeypatch.setattr(app_module.time, "sleep", lambda s: slept.append(s))
    Application(config, backend, NullInput()).run(duration=0.05)

    stagger = config.startup.home_stagger_s
    assert slept.count(stagger) == 6, "expected one stagger pause per channel"


def test_zero_stagger_disables_pauses(config, backend, monkeypatch):
    from dataclasses import replace

    import animatronic_eyes.app as app_module

    cfg = replace(config, startup=replace(config.startup, home_stagger_ms=0))
    slept: list[float] = []
    monkeypatch.setattr(app_module.time, "sleep", lambda s: slept.append(s))
    Application(cfg, backend, NullInput()).run(duration=0.05)
    assert 0.0 not in slept


def test_cli_lid_waypoints_respect_inversion(config):
    """selftest/home must label by lid state, not by raw field name.

    On an inverted channel the open_ticks/closed_ticks fields are the servo's
    travel endpoints with open and closed swapped. Reading them directly makes
    the tool announce "closed" while driving the lid open -- which matters
    because the hardware procedure depends on knowing when the lid is closing.
    """
    for name in ("left_upper", "left_lower", "right_upper", "right_lower"):
        lid = getattr(config.eyelids, name)
        from animatronic_eyes.module.eyes import LID_CLOSED, LID_OPEN

        if lid.inverted:
            assert lid.ticks_for(LID_OPEN) == lid.closed_ticks, name
            assert lid.ticks_for(LID_CLOSED) == lid.open_ticks, name
        else:
            assert lid.ticks_for(LID_OPEN) == lid.open_ticks, name
            assert lid.ticks_for(LID_CLOSED) == lid.closed_ticks, name
