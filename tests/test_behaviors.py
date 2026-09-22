"""State machine, startup choreography, idle behaviour, and blink timing."""

from __future__ import annotations

import pytest

from animatronic_eyes.behaviors.idle import IdleBehavior
from animatronic_eyes.behaviors.startup import Phase, StartupSequence
from animatronic_eyes.behaviors.state_machine import State, StateMachine
from animatronic_eyes.inputs.source import NEUTRAL, GazeCommand
from animatronic_eyes.module.eyes import LID_CLOSED, LID_OPEN

DT = 0.02  # the configured 50 Hz loop period


def advance(machine, seconds, command=NEUTRAL, dt=DT):
    for _ in range(int(seconds / dt)):
        machine.update(command, dt)


# --- Startup -----------------------------------------------------------------


def test_startup_runs_phases_in_order(config, eyes):
    startup = StartupSequence(config.startup, eyes)
    seen = []
    for _ in range(1000):
        if not seen or seen[-1] is not startup.phase:
            seen.append(startup.phase)
        startup.update(DT)
        if startup.complete:
            break
    assert seen == [
        Phase.CLOSE_EYES,
        Phase.HOLD_CLOSED,
        Phase.OPEN_EYES,
        Phase.LOOK_AROUND,
        Phase.CENTER,
    ]
    assert startup.complete


def test_startup_total_duration_matches_config(config, eyes):
    startup = StartupSequence(config.startup, eyes)
    expected = (
        config.startup.eyes_close_duration_ms
        + config.startup.eyes_closed_hold_ms
        + config.startup.eyes_open_duration_ms
        + config.startup.look_around_duration_ms
        + config.startup.return_to_center_ms
    ) / 1000.0

    elapsed = 0.0
    while not startup.complete and elapsed < 30.0:
        startup.update(DT)
        elapsed += DT
    assert elapsed == pytest.approx(expected, abs=5 * DT)


def test_startup_look_around_visits_all_four_directions(config, eyes):
    startup = StartupSequence(config.startup, eyes)
    targets = set()
    for _ in range(2000):
        was_looking = startup.phase is Phase.LOOK_AROUND
        startup.update(DT)
        # Read after the update: the frame that enters LOOK_AROUND is the frame
        # that first sets a direction.
        if was_looking or startup.phase is Phase.LOOK_AROUND:
            targets.add((eyes.target.x, eyes.target.y))
        if startup.complete:
            break
    assert {(-1.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, -1.0)} <= targets


def test_startup_ends_centered(config, eyes):
    startup = StartupSequence(config.startup, eyes)
    while not startup.complete:
        startup.update(DT)
    assert eyes.target.x == 0.0
    assert eyes.target.y == 0.0


def test_startup_is_idempotent_once_complete(config, eyes):
    startup = StartupSequence(config.startup, eyes)
    while not startup.complete:
        startup.update(DT)
    startup.update(DT)
    assert startup.phase is Phase.COMPLETE


# --- State machine -----------------------------------------------------------


def test_starts_in_startup(config, eyes):
    assert StateMachine(config, eyes).state is State.STARTUP


def test_transitions_to_active_after_startup(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    assert machine.state is State.ACTIVE


def test_drops_to_idle_after_timeout(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    assert machine.state is State.ACTIVE
    advance(machine, config.idle.timeout_s + 1.0)
    assert machine.state is State.IDLE


def test_activity_exits_idle_on_the_same_frame(config, eyes):
    """The frame that first sees input is the frame that leaves idle."""
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    advance(machine, config.idle.timeout_s + 1.0)
    assert machine.state is State.IDLE

    machine.update(GazeCommand(x=0.5, active=True), DT)
    assert machine.state is State.ACTIVE


def test_activity_resets_the_idle_timer(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    advance(machine, config.idle.timeout_s * 0.8)
    machine.update(GazeCommand(x=0.3, active=True), DT)
    assert machine.time_since_activity == 0.0
    advance(machine, config.idle.timeout_s * 0.8)
    assert machine.state is State.ACTIVE


def test_active_input_steers_gaze(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    machine.update(GazeCommand(x=0.75, y=-0.5, active=True), DT)
    assert eyes.target.x == 0.75
    assert eyes.target.y == -0.5


def test_center_command_recenters(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    machine.update(GazeCommand(x=0.9, y=0.9, active=True), DT)
    machine.update(GazeCommand(center=True, active=True), DT)
    assert eyes.target.x == 0.0
    assert eyes.target.y == 0.0


def test_blink_command_triggers_blink(config, eyes):
    machine = StateMachine(config, eyes)
    advance(machine, 8.0)
    machine.update(GazeCommand(blink=True, active=True), DT)
    assert eyes.is_blinking


def test_input_ignored_during_startup(config, eyes):
    machine = StateMachine(config, eyes)
    machine.update(GazeCommand(x=1.0, active=True), DT)
    assert machine.state is State.STARTUP


# --- Blink -------------------------------------------------------------------


def test_blink_lasts_the_configured_duration(config, eyes):
    eyes.blink()
    steps = 0
    while eyes.is_blinking and steps < 1000:
        eyes.update(DT)
        steps += 1
    assert steps * DT == pytest.approx(config.blink.duration_s, abs=2 * DT)


def test_blink_fully_closes_the_lids_within_its_duration(config, eyes, backend):
    """The lids reach fully closed, but the slew limit spreads it over frames.

    The controller commands a snap to closed; the servo layer's
    max_delta_per_update caps how fast that can actually be driven. The Arduino
    declared the same limit but never enforced it, so its blink was a true snap.
    Here a blink closes over a few frames -- well inside the blink duration, and
    gentler on the servo.
    """
    eyes.snap_to(eyes.target, LID_OPEN)
    backend.clear()
    eyes.blink()

    frames = 0
    while eyes.is_blinking and frames < 100:
        eyes.update(DT)
        frames += 1
        if all(
            backend.positions[lid.channel] == lid.ticks_for(LID_CLOSED)
            for lid in config.eyelids.all()
        ):
            break

    assert frames * DT < config.blink.duration_s, "lids did not close within the blink"
    for lid in config.eyelids.all():
        assert backend.positions[lid.channel] == lid.ticks_for(LID_CLOSED)


def test_blink_starts_closing_immediately(config, eyes, backend):
    eyes.snap_to(eyes.target, LID_OPEN)
    eyes.blink()
    eyes.update(DT)
    lid = config.eyelids.left_upper
    moved = abs(backend.positions[lid.channel] - lid.ticks_for(LID_OPEN))
    assert moved == config.safety.max_delta_per_update


def test_lids_reopen_after_blink(config, eyes, backend):
    eyes.snap_to(eyes.target, LID_OPEN)
    eyes.blink()
    for _ in range(100):
        eyes.update(DT)
    assert not eyes.is_blinking
    lid = config.eyelids.left_upper
    assert backend.positions[lid.channel] == pytest.approx(
        lid.ticks_for(LID_OPEN), abs=1
    )


def test_blink_does_not_restart_while_running(eyes):
    eyes.blink()
    eyes.update(DT)
    eyes.blink()
    steps = 0
    while eyes.is_blinking and steps < 1000:
        eyes.update(DT)
        steps += 1
    assert steps * DT < 0.3  # one blink, not two back to back


def test_blink_does_not_disturb_gaze(config, eyes):
    from animatronic_eyes.module.eyes import GazeTarget

    eyes.look_at(GazeTarget(0.5, 0.5))
    eyes.blink()
    for _ in range(50):
        eyes.update(DT)
    assert eyes.target.x == 0.5
    assert eyes.target.y == 0.5


# --- Idle --------------------------------------------------------------------


def test_idle_targets_stay_within_movement_range(config, eyes, rng):
    idle = IdleBehavior(config.idle, eyes, rng)
    idle.enter()
    limit = config.idle.movement_range
    for _ in range(5000):
        idle.update(DT)
        assert abs(eyes.target.x) <= limit + 1e-9
        assert abs(eyes.target.y) <= limit + 1e-9


def test_idle_blinks_periodically(config, eyes, rng):
    idle = IdleBehavior(config.idle, eyes, rng)
    idle.enter()
    blinks = 0
    was_blinking = False
    for _ in range(int(30.0 / DT)):
        idle.update(DT)
        eyes.update(DT)
        if eyes.is_blinking and not was_blinking:
            blinks += 1
        was_blinking = eyes.is_blinking

    lo = 30.0 / (config.idle.blink_interval_max_ms / 1000.0)
    hi = 30.0 / (config.idle.blink_interval_min_ms / 1000.0)
    assert lo - 1 <= blinks <= hi + 1


def test_idle_changes_gaze_target_over_time(config, eyes, rng):
    idle = IdleBehavior(config.idle, eyes, rng)
    idle.enter()
    targets = set()
    for _ in range(int(30.0 / DT)):
        idle.update(DT)
        targets.add((eyes.target.x, eyes.target.y))
    assert len(targets) > 3


def test_idle_is_deterministic_for_a_given_seed(config, eyes, backend):
    import random

    from animatronic_eyes.module.eyes import EyeController

    def run(seed):
        controller = EyeController(config, backend)
        idle = IdleBehavior(config.idle, controller, random.Random(seed))
        idle.enter()
        out = []
        for _ in range(500):
            idle.update(DT)
            out.append((controller.target.x, controller.target.y))
        return out

    assert run(42) == run(42)
