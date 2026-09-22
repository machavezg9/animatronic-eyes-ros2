"""Scripted and silent input sources.

NullInput reports no activity at all, which is what exercises the startup
sequence and the drop into idle without any hardware attached. ScriptedInput
replays a fixed list of commands, for deterministic tests of state transitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .source import NEUTRAL, GazeCommand, InputSource


class NullInput(InputSource):
    """Never reports activity. Drives startup -> idle with no manual input."""

    def poll(self) -> GazeCommand:
        return NEUTRAL


@dataclass
class ScriptedInput(InputSource):
    """Replays `commands`, then repeats the final one (or neutral if empty)."""

    commands: Sequence[GazeCommand] = field(default_factory=tuple)
    _index: int = 0

    def poll(self) -> GazeCommand:
        if not self.commands:
            return NEUTRAL
        command = self.commands[min(self._index, len(self.commands) - 1)]
        self._index += 1
        return command

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self.commands)
