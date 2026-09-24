"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .app import Application
from .config.loader import DEFAULT_CONFIG_PATH, load
from .config.sanity import ConfigError
from .hal.backend import PWMBackend
from .hal.mock import MockBackend
from .inputs.mock import NullInput
from .inputs.source import InputSource
from .module.eyes import LID_OPEN, EyeController
from .module.servo import Servo

log = logging.getLogger("animatronic_eyes")


def _make_backend(name: str, config) -> PWMBackend:
    if name == "mock":
        return MockBackend(verbose=True)
    from .hal.pca9685 import PCA9685Backend

    return PCA9685Backend(
        i2c_address=config.board.i2c_address,
        pwm_frequency_hz=config.board.pwm_frequency_hz,
    )


def _make_input(name: str, config) -> InputSource:
    if name == "null":
        return NullInput()
    from .inputs.nunchuck import NunchuckInput

    return NunchuckInput(config.nunchuck)


def _cmd_run(args: argparse.Namespace) -> int:
    config = load(args.config)
    backend = _make_backend(args.backend, config)
    source = _make_input(args.input, config)
    Application(config, backend, source).run(duration=args.duration)
    return 0


def _cmd_selftest(args: argparse.Namespace) -> int:
    """Drive one channel through its calibrated travel, slowly.

    Run this on every channel individually during hardware bring-up, before
    running the full system. Listen for buzzing or straining and abort
    immediately if you hear either -- that means the calibrated bounds no
    longer match the mechanism.
    """
    config = load(args.config)

    found = _find_servo(config, args.servo, args.channel)
    if found is None:
        log.error("No servo named %r or on channel %s", args.servo, args.channel)
        return 2
    cfg, kind, _ = found
    if kind == "gaze":
        waypoints = [
            ("center", cfg.center_ticks),
            ("min", cfg.min_ticks),
            ("center", cfg.center_ticks),
            ("max", cfg.max_ticks),
            ("center", cfg.center_ticks),
        ]
    else:
        waypoints = [
            ("open", cfg.open_ticks),
            ("half", cfg.half_ticks),
            ("closed", cfg.closed_ticks),
            ("half", cfg.half_ticks),
            ("open", cfg.open_ticks),
        ]

    backend = _make_backend(args.backend, config)
    servo = Servo(
        channel=cfg.channel,
        min_ticks=min(w[1] for w in waypoints),
        max_ticks=max(w[1] for w in waypoints),
        safety=config.safety,
        backend=backend,
    )

    step_period = config.safety.update_interval_s
    dwell = args.dwell

    print(f"Self-test: channel {cfg.channel}. Ctrl-C to abort.\n")
    try:
        for label, ticks in waypoints:
            print(f"  -> {label:>6}  ({ticks} ticks)")
            # Approach through the slew limiter rather than jumping.
            while servo.position != ticks:
                servo.write(ticks)
                time.sleep(step_period)
            time.sleep(dwell)
        print("\nSelf-test complete. No buzzing? Channel is good.")
    except KeyboardInterrupt:
        print("\nAborted.")
        return 1
    finally:
        backend.deinit()
    return 0


def _find_servo(config, name: str | None, channel: int | None):
    """Resolve a servo by name or channel. Returns (config, kind, name)."""
    table = {
        "horizontal": (config.gaze.horizontal, "gaze"),
        "vertical": (config.gaze.vertical, "gaze"),
        "left_upper": (config.eyelids.left_upper, "lid"),
        "left_lower": (config.eyelids.left_lower, "lid"),
        "right_upper": (config.eyelids.right_upper, "lid"),
        "right_lower": (config.eyelids.right_lower, "lid"),
    }
    for key, (cfg, kind) in table.items():
        if key == name or cfg.channel == channel:
            return cfg, kind, key
    return None


def _cmd_home(args: argparse.Namespace) -> int:
    """Drive servos to a known safe position and exit.

    Gaze goes to centre -- the point furthest from either mechanical stop --
    and eyelids to open. This is the safest command in the tool: one position
    per servo, no sweep, no travel toward a limit. Use it as the first move
    after wiring, and to recover a known state any time the mechanism has been
    left somewhere uncertain.
    """
    config = load(args.config)
    backend = _make_backend(args.backend, config)

    try:
        if args.servo is None and args.channel is None:
            eyes = EyeController(config, backend)
            print("Homing all six channels (gaze centred, lids open).\n")
            eyes.home(
                LID_OPEN,
                on_channel=lambda name, ch, ticks: (
                    print(f"  ch{ch}  {name:<12} -> {ticks}"),
                    time.sleep(config.startup.home_stagger_s),
                )[0],
            )
        else:
            found = _find_servo(config, args.servo, args.channel)
            if found is None:
                log.error("No servo named %r or on channel %s", args.servo, args.channel)
                return 2
            cfg, kind, name = found
            target = cfg.center_ticks if kind == "gaze" else cfg.open_ticks
            servo = Servo(
                channel=cfg.channel,
                min_ticks=target,
                max_ticks=target,
                safety=config.safety,
                backend=backend,
            )
            print(f"Homing ch{cfg.channel} ({name}) -> {target} ticks")
            servo.snap_to(target)

        if args.hold > 0:
            print(f"\nHolding {args.hold:.0f}s. Watch for buzzing or strain. Ctrl-C aborts.")
            time.sleep(args.hold)
    except KeyboardInterrupt:
        print("\nAborted.")
        return 1
    finally:
        backend.deinit()
        print("Output released.")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    config = load(args.config)
    print(f"Configuration OK: {args.config or DEFAULT_CONFIG_PATH}")
    print(f"  Board       0x{config.board.i2c_address:02X} @ {config.board.pwm_frequency_hz} Hz")
    print(f"  Horizontal  ch{config.gaze.horizontal.channel}  "
          f"{config.gaze.horizontal.min_ticks}..{config.gaze.horizontal.max_ticks} "
          f"(center {config.gaze.horizontal.center_ticks})")
    print(f"  Vertical    ch{config.gaze.vertical.channel}  "
          f"{config.gaze.vertical.min_ticks}..{config.gaze.vertical.max_ticks} "
          f"(center {config.gaze.vertical.center_ticks})")
    for name, lid in zip(
        ("left_upper", "left_lower", "right_upper", "right_lower"),
        config.eyelids.all(),
    ):
        print(f"  {name:<11} ch{lid.channel}  "
              f"open {lid.open_ticks} / closed {lid.closed_ticks}"
              f"{'  (inverted)' if lid.inverted else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animatronic-eyes",
        description="Six-axis animatronic eye control.",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help=f"Configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the eye system")
    run.add_argument("--backend", choices=("mock", "pca9685"), default="mock")
    run.add_argument("--input", choices=("null", "nunchuck"), default="null")
    run.add_argument("--duration", type=float, default=None,
                     help="Stop after N seconds (default: run until interrupted)")
    run.set_defaults(func=_cmd_run)

    selftest = sub.add_parser("selftest", help="Exercise one servo through its travel")
    group = selftest.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", type=int, help="PCA9685 channel number")
    group.add_argument("--servo", help="Servo name, e.g. horizontal, left_upper")
    selftest.add_argument("--backend", choices=("mock", "pca9685"), default="pca9685")
    selftest.add_argument("--dwell", type=float, default=1.0,
                          help="Seconds to hold at each waypoint (default: 1.0)")
    selftest.set_defaults(func=_cmd_selftest, channel=None, servo=None)

    home = sub.add_parser(
        "home", help="Drive servo(s) to a safe known position and stop (no sweep)"
    )
    home_target = home.add_mutually_exclusive_group()
    home_target.add_argument("--channel", type=int, help="PCA9685 channel number")
    home_target.add_argument("--servo", help="Servo name, e.g. horizontal")
    home.add_argument("--backend", choices=("mock", "pca9685"), default="pca9685")
    home.add_argument("--hold", type=float, default=3.0,
                      help="Seconds to hold position before releasing (default: 3)")
    home.set_defaults(func=_cmd_home, channel=None, servo=None)

    validate = sub.add_parser("validate", help="Check the configuration and print it")
    validate.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
