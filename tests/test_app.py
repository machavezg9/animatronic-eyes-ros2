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
