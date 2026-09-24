"""Fixed-timestep application loop.

The Arduino ended each iteration with delay(20), so its loop period drifted by
however long the body took. Here the loop sleeps to an absolute deadline on the
monotonic clock, which keeps the period honest on a non-realtime OS, and passes
the measured dt to the motion layer so a missed deadline changes nothing about
how the motion looks.

Shutdown is guaranteed: on normal exit, Ctrl-C, or SIGTERM, the eyes are
recentred, the lids opened, and the backend released, so no servo is left
holding a strained position.
"""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from .behaviors.state_machine import StateMachine
from .config.schema import EyesConfig
from .hal.backend import PWMBackend
from .inputs.source import InputSource
from .module.eyes import LID_CLOSED, EyeController

log = logging.getLogger(__name__)


class Application:
    """Wires the stack together and runs the loop."""

    def __init__(
        self,
        config: EyesConfig,
        backend: PWMBackend,
        input_source: InputSource,
    ) -> None:
        self._cfg = config
        self._backend = backend
        self._input = input_source
        self._eyes = EyeController(config, backend)
        self._machine = StateMachine(config, self._eyes)
        self._running = False

    @property
    def eyes(self) -> EyeController:
        return self._eyes

    @property
    def state_machine(self) -> StateMachine:
        return self._machine

    def stop(self) -> None:
        self._running = False

    def run(self, duration: float | None = None) -> None:
        """Run until stopped, or for `duration` seconds if given."""
        period = self._cfg.safety.update_interval_s
        self._install_signal_handlers()

        log.info(
            "Starting: %.0f Hz loop, input=%s", 1.0 / period, self._input.name
        )

        self._running = True
        try:
            self._input.start()
            self._home()

            clock = time.monotonic
            started = clock()
            previous = started
            deadline = started

            while self._running:
                now = clock()
                dt = now - previous
                previous = now

                command = self._input.poll()
                self._machine.update(command, dt)

                if duration is not None and now - started >= duration:
                    break

                deadline += period
                remaining = deadline - clock()
                if remaining > 0:
                    time.sleep(remaining)
                else:
                    # Overran the budget; resync rather than accumulate debt.
                    deadline = clock()
        except KeyboardInterrupt:
            log.info("Interrupted")
        finally:
            self._shutdown()

    def _home(self) -> None:
        """Bring the servos up one at a time before the loop starts.

        Lids are homed closed rather than open because that is where the
        startup sequence begins -- commanding open first would have the lids
        reverse on the very next frame, adding a needless move to the one part
        of the session where the mechanism's physical position is unknown.
        """
        stagger = self._cfg.startup.home_stagger_s

        def pause(_name: str, _channel: int, _ticks: int) -> None:
            if stagger > 0:
                time.sleep(stagger)

        log.info("Homing servos (%.0f ms apart)", stagger * 1000)
        self._eyes.home(LID_CLOSED, on_channel=pause)

    # --- Lifecycle ----------------------------------------------------------

    def _shutdown(self) -> None:
        self._running = False
        try:
            self._eyes.rest()
        except Exception:
            log.exception("Failed to return eyes to rest position")
        try:
            self._input.stop()
        except Exception:
            log.exception("Failed to stop input source")
        self._backend.deinit()
        log.info("Shutdown complete")

    def _install_signal_handlers(self) -> None:
        def handler(signum: int, _frame: FrameType | None) -> None:
            log.info("Received %s; shutting down", signal.Signals(signum).name)
            self._running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except ValueError:
                # Not on the main thread; the caller owns shutdown.
                pass
