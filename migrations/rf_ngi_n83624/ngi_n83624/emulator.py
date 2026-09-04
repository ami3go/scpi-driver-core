"""Small in-process SCPI emulator/fake transport for unit tests and examples."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .exceptions import CommunicationError

ResponseMap = dict[str, str | Callable[[str], str]]


@dataclass
class FakeTransport:
    """Recording fake transport.

    Use this class in unit tests to verify command ordering without hardware. It is
    intentionally small and deterministic, not a complete instrument simulator.
    """

    responses: ResponseMap = field(default_factory=dict)
    default_response: str = "0"
    opened: bool = False
    writes: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    all_commands: list[str] = field(default_factory=list)

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_open(self) -> bool:
        return self.opened

    def write(self, command: str) -> None:
        self._ensure_open()
        command = command.strip()
        self.writes.append(command)
        self.all_commands.append(command)

    def query(self, command: str) -> str:
        self._ensure_open()
        command = command.strip()
        self.queries.append(command)
        self.all_commands.append(command)
        value = self.responses.get(command, self.default_response)
        if callable(value):
            return value(command)
        return value

    def _ensure_open(self) -> None:
        if not self.opened:
            raise CommunicationError("FakeTransport is not open")


class SimpleN83624Emulator(FakeTransport):
    """Minimal stateful emulator for command-sequence tests.

    It supports the common and basic channel commands used by the unit tests. It is
    not a substitute for hardware integration testing.
    """

    def __init__(self) -> None:
        super().__init__(default_response="0")
        self.state: dict[str, float | int | str] = {"*IDN?": "NGI,N83624,0,V1.00"}
        for ch in range(1, 25):
            self.state[f"OUTPut{ch}:MODE"] = 0
            self.state[f"OUTPut{ch}:ONOFF"] = 0
            self.state[f"OUTPut{ch}:STATe"] = 0
            self.state[f"OUTPut{ch}:EVENt"] = 0
            self.state[f"SOURce{ch}:VOLTage"] = 0.0
            self.state[f"SOURce{ch}:OUTCURRent"] = 0.0
            self.state[f"SOURce{ch}:RANGe"] = 3
            self.state[f"CHARge{ch}:VOLTage"] = 0.0
            self.state[f"CHARge{ch}:OUTCURRent"] = 0.0
            self.state[f"CHARge{ch}:Res"] = 0.0
            self.state[f"MEASure{ch}:VOLTage"] = 0.0
            self.state[f"MEASure{ch}:CURRent"] = 0.0
            self.state[f"MEASure{ch}:POWer"] = 0.0
            self.state[f"MEASure{ch}:MAH"] = 0.0
            self.state[f"MEASure{ch}:Res"] = 0.0
            self.state[f"MEASure{ch}:CAPRate"] = 1
            self.state[f"PRO{ch}:CURRent"] = 0.0
            self.state[f"PRO{ch}:VOLTage"] = 0.0
            self.state[f"PRO{ch}:POWEr"] = 0.0
            self.state[f"FAULt{ch}:SIMUlate"] = 0

    def write(self, command: str) -> None:
        super().write(command)
        if command == "*RST":
            return
        key, value = _split_setter(command)
        if key is None:
            return
        try:
            if "." in value or "E" in value.upper():
                parsed: float | int | str = float(value)
            else:
                parsed = int(value)
        except ValueError:
            parsed = value.strip('"')
        self.state[key] = parsed
        m = re.match(r"OUTPut(\d+):ONOFF", key)
        if m:
            ch = int(m.group(1))
            raw = int(parsed) & 1
            self.state[f"OUTPut{ch}:STATe"] = raw

    def query(self, command: str) -> str:
        super().query(command)
        if command == "*IDN?":
            return str(self.state["*IDN?"])
        if command == "*OPC?":
            return "1"
        multi = re.fullmatch(r"MEASure:(VOLTage|CURRent|POWer)\?\(@([0-9,]+)\)", command)
        if multi:
            quantity, channel_csv = multi.groups()
            channels = [int(item) for item in channel_csv.split(",")]
            return ",".join(str(self.state.get(f"MEASure{channel}:{quantity}", 0.0)) for channel in channels)
        key = command[:-1] if command.endswith("?") else command
        if key in self.state:
            return str(self.state[key])
        return self.default_response


def _split_setter(command: str) -> tuple[str | None, str]:
    parts = command.split(maxsplit=1)
    if len(parts) != 2:
        return None, ""
    return parts[0], parts[1]
